"""Browser contexts and captures: one fresh profile per store at the Desktop PC's viewport, every deck capture at
scale 1, the hide-before-capture list, full-page captures after a scroll pass, crops with the full frame kept in
captures/raw/, red boxes on the exact spot, and the contact sheet."""
from pathlib import Path

from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

from . import config, snippets


class Browser:
    """A headless Chromium with one context per store. Use as a context manager around a store's run."""

    def __init__(self, automation_flag=True):
        self._pw = None
        self.browser = None
        self.automation_flag = automation_flag

    def __enter__(self):
        self._pw = sync_playwright().start()
        # channel='chromium' is the full Chromium in its new headless mode. Playwright's default headless build is the
        # stripped-down headless shell, which Dealer.com's Akamai edge answers with a 403 Access Denied page (seen on
        # bayhyundai.com and butlerlexus.com, Sep 30, 2026); the full browser gets the normal page. No evasion beyond
        # a normal browser: the user agent below is the browser's own version, on a desktop.
        # automation_flag=False turns off navigator.webdriver (Lighthouse's Chrome has it off too). Jonathan's call,
        # Sep 30, 2026: only the pop-up timing pass runs that way, and only after the normal pass has loaded the site;
        # everything else keeps the flag so a platform that blocks headless browsers still shows as chrome_only.
        args = [] if self.automation_flag else ['--disable-blink-features=AutomationControlled']
        self.browser = self._pw.chromium.launch(headless=True, channel='chromium', args=args)
        self.user_agent = config.user_agent_for(self.browser.version)
        return self

    def __exit__(self, *a):
        self.browser.close()
        self._pw.stop()

    def sibling(self, automation_flag=False):
        """A second browser on the same Playwright instance (a second sync_playwright() cannot start inside the first),
        for the pop-up timing pass with the automation flag off. Use as a context manager."""
        return _Sibling(self, automation_flag)

    def context(self):
        return self.browser.new_context(viewport=config.VIEWPORT, device_scale_factor=1, user_agent=self.user_agent,
                                        locale=config.LOCALE, timezone_id=config.TIMEZONE, ignore_https_errors=False)


class _Sibling:
    def __init__(self, parent, automation_flag):
        self.parent = parent
        self.automation_flag = automation_flag
        self.browser = None

    def __enter__(self):
        args = [] if self.automation_flag else ['--disable-blink-features=AutomationControlled']
        self.browser = self.parent._pw.chromium.launch(headless=True, channel='chromium', args=args)
        self.user_agent = config.user_agent_for(self.browser.version)
        return self

    def __exit__(self, *a):
        self.browser.close()

    def context(self):
        return self.browser.new_context(viewport=config.VIEWPORT, device_scale_factor=1, user_agent=self.user_agent,
                                        locale=config.LOCALE, timezone_id=config.TIMEZONE, ignore_https_errors=False)


def goto(page, url, wait='load'):
    """A real navigation with the collector's timeout; returns the response (or None on a client-side redirect).
    A navigation the page itself interrupts (a redirect still in flight from the last page) is tried once more."""
    try:
        return page.goto(url, wait_until=wait, timeout=config.NAV_TIMEOUT)
    except Exception as e:
        if 'interrupted by another navigation' not in str(e):
            raise
        try:
            page.wait_for_load_state('load', timeout=10000)
        except Exception:
            pass
        page.wait_for_timeout(500)
        return page.goto(url, wait_until=wait, timeout=config.NAV_TIMEOUT)


