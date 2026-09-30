"""Step 13: the VDP on a phone. PageSpeed mobile on the VDP gives the numbers, the gauge and field pictures, and the
full-page render that becomes the four phone screens. In the desktop page, the price stack and the CTA stack are read
as text (the mobile template is the same), every CTA's host checked for one that leaves the site, click to call
found, and the swipes to the price stack and the CTA stack counted from the render's pixel positions."""
import re

from . import captures, pagespeed, snippets

FEE = re.compile(r'fee|processing|doc|admin|dealer handling', re.I)
SELLING = re.compile(r'price|our price|sale price|selling|internet|bay price|dealer price|your price|total', re.I)
PROMO = re.compile(r'closeout|model year|sale event|clearance|text .{2,12} to \d{5}', re.I)


def vdp(store, page, report_page):
    r = store.results
    url = r['pages'].get('vdp')
    if not url:
        store.check('conversion', 'skipped', 'no VDP from set-up')
        return
    conv = {'ctas': [], 'cta_count': None, 'click_to_call': None, 'swipes_to_price_stack': None, 'swipes_to_cta_stack': None,
            'big_price_is': None, 'price_stack': [], 'popup_on_load': None, 'complyauto_panel_on_load': None, 'promo_banner_top': None,
            'photo_overlay_note': None, 'vdp_lcp_s': None, 'captures': []}
    # PageSpeed mobile on the VDP: numbers by API (with the rerun rule), pictures from the report page
    try:
        main, runs = pagespeed.api_with_rerun(store, url, 'mobile')
        pics = pagespeed.report_pictures(store, report_page, url, 'vdp') if report_page else {'captures': {}, 'numbers': {}}
        r['pagespeed']['vdp_mobile'] = {'api': main, 'report': pics.get('numbers', {}).get('mobile'), 'report_url': pics.get('report_url'),
                                        'runs': runs, 'lcp_is_popup': main['lcp_is_popup'], 'captures': pics.get('captures', {}), 'vehicle_swapped': False}
        conv['vdp_lcp_s'] = main['lcp_s']
        screens = pagespeed.phone_screens(store, main.get('full_page_screenshot'))
        conv['captures'] = [f'captures/{s}' for s in screens]
        # the render's text is not readable from pixels; the stack positions come from the desktop page below, which is
        # the same template; the screens themselves carry the visual evidence the slide shows
    except Exception as e:
        store.check('pagespeed_vdp', 'failed', str(e))
    # price stack and CTAs from the page (same template as the mobile render)
    try:
        captures.goto(page, url)
        page.evaluate(snippets.SCROLL_PASS)
        st = page.evaluate(snippets.VDP_STACK)
        prices = st['prices']
        if prices:
            big = max(prices, key=lambda p: p['size'])
            for p in prices:
                p['biggest'] = p is big
                p['label'] = 'fee' if FEE.search(p['text']) else ('selling' if SELLING.search(p['text']) else 'other')
            conv['price_stack'] = prices
            conv['big_price_is'] = 'fee' if FEE.search(big['text']) else ('selling price' if SELLING.search(big['text']) else big['text'][:40])
            if not any(p['label'] == 'selling' for p in prices):
                conv['big_price_is'] = conv['big_price_is'] + ' (no selling price found in the stack)'
        offsite = page.evaluate(snippets.VDP_OFFSITE_LINKS)
        host = st['host']
        ctas = []
        for c in st['ctas']:
            leaves = bool(c['host']) and c['host'] != host
            ctas.append({'text': c['text'], 'host': c['host'] or host, 'leaves_site': leaves, 'y': c['y'], 'tel': c['tel']})
        conv['ctas'] = ctas
        conv['cta_count'] = len(ctas)
        conv['click_to_call'] = any(c['tel'] for c in ctas)
        conv['offsite_links'] = offsite[:40]
        # swipes: one swipe is one full phone screen (823 px at 412 wide); the desktop page's y positions are mapped by
        # the ratio of document heights when the render is present, else left null for Claude to count on the screens
        fps = (r['pagespeed'].get('vdp_mobile') or {}).get('api', {}).get('full_page_screenshot') or {}
        doc_h = page.evaluate('() => document.body.scrollHeight')
        if fps.get('height') and doc_h:
            k = fps['height'] / doc_h
            first_price = min((p['y'] for p in prices), default=None)
            first_cta = min((c['y'] for c in ctas if c['text']), default=None)
            conv['swipes_to_price_stack'] = None if first_price is None else int(first_price * k // 823)
            conv['swipes_to_cta_stack'] = None if first_cta is None else int(first_cta * k // 823)
            conv['swipe_note'] = 'mapped from the desktop page by document height; confirm on the phone screens'
        text_top = page.evaluate('() => (document.body.innerText || "").slice(0, 600)')
        conv['promo_banner_top'] = bool(PROMO.search(text_top))
        conv['complyauto_panel_on_load'] = bool(page.query_selector('[class*="complyauto"], iframe[src*="complyauto"]'))
        try:
            captures.element_shot(store, page, '[class*="gallery"] img, [class*="media"] img, .vehicle-image img, img[class*="vehicle"]', 'vdp_photo.png')
            conv['captures'].append('captures/vdp_photo.png')
        except Exception as e:
            store.not_captured('vdp_photo.png', str(e))
        r['conversion'] = conv
        store.check('conversion', 'ok')
    except Exception as e:
        r['conversion'] = conv
        store.check('conversion', 'failed', str(e))
