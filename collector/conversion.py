"""Step 13: the VDP on a phone. PageSpeed runs on the home page only (Jonathan, Sep 30, 2026, 4:18 PM ET: "we do not
need to determine page speed on any page outside of the homepage"), so the VDP's four phone screens come from the
collector's own render: the VDP opened in a fresh context emulating a phone (412 x 823, device scale 1, a current
mobile Chrome user agent, mobile and touch on), the load event plus the pop-up window the skill uses, a full-page
capture cut into 412 x 823 screens with the 4 px #FF2D55 outline at 1.25 scale, named vdp_phone_1.png to
vdp_phone_4.png. The same phone context gives the swipes to the price stack and the CTA stack and what shows on load
(a pop-up, the ComplyAuto panel, a promotion banner). The desktop page gives the price stack and the CTA stack as
text (the mobile template is the same), every CTA's host checked for one that leaves the site, click to call found.
A VDP that fails to load twice in the phone context is swapped for the next vehicle on the SRP, and results.json
says so (vehicle_swapped)."""
import re

from . import captures, config, pagespeed, snippets
from .store import now_et

FEE = re.compile(r'fee|processing|doc\b|documentation|admin|dealer handling|filing', re.I)
SELLING = re.compile(r'price|selling|internet|dealer price|your price|our price|sale|final|e-?price|retail', re.I)
NOT_SELLING = re.compile(r'msrp|fee|discount|savings|rebate|payment|/mo|month|apr|down', re.I)
PROMO = re.compile(r'closeout|model year|sale event|clearance|sales event|text .{2,12} to \d{5}|special offer|bonus cash', re.I)
MOBILE_UA = 'Mozilla/5.0 (Linux; Android 11; moto g power (2022)) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.0.0 Mobile Safari/537.36'
VEHICLE_DETAIL = """() => { const t = (document.body.innerText || ''); const h1 = document.querySelector('h1');
  // the stock number follows "Stock" with a colon or a hash ("In Stock" is not it)
  const stock = (t.match(/Stock\\s*(?:#|No\\.?|Number)?\\s*[:#]\\s*([A-Z0-9-]{3,20})/i) || t.match(/Stock\\s*#\\s*([A-Z0-9-]{3,20})/i) || [])[1] || null;
  // the VIN: schema.org first, then the og:title, then the page's own "VIN# X" (Dealer.com prints it flush against "Stock#")
  let vin = null;
  for (const sc of document.querySelectorAll('script[type="application/ld+json"]')) { const m = (sc.textContent || '').match(/vehicleIdentificationNumber"\\s*:\\s*"([A-HJ-NPR-Z0-9]{17})"/); if (m) { vin = m[1]; break; } }
  if (!vin) { const og = document.querySelector('meta[property="og:title"], meta[name="og:title"]'); const m = og && (og.content || '').match(/VIN:?\\s*([A-HJ-NPR-Z0-9]{17})/i); if (m) vin = m[1]; }
  if (!vin) { const m = t.match(/VIN\\s*(?:#|:)?\\s*([A-HJ-NPR-Z0-9]{17})/i); if (m) vin = m[1]; }
  const tEl = h1 || document.querySelector('[class*="vehicle-title"], [class*="vdp-title"], [class*="vehicleTitle"], h2');
  return { title: tEl && (tEl.innerText || '').trim() ? (tEl.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 120) : document.title.slice(0, 120), stock, vin }; }"""


def price_label(p):
    lab = p.get('label') or ''
    if FEE.search(lab):
        return 'fee'
    if NOT_SELLING.search(lab):
        return 'other'
    if SELLING.search(lab):
        return 'selling'
    return 'other'