def prepare(page, zoom=None):
    """Before every capture (references/04_capture.md): hide the extension button and the Podium bubble, park the
    mouse off the page, scroll once so lazy images load, set the document zoom when the page renders small."""
    page.evaluate(snippets.HIDE, config.HIDE_BEFORE_CAPTURE)
    page.mouse.move(config.VIEWPORT['width'] - 1, config.VIEWPORT['height'] // 2)
    page.evaluate(snippets.SCROLL_PASS)
    if zoom:
        page.evaluate(snippets.ZOOM, zoom)
        page.wait_for_timeout(400)


def shot(store, page, name, full_page=False, clip=None, zoom=None):
    """Save a capture as captures/<name>.png at scale 1 and record it in results.json."""
    prepare(page, zoom)
    path = store.captures / name
    page.screenshot(path=str(path), full_page=full_page, clip=clip, type='png')
    if zoom:
        page.evaluate(snippets.ZOOM, 1)
    size = Image.open(path).size
    store.record_capture(name, page.url, size)
    store.log(f'captured {name} {size[0]}x{size[1]}')
    return path


def element_shot(store, page, selector, name, zoom=None, pad=0):
    """Capture one element (the Bing panel, a hours block) by its bounding box, at scale 1, below any sticky header."""
    prepare(page, zoom)
    box = page.evaluate("""(sel) => { const e = [...document.querySelectorAll(sel)].find(x => x.getBoundingClientRect().width > 2 && x.getBoundingClientRect().height > 2);
        if (!e) return null; const r = e.getBoundingClientRect(); return { x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height }; }""", selector)
    if not box:
        page.evaluate(snippets.ZOOM, 1)
        raise RuntimeError(f'no visible element {selector} for {name}')
    path = box_shot(store, page, box, name, pad=pad, remeasure=("""(sel) => { const e = [...document.querySelectorAll(sel)].find(x => x.getBoundingClientRect().width > 2 && x.getBoundingClientRect().height > 2);
        if (!e) return null; const r = e.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; }""", selector))
    page.evaluate(snippets.ZOOM, 1)
    return path


STICKY_TOP = """() => { let h = 0; for (const e of document.querySelectorAll('body *')) { const cs = getComputedStyle(e); if ((cs.position === 'fixed' || cs.position === 'sticky') && cs.display !== 'none') {
  const r = e.getBoundingClientRect(); if (r.top <= 2 && r.width > innerWidth * 0.6 && r.height < innerHeight * 0.5) h = Math.max(h, r.bottom); } } return Math.round(h); }"""


def sticky_top(page):
    """The height of a fixed or sticky header at the top of the frame, so a capture can be scrolled out from under it."""
    try:
        return page.evaluate(STICKY_TOP)
    except Exception:
        return 0


def box_shot(store, page, box, name, pad=0, zoom=None, remeasure=None):
    """Capture a page-coordinate box at scale 1: scroll it into the frame below any sticky header, clip in viewport
    coordinates. A box taller than the frame is captured from its top. remeasure, a (js, arg) pair returning the
    element's viewport rect, is read after the scroll: an element inside a sticky header keeps its own place."""
    if zoom:
        page.evaluate(snippets.ZOOM, zoom)
        page.wait_for_timeout(400)
    top_pad = sticky_top(page) + 12
    page.evaluate('(y) => window.scrollTo(0, y)', max(0, box['y'] - pad - top_pad))
    page.wait_for_timeout(250)
    sy = page.evaluate('() => window.scrollY')
    top = box['y'] - pad - sy
    if remeasure:
        rect = page.evaluate(remeasure[0], remeasure[1])
        if rect:
            box = {'x': rect['x'], 'y': rect['y'] + sy, 'w': rect['w'], 'h': rect['h']}
            top = rect['y'] - pad
    clip = {'x': max(0, box['x'] - pad), 'y': max(0, top), 'width': min(box['w'] + 2 * pad, config.VIEWPORT['width']),
            'height': max(1, min(box['h'] + 2 * pad, config.VIEWPORT['height'] - max(0, top)))}
    page.evaluate(snippets.HIDE, config.HIDE_BEFORE_CAPTURE)
    page.mouse.move(config.VIEWPORT['width'] - 1, config.VIEWPORT['height'] // 2)
    path = store.captures / name
    page.screenshot(path=str(path), clip=clip, type='png')
    if zoom:
        page.evaluate(snippets.ZOOM, 1)
    size = Image.open(path).size
    store.record_capture(name, page.url, size)
    store.log(f'captured {name} {size[0]}x{size[1]}')
    return path


TEXT_LOCATOR = """([t, also, maxLen, scopes, client]) => { const vis = e => { const r = e.getBoundingClientRect(); return r.width > 60 && r.height > 10; };
    const ok = e => vis(e) && (e.innerText || '').includes(t) && (!also || e.innerText.includes(also)) && e.innerText.length <= maxLen && !['SCRIPT','STYLE'].includes(e.tagName) && !e.closest('[class*="map"], [id*="map"], .gm-style');
    for (const scope of scopes) { const roots = scope === 'body' ? [document.body] : [...document.querySelectorAll(scope)]; const els = [];
      for (const root of roots) for (const e of root.querySelectorAll('*')) if (ok(e)) els.push(e);
      const e = els.sort((a, b) => a.innerText.length - b.innerText.length)[0]; if (e) { const r = e.getBoundingClientRect(); return client ? { x: r.left, y: r.top, w: r.width, h: r.height } : { x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height }; } }
    return null; }"""


def text_shot(store, page, text, name, pad=0, zoom=None, max_len=200, also=None, scopes=('header, .page-header, [class*="header"]', 'footer, [class*="footer"]', 'body')):
    """Capture the smallest visible element whose text carries the given string (and a second one, when given: the
    street and the zip code for an address line), looking in the header first, then the footer, then the page, never
    inside a map widget."""
    if zoom:
        page.evaluate(snippets.ZOOM, zoom)
        page.wait_for_timeout(300)
    box = page.evaluate(TEXT_LOCATOR, [text, also, max_len, list(scopes), False])
    if not box and also:
        box = page.evaluate(TEXT_LOCATOR, [text, None, max_len, list(scopes), False])
        also = None
    if not box:
        if zoom:
            page.evaluate(snippets.ZOOM, 1)
        raise RuntimeError(f'no visible element with the text "{text}" for {name}')
    path = box_shot(store, page, box, name, pad=pad, remeasure=(TEXT_LOCATOR, [text, also, max_len, list(scopes), True]))
    if zoom:
        page.evaluate(snippets.ZOOM, 1)
    return path


def union_shot(store, page, selectors, name, zoom=None, pad=0, max_gap=900):
    """Capture the smallest box around one visible match per selector (the SRP's H1 and its count): the first
    selector's first match anchors it, and each later selector contributes its match nearest that anchor when it sits
    within max_gap px. A selector with no match is skipped."""
    prepare(page, zoom)
    boxes = page.evaluate("""(sels) => { const vis = x => x.getBoundingClientRect().width > 2 && x.getBoundingClientRect().height > 2;
        const box = e => { const r = e.getBoundingClientRect(); return { x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height }; };
        const out = []; let anchor = null;
        for (const s of sels) { const m = [...document.querySelectorAll(s)].filter(vis).map(box); if (!m.length) { out.push(null); continue; }
          const pick = anchor ? m.sort((a, b) => Math.abs(a.y - anchor.y) - Math.abs(b.y - anchor.y))[0] : m[0]; if (!anchor) anchor = pick; out.push(pick); }
        return out; }""", selectors)
    boxes = [b for b in boxes if b]
    if not boxes:
        page.evaluate(snippets.ZOOM, 1)
        raise RuntimeError(f'no element for {name} ({selectors})')
    keep = [boxes[0]] + [b for b in boxes[1:] if abs(b['y'] - boxes[0]['y']) < max_gap]
    x0 = min(b['x'] for b in keep); y0 = min(b['y'] for b in keep)
    x1 = max(b['x'] + b['w'] for b in keep); y1 = max(b['y'] + b['h'] for b in keep)
    path = box_shot(store, page, {'x': x0, 'y': y0, 'w': x1 - x0, 'h': y1 - y0}, name, pad=pad)
    page.evaluate(snippets.ZOOM, 1)
    return path


def crop(store, src_name, dst_name, box):
    """Crop a capture in pixels, keeping the full frame in captures/raw/ (the skill's most reliable crop)."""
    src = store.captures / src_name
    raw = store.raw / (Path(dst_name).stem + '_raw' + src.suffix)
    if not raw.exists():
        raw.write_bytes(src.read_bytes())
    im = Image.open(src).convert('RGB').crop(box)
    im.save(store.captures / dst_name)
    store.record_capture(dst_name, store.results['captures'].get(src_name, {}).get('page'), im.size)
    return store.captures / dst_name


def red_box(store, name, box, width=4, color=(217, 48, 37)):
    """Draw the skill's red box (D93025) on a capture at the spot a finding names, in the image's own pixels."""
    path = store.captures / name
    im = Image.open(path).convert('RGB')
    ImageDraw.Draw(im).rectangle(box, outline=color, width=width)
    im.save(path)


def contact_sheet(store, cols=4, tile_w=480):
    """Every capture, four to a row with file names and pixel sizes, to look at before building the deck."""
    files = sorted(p for p in store.captures.glob('*.png') if p.name != 'contact_sheet.png')
    if not files:
        return None
    tiles = []
    for f in files:
        im = Image.open(f).convert('RGB')
        th = max(1, round(im.size[1] * tile_w / im.size[0]))
        tiles.append((f.name, im.resize((tile_w, min(th, tile_w * 2))), im.size))
    rows = (len(tiles) + cols - 1) // cols
    row_h = [max(t[1].size[1] for t in tiles[r * cols:(r + 1) * cols]) + 28 for r in range(rows)]
    sheet = Image.new('RGB', (cols * (tile_w + 12) + 12, sum(row_h) + 12 * (rows + 1)), (215, 215, 215))
    dr = ImageDraw.Draw(sheet)
    y = 12
    for r in range(rows):
        for c, (name, im, size) in enumerate(tiles[r * cols:(r + 1) * cols]):
            x = 12 + c * (tile_w + 12)
            dr.text((x, y), f'{name}  {size[0]}x{size[1]}', fill=(0, 0, 0))
            sheet.paste(im, (x, y + 20))
        y += row_h[r] + 12
    out = store.dir / 'contact_sheet.png'
    sheet.save(out)
    store.log(f'contact sheet: {len(files)} captures')
    return out
