"""Step 13: the VDP on a phone. PageSpeed mobile on the VDP gives the numbers, the gauge and field pictures, and the
full-page render that becomes the four phone screens. The desktop page gives the price stack and the CTA stack as
text (the mobile template is the same), every CTA's host checked for one that leaves the site, click to call found.
Swipes are counted in a phone-sized layout of the same page (412 x 823, a mobile Chrome user agent): the y of the
price stack and of the CTA stack, one swipe per full screen, and what shows on load there (a pop-up, the ComplyAuto
panel, a promotion banner across the top). A blank phone render still leaves the layout read as the second source."""
import re

from . import captures, config, pagespeed, snippets
from .store import now_et

FEE = re.compile(r'fee|processing|doc\b|documentation|admin|dealer handling|filing', re.I)
SELLING = re.compile(r'price|selling|internet|dealer price|your price|our price|sale|final|e-?price|retail', re.I)
NOT_SELLING = re.compile(r'msrp|fee|discount|savings|rebate|payment|/mo|month|apr|down', re.I)
PROMO = re.compile(r'closeout|model year|sale event|clearance|sales event|text .{2,12} to \d{5}|special offer|bonus cash', re.I)
MOBILE_UA = 'Mozilla/5.0 (Linux; Android 11; moto g power (2022)) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.0.0 Mobile Safari/537.36'


def price_label(p):
    lab = p.get('label') or ''
    if FEE.search(lab):
        return 'fee'
    if NOT_SELLING.search(lab):
        return 'other'
    if SELLING.search(lab):
        return 'selling'
    return 'other'


