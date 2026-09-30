"""Browser contexts and captures: one fresh profile per store at the Desktop PC's viewport, every deck capture at
scale 1, the hide-before-capture list, full-page captures after a scroll pass, crops with the full frame kept in
captures/raw/, red boxes on the exact spot, and the contact sheet."""
from pathlib import Path

from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

from . import config, snippets


class Browser:
    """A headless Chromium with one context per store. Use as a context manager around a store's run."""

    def __init__(self):
        self._pw = None
        self.browser = None

    def __enter__(self):
        self._pw = sync_playwright().start()
        # channel='chromium' is the full Chromium in its new headless mode. Playwright's default headless build is the
        # stripped-down headless shell, which Dealer.com's Akamai edge answers with a 403 Access Denied page (seen on
        # bayhyundai.com and butlerlexus.com, Sep 30, 2026); the full browser gets the normal page. No evasion beyond
        # a normal browser: the user agent below is the browser's own version, on a desktop.
        self.browser = self._pw.chromium.launch(headless=True, channel='chromium')
        self.user_agent = config.user_agent_for(self.browser.version)
        return self

    def __exit__(self, *a):
        self.browser.close()
        self._pw.stop()

    def context(self):
        return self.browser.new_context(viewport=config.VIEWPORT, device_scale_factor=1, user_agent=self.user_agent,
                                        locale=config.LOCALE, timezone_id=config.TIMEZONE, ignore_https_errors=False)


def goto(page, url, wait='load'):
    """A real navigation with the collector's timeout; returns the response (or None on a client-side redirect)."""
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
    """Capture one element (the Bing panel, a PageSpeed gauge block) by its bounding box, at scale 1."""
    prepare(page, zoom)
    el = page.query_selector(selector)
    if el is None:
        raise RuntimeError(f'no element {selector} for {name}')
    el.scroll_into_view_if_needed()
    page.wait_for_timeout(300)
    box = el.bounding_box()
    if not box:
        raise RuntimeError(f'{selector} has no box for {name}')
    clip = {'x': max(0, box['x'] - pad), 'y': max(0, box['y'] - pad), 'width': box['width'] + 2 * pad, 'height': box['height'] + 2 * pad}
    return shot(store, page, name, clip=clip)


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