def phone_ctas(page, site_host, price_stack_y, price_stack_bottom, price_labels):
    """The CTA stack as the phone render shows it: button-like elements in the main frame and in every iframe (the
    Capital One digital-retail buttons sit in one), placed in page coordinates, from the vehicle title down to 900 px
    below the price stack; gallery controls, tabs, the media toolbar and the offer accordions are left out."""
    buttons = []
    for fr in page.frames:
        try:
            if fr == page.main_frame:
                off_x, off_y, frame_host = 0, 0, None
            else:
                el = fr.frame_element()
                box = el.bounding_box()
                if not box or box['width'] < 60 or box['height'] < 30:
                    continue
                sy = page.evaluate('() => window.scrollY')
                off_x, off_y = box['x'], box['y'] + sy
                frame_host = (fr.url.split('/')[2] if '://' in fr.url else '') or None
            for b in fr.evaluate(snippets.PHONE_BUTTONS):
                b['y'] = round(b['y'] + off_y)
                b['frame'] = frame_host
                buttons.append(b)
        except Exception:
            continue
    buttons.sort(key=lambda b: b['y'])
    skip = re.compile(r'load more|photos?$|^\d+\s*/\s*\d+$|^ext\.?$|^int\.?$|track price|^save$|^share$|compare|window sticker|full specs|^details$|highlights|full review|collapse|expand|^next$|^prev|^back$|^close$|^menu$|^\d+$', re.I)
    labels = [l.lower()[:30] for l in price_labels if l]
    top = 150
    bottom = (price_stack_bottom or price_stack_y or 2000) + 900
    seen = set()
    tels = set()
    stack = []
    tabs = []
    for b in buttons:
        t = b['text']
        if b['y'] < top or b['y'] > bottom or skip.search(t) or re.search(r'\$\s?\d', t):
            continue
        if any(t.lower().startswith(l) for l in labels):   # an offer accordion (its label runs past the 40 characters the stack kept)
            continue
        if re.search(r'\b(19|20)\d\d\b.*\b\d{1,3}$', t):   # a gallery thumbnail button: the vehicle's title plus its slide number
            continue
        if b['tel']:
            num = re.sub(r'\D', '', b['href'])[-10:]
            if num in tels:
                continue
            tels.add(num)
        key = (t.lower(), b['y'] // 12)
        if key in seen:
            continue
        seen.add(key)
        # the price panel's tabs (BUY, FINANCE, LEASE, CASH) switch the stack's view; they are not CTAs (Jonathan, Oct 1, 2026)
        if re.fullmatch(r'(buy|finance|lease|cash|purchase|buy now|finance now)', t, re.I):
            tabs.append({'text': t, 'y_phone': b['y'], 'screen': b['y'] // 823 + 1})
            continue
        host = b['host'] or (b['frame'] if b['frame'] and site_host not in b['frame'] else '')
        leaves = bool(host) and site_host not in host and not b['tel']
        stack.append({'text': b['text'], 'host': host or site_host, 'href': b['href'], 'leaves_site': leaves, 'y_phone': b['y'], 'tel': b['tel'], 'target': b['target'],
                      'frame': b['frame'], 'screen': b['y'] // 823 + 1})
    return stack[:14], buttons, tabs


def phone_pass(store, browser, url, price_texts, cta_texts):
    """The VDP in a phone context: the load event, the skill's pop-up window, what shows on load, the full-page
    render cut into phone screens, then the swipes to the price stack and the CTA stack after a scroll pass."""
    ctx = browser.browser.new_context(viewport={'width': 412, 'height': 823}, device_scale_factor=1, is_mobile=True, has_touch=True,
                                      user_agent=MOBILE_UA.format(major=browser.browser.version.split('.')[0]), locale=config.LOCALE, timezone_id=config.TIMEZONE)
    try:
        page = ctx.new_page()
        captures.goto(page, url, wait='load')
        poll = page.evaluate(snippets.POPUP_POLL, {'selectors': [v['selector'] for v in config.POPUP_VENDORS], 'maxMs': config.POPUP_POLL_MS})
        args = {'priceTexts': price_texts, 'ctaTexts': cta_texts, 'popupSelectors': [v['selector'] for v in config.POPUP_VENDORS]}
        onload = page.evaluate(snippets.VDP_MOBILE, args)
        page.evaluate(snippets.HIDE, config.HIDE_BEFORE_CAPTURE)
        raw = store.raw / 'vdp_phone_render.png'
        page.screenshot(path=str(raw), full_page=True, type='png')
        screens = pagespeed.phone_screens(store, image_path=raw)
        rendered_at = now_et()
        page.evaluate(snippets.SCROLL_PASS)
        page.wait_for_timeout(800)
        after = page.evaluate(snippets.VDP_MOBILE, args)
        site_host = url.split('/')[2].replace('www.', '')
        cta_stack, all_buttons, tabs = phone_ctas(page, site_host, after['priceY'], after['priceBottom'], store.results.get('conversion', {}).get('_price_labels', []))
        # a digital-retail iframe (Capital One through autodriven, Roadster, and the like) that stays 0 x 0 in the
        # headless phone context never shows its buttons here; Natchez Nissan's did not size in 38 s (Sep 30, 2026).
        # What the render shows where it sits is recorded: its parent's place on the page and the buttons seen there.
        dead = page.evaluate("""() => [...document.querySelectorAll('iframe')].filter(f => /autodriven|capitalone|digital-retail|roadster|carnow|drive\\.|gubagoo|modal|tekion|darwin|dealer-fx/i.test(f.src || '') && f.getBoundingClientRect().width < 10)
            .map(f => { let p = f.parentElement; while (p && p.getBoundingClientRect().height === 0 && p !== document.body) p = p.parentElement; const r = p ? p.getBoundingClientRect() : null;
              return { host: (f.src || '').split('/')[2] || '', parent: p ? (p.className || p.tagName).toString().slice(0, 50) : null, y: r ? Math.round(r.top + scrollY) : null, h: r ? Math.round(r.height) : null }; })""")
        if dead:
            for d in dead:
                near = [b for b in all_buttons if d['y'] is not None and d['y'] - 40 <= b['y'] <= d['y'] + (d['h'] or 0) + 40]
                d['screen'] = None if d['y'] is None else d['y'] // 823 + 1
                d['buttons_shown_there'] = [b['text'] for b in near][:8]
                d['buttons_shown_count'] = len(near)
            hosts = sorted({d['host'] for d in dead if d['host']})
            store.not_captured('VDP digital-retail buttons in the phone render', f'the {", ".join(hosts)} iframe stayed 0 x 0 in the headless phone context, so its buttons (payment, pre-qualification, trade value) are not in the CTA stack; Chrome confirms them. '
                               + '; '.join(f'at its place (screen {d["screen"]}, y {d["y"]}) the render shows {d["buttons_shown_count"]} button(s){": " + ", ".join(d["buttons_shown_there"]) if d["buttons_shown_there"] else ""}' for d in dead))
        out = {'source': "the collector's own phone render (412 x 823, device scale 1, mobile Chrome user agent)", 'rendered_at': rendered_at,
               'popup_window_s': config.POPUP_POLL_MS // 1000, 'popup_hit': poll.get('hit'), 'popup_open_s': poll.get('popupSec'), 'load_s': poll.get('loadSec'),
               'screens': screens, 'render_height_px': None,
               'price_stack_y': after['priceY'], 'price_stack_bottom_y': after['priceBottom'], 'cta_stack_y': after['ctaY'], 'cta_stack_bottom_y': after['ctaBottom'],
               'doc_height': after['docHeight'], 'popup_on_load': bool(onload['vendor'] or onload['fixed'] or poll.get('hit')), 'popup_detail': onload['vendor'] or onload['fixed'] or poll.get('hit'),
               'complyauto_panel_on_load': bool(onload['complyauto']), 'complyauto_text': onload['complyauto'],
               'promo_banner_top': bool(PROMO.search(onload['topText'] or '')), 'top_third_text': onload['topText'][:300], 'tel_links': onload['tel'],
               'cta_stack': cta_stack, 'price_panel_tabs': tabs, 'digital_retail_iframes': dead, 'buttons_all': all_buttons[:80]}
        from PIL import Image
        out['render_height_px'] = Image.open(raw).size[1]
        for k, y in (('swipes_to_price_stack', after['priceY']), ('swipes_to_cta_stack', after['ctaY']), ('swipes_to_full_price_stack', after['priceBottom']), ('swipes_to_full_cta_stack', after['ctaBottom'])):
            out[k] = None if y is None else int(y // 823)
        return out
    finally:
        ctx.close()


def next_vehicle(store, page, skip_href):
    """The next priced vehicle on the SRP after the one that failed (the swap rule)."""
    captures.goto(page, store.results['pages']['srp'])
    page.wait_for_timeout(1500)
    return page.evaluate(snippets.NEXT_VEHICLE, skip_href)


def read_stack(store, page, url, conv):
    """The desktop page: the vehicle's title, stock and VIN, the price stack, the CTAs, the off-site links, the photo."""
    r = store.results
    captures.goto(page, url)
    page.evaluate(snippets.SCROLL_PASS)
    r['pages']['vdp_vehicle_detail'] = page.evaluate(VEHICLE_DETAIL)
    st = page.evaluate(snippets.VDP_STACK)
    prices = st['prices']
    for p in prices:
        p['label_kind'] = price_label(p)
    conv['price_stack'] = prices
    conv['other_prices_on_page'] = st['other_prices']
    big = next((p for p in prices if p.get('biggest')), None)
    if big:
        kind = price_label(big)
        conv['big_price_is'] = f'{big["label"] or "unlabeled"} {big["text"]} ({"a fee" if kind == "fee" else "the selling price" if kind == "selling" else "not marked as the selling price"})'
        conv['big_price_kind'] = kind
        if not any(price_label(p) == 'selling' for p in prices):
            conv['big_price_is'] += '; no selling price found in the stack'
    offsite = page.evaluate(snippets.VDP_OFFSITE_LINKS)
    host = st['host']
    ctas = []
    for c in st['ctas']:
        leaves = bool(c['host']) and c['host'] != host
        ctas.append({'text': c['text'], 'host': c['host'] or host, 'href': c['href'], 'leaves_site': leaves, 'y_desktop': c['y'], 'tel': c['tel'], 'target': c['target']})
    conv['ctas'] = ctas
    conv['cta_count'] = len(ctas)
    conv['click_to_call'] = any(c['tel'] for c in ctas) or bool(st['hidden_tel'])
    conv['click_to_call_note'] = ('a tel link sits in the stack' if any(c['tel'] for c in ctas) else
                                  f'tel links hidden on desktop, shown on a phone: {", ".join(t["text"] or t["number"] for t in st["hidden_tel"][:3])}' if st['hidden_tel'] else 'no tel link in the stack')
    conv['buttons_all'] = st['buttons_all']
    conv['offsite_links'] = offsite[:40]
    conv['stack_read_at'] = now_et()
    try:
        ph = page.evaluate(snippets.VDP_PHOTO)
        if ph:
            captures.box_shot(store, page, {'x': ph['x'], 'y': ph['y'], 'w': ph['w'], 'h': ph['h']}, 'vdp_photo.png')
            conv['captures'].append('captures/vdp_photo.png')
            conv['photo'] = {'src': ph['src'], 'alt': ph['alt']}
        else:
            store.not_captured('vdp_photo.png', 'no gallery image found on the VDP')
    except Exception as e:
        store.not_captured('vdp_photo.png', str(e))
    return prices, ctas


def vdp(store, page, report_page=None, browser=None):
    r = store.results
    url = r['pages'].get('vdp')
    if not url:
        store.check('conversion', 'skipped', 'no VDP from set-up')
        return
    conv = {'ctas': [], 'cta_count': None, 'click_to_call': None, 'swipes_to_price_stack': None, 'swipes_to_cta_stack': None,
            'big_price_is': None, 'price_stack': [], 'popup_on_load': None, 'complyauto_panel_on_load': None, 'promo_banner_top': None,
            'photo_overlay_note': None, 'captures': []}
    r['pages']['vehicle_swapped'] = False
    # the desktop read, then the phone pass; a VDP that fails to load twice in the phone context is swapped once
    for attempt in range(1, 4):
        try:
            prices, ctas = read_stack(store, page, url, conv)
            conv['_price_labels'] = [p.get('label') for p in prices]
            r['conversion'] = conv
            store.save()
        except Exception as e:
            r['conversion'] = conv
            store.check('conversion', 'failed', f'{type(e).__name__}: {str(e)[:200]}')
            return
        if not browser:
            break
        failures = []
        ml = None
        for n in (1, 2):
            try:
                ml = phone_pass(store, browser, url, [p['text'] for p in prices], [c['text'] for c in ctas if c['text']])
                break
            except Exception as e:
                failures.append(f'{type(e).__name__}: {str(e)[:160]}')
        if ml:
            conv['phone_render'] = ml
            conv['ctas_desktop'] = ctas
            if ml.get('cta_stack'):
                # the CTA stack is what the phone shows (iframes included); the desktop read is kept beside it
                conv['ctas'] = ml['cta_stack']
                conv['cta_count'] = len(ml['cta_stack'])
                conv['price_panel_tabs'] = ml.get('price_panel_tabs') or []
                conv['cta_stack_source'] = 'the phone render\'s DOM, iframes included'
                conv['swipes_to_cta_stack'] = None
                ys = [c['y_phone'] for c in ml['cta_stack']]
                ml['cta_stack_y'] = min(ys)
                ml['cta_stack_bottom_y'] = max(ys)
                ml['swipes_to_cta_stack'] = int(min(ys) // 823)
                ml['swipes_to_full_cta_stack'] = int(max(ys) // 823)
            conv['captures'] = [f'captures/{s}' for s in ml['screens']] + [c for c in conv['captures'] if 'vdp_photo' in c]
            conv['phone_screens_source'] = f'{ml["source"]}, {ml["rendered_at"]}'
            conv['swipes_to_price_stack'] = ml['swipes_to_full_price_stack'] if ml['swipes_to_full_price_stack'] is not None else ml['swipes_to_price_stack']
            conv['swipes_to_cta_stack'] = ml['swipes_to_full_cta_stack'] if ml['swipes_to_full_cta_stack'] is not None else ml['swipes_to_cta_stack']
            for k in ('popup_on_load', 'complyauto_panel_on_load', 'promo_banner_top'):
                conv[k] = ml[k]
            conv['swipe_note'] = 'one swipe is one full 412 x 823 screen, counted to the bottom of the stack in the phone render; confirm on the phone screens'
            # a tel link that sits in the CTA stack on a phone (Call Now shows only there) is a CTA and click to call
            if ml.get('cta_stack_y') is not None:
                lo, hi = ml['cta_stack_y'] - 60, (ml.get('cta_stack_bottom_y') or ml['cta_stack_y']) + 120
                for t in ml.get('tel_links') or []:
                    if lo <= t['y'] <= hi and not any(c.get('tel') and c['text'] == t['text'] for c in conv['ctas']):
                        conv['ctas'].append({'text': t['text'], 'host': 'tel', 'href': 'tel:' + t['number'], 'leaves_site': False, 'y_phone': t['y'], 'tel': True, 'target': '', 'note': 'shown on a phone only'})
                conv['cta_count'] = len(conv['ctas'])
                if any(c.get('tel') for c in conv['ctas']):
                    conv['click_to_call'] = True
                    conv['click_to_call_note'] = 'a tel link sits in the CTA stack on a phone'
                elif not conv.get('click_to_call'):
                    conv['click_to_call'] = False
            have = {p['number'] for p in r.get('phones') or []}
            for t in ml.get('tel_links') or []:
                digits = re.sub(r'\D', '', t['number'])[-10:]
                num = f'({digits[:3]}) {digits[3:6]}-{digits[6:]}' if len(digits) == 10 else None
                if num and num not in have:
                    have.add(num)
                    r.setdefault('phones', []).append({'where': 'VDP in the phone render (tel link)', 'dept': t['text'][:30] or 'Call', 'number': num})
            d = r['pages'].get('vdp_vehicle_detail') or {}
            r['checks']['vdp_render'] = 'ok'
            r['vdp_render'] = {'status': 'ok', 'rendered_at': ml['rendered_at'], 'url': url, 'vehicle': d, 'screens': ml['screens'], 'render_height_px': ml['render_height_px'],
                               'attempts': n, 'vehicle_swapped': r['pages']['vehicle_swapped']}
            break
        # two failures at this VDP: swap for the next vehicle on the SRP, once
        store.log(f'the VDP did not render in the phone context twice ({failures[-1]}); swapping for the next vehicle on the SRP')
        nxt = next_vehicle(store, page, url) if attempt < 3 else None
        if not nxt or r['pages']['vehicle_swapped']:
            r['conversion'] = conv
            r['vdp_render'] = {'status': 'failed', 'url': url, 'failures': failures, 'vehicle_swapped': r['pages']['vehicle_swapped']}
            store.check('vdp_render', 'failed', f'the VDP did not render in the phone context twice: {failures[-1]}')
            break
        r['pages']['vehicle_swapped'] = True
        r['pages']['vdp_swapped_from'] = url
        url = nxt['href'].split('?')[0] if 'priorityType' in nxt['href'] else nxt['href']
        r['pages']['vdp'] = url
        r['pages']['vdp_vehicle'] = nxt['text'][:160]
        store.log(f'VDP swapped to {url}')
    conv.pop('_price_labels', None)
    r['conversion'] = conv
    store.check('conversion', 'ok')