def mobile_layout(store, browser, url, price_texts, cta_texts):
    """The VDP in a phone-sized layout: swipes to the price stack and to the CTA stack, and what shows on load."""
    ctx = browser.browser.new_context(viewport={'width': 412, 'height': 823}, device_scale_factor=1, is_mobile=True, has_touch=True,
                                      user_agent=MOBILE_UA.format(major=browser.browser.version.split('.')[0]), locale=config.LOCALE, timezone_id=config.TIMEZONE)
    try:
        page = ctx.new_page()
        captures.goto(page, url, wait='domcontentloaded')
        page.wait_for_timeout(6000)   # a vendor overlay that opens on load has usually opened by now
        onload = page.evaluate(snippets.VDP_MOBILE, {'priceTexts': price_texts, 'ctaTexts': cta_texts, 'popupSelectors': [v['selector'] for v in config.POPUP_VENDORS]})
        page.evaluate(snippets.SCROLL_PASS)
        page.wait_for_timeout(800)
        after = page.evaluate(snippets.VDP_MOBILE, {'priceTexts': price_texts, 'ctaTexts': cta_texts, 'popupSelectors': [v['selector'] for v in config.POPUP_VENDORS]})
        out = {'source': 'the collector\'s own phone-sized layout (412 x 823, mobile Chrome user agent), not the PageSpeed render', 'at': now_et(),
               'price_stack_y': after['priceY'], 'price_stack_bottom_y': after['priceBottom'], 'cta_stack_y': after['ctaY'], 'cta_stack_bottom_y': after['ctaBottom'],
               'doc_height': after['docHeight'], 'popup_on_load': bool(onload['vendor'] or onload['fixed']), 'popup_detail': onload['vendor'] or onload['fixed'],
               'complyauto_panel_on_load': bool(onload['complyauto']), 'complyauto_text': onload['complyauto'],
               'promo_banner_top': bool(PROMO.search(onload['topText'] or '')), 'top_third_text': onload['topText'][:300], 'tel_links': onload['tel']}
        for k, y in (('swipes_to_price_stack', after['priceY']), ('swipes_to_cta_stack', after['ctaY']), ('swipes_to_full_price_stack', after['priceBottom']), ('swipes_to_full_cta_stack', after['ctaBottom'])):
            out[k] = None if y is None else int(y // 823)
        return out
    finally:
        ctx.close()


def vdp(store, page, report_page, browser=None):
    r = store.results
    url = r['pages'].get('vdp')
    if not url:
        store.check('conversion', 'skipped', 'no VDP from set-up')
        return
    conv = {'ctas': [], 'cta_count': None, 'click_to_call': None, 'swipes_to_price_stack': None, 'swipes_to_cta_stack': None,
            'big_price_is': None, 'price_stack': [], 'popup_on_load': None, 'complyauto_panel_on_load': None, 'promo_banner_top': None,
            'photo_overlay_note': None, 'vdp_lcp_s': None, 'captures': []}
    # PageSpeed mobile on the VDP: numbers by API (with the rerun rule), pictures from the report page (mobile only)
    r['pagespeed']['vdp_mobile'] = {'api': None, 'report': None, 'report_url': None, 'runs': [], 'lcp_is_popup': None, 'captures': {}, 'vehicle_swapped': False}
    rec = r['pagespeed']['vdp_mobile']
    main = None
    if config.PSI_API_KEY:
        try:
            main, runs = pagespeed.api_with_rerun(store, url, 'mobile')
            rec.update({'api': main, 'runs': list(runs), 'lcp_is_popup': main['lcp_is_popup']})
            store.log(f'PageSpeed API VDP mobile: score {main["score"]}, LCP {main["lcp_s"]} s, {main["seconds"]} s')
        except Exception as e:
            store.check('pagespeed_vdp', 'failed', f'API: {type(e).__name__}: {str(e)[:200]}')
    store.save()
    pics = pagespeed.report_pictures(store, report_page, url, 'vdp', sides=('mobile',)) if report_page else {'captures': {}, 'numbers': {}}
    rec['report'] = pics.get('numbers', {}).get('mobile')
    rec['report_url'] = (rec['report'] or {}).get('report_url') or pics.get('report_url')
    if rec['report']:
        rec['runs'].append(rec['report'])
        if rec['lcp_is_popup'] is None:
            rec['lcp_is_popup'] = rec['report']['lcp_is_popup']
    rec['captures'] = {k.split('_', 1)[1]: f'captures/{v}' for k, v in pics.get('captures', {}).items()}
    rec['api_vs_report'] = pagespeed.compare_runs(main, rec['report'])
    src = main or rec['report']
    if src:
        conv['vdp_lcp_s'] = src['lcp_s']
        conv['vdp_lcp_source'] = src['source']
        store.check('pagespeed_vdp', 'ok')
        screens = pagespeed.phone_screens(store, src.get('full_page_screenshot'))
        conv['captures'] = [f'captures/{s}' for s in screens]
        conv['phone_screens_source'] = f'{src["source"]} full-page render, {src["at"]}'
        if not screens:
            store.not_captured('vdp_phone_1.png to vdp_phone_4.png', 'the PageSpeed run carried no full-page render')
    elif 'pagespeed_vdp' not in r['checks']:
        store.check('pagespeed_vdp', 'failed', 'no PageSpeed numbers for the VDP from the API or the report page')
    # price stack and CTAs from the page (same template as the mobile render)
    try:
        captures.goto(page, url)
        page.evaluate(snippets.SCROLL_PASS)
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
        r['conversion'] = conv
        store.save()
    except Exception as e:
        r['conversion'] = conv
        store.check('conversion', 'failed', str(e))
        return
    # swipes and what shows on load, in a phone-sized layout
    if browser:
        try:
            ml = mobile_layout(store, browser, url, [p['text'] for p in prices], [c['text'] for c in ctas if c['text']])
            conv['mobile_layout'] = ml
            for k in ('swipes_to_price_stack', 'swipes_to_cta_stack', 'popup_on_load', 'complyauto_panel_on_load', 'promo_banner_top'):
                conv[k] = ml[k]
            conv['swipe_note'] = 'one swipe is one full 412 x 823 screen; counted in the collector\'s phone-sized layout, confirm on the phone screens'
        except Exception as e:
            store.not_captured('VDP phone layout (swipes, pop-up on load)', f'{type(e).__name__}: {str(e)[:200]}')
    r['conversion'] = conv
    store.check('conversion', 'ok')
