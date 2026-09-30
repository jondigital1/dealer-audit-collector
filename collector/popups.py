"""Step 8: homepage pop-up timing. A fresh context (no cookies), the home page, a poll every 100 ms for the vendor
overlays the skill names and for any fixed element that appears after load covering a third of the viewport, the
seconds from navigation start and from the load event, screenshots before and after, then cookies and storage cleared
and the page loaded again so a cookie-capped pop-up is seen twice (the skill's method). A headless page has no
hidden-tab timing problem, so every load is a visible-tab load."""
from . import captures, config, snippets


def timing(store, browser):
    r = store.results
    home = r['pages']['home']
    selectors = [v['selector'] for v in config.POPUP_VENDORS]
    loads = []
    ctx = browser.context()
    page = ctx.new_page()
    try:
        for n in range(2):
            captures.goto(page, home, wait='domcontentloaded')
            if n == 0:
                page.wait_for_timeout(400)
                captures.shot(store, page, 'popup_before.png')
            res = page.evaluate(snippets.POPUP_POLL, {'selectors': selectors, 'maxMs': config.POPUP_POLL_MS})
            vendor = None
            if res['hit']:
                vendor = next((v['vendor'] for v in config.POPUP_VENDORS if v['selector'] == res['hit']['selector']), res['hit']['selector'])
            open_s = res['popupSec']
            if vendor == 'Gubagoo' and res.get('gubagooSec'):
                open_s = res['gubagooSec']   # the invite renders before a poll can start; its avatar's start time marks it
            loads.append({'n': n + 1, 'vendor': vendor, 'selector': res['hit']['selector'] if res['hit'] else None, 'open_s': open_s,
                          'load_s': res['loadSec'], 'bouncex': res.get('bouncex'), 'at': store.results['captured_at']})
            if n == 0 and res['hit']:
                page.wait_for_timeout(500)
                captures.shot(store, page, 'popup_after.png')
            page.evaluate(snippets.CLEAR_STORAGE)
        hits = [l for l in loads if l['vendor']]
        first = hits[0] if hits else None
        r['popup'] = {'vendor': first['vendor'] if first else None, 'selector': first['selector'] if first else None,
                      'open_s': first['open_s'] if first else None, 'load_s': first['load_s'] if first else (loads[0]['load_s'] if loads else None),
                      'loads': loads, 'second_vendor': None, 'on_srp': None, 'on_vdp_load': None,
                      'captures': ['captures/popup_before.png'] + (['captures/popup_after.png'] if first else [])}
        # Wunderkind campaigns list exit-intent ("bounce") and timed activations; keep them for a second-vendor call
        bx = next((l['bouncex'] for l in loads if l.get('bouncex')), None)
        if bx:
            r['popup']['wunderkind_campaigns'] = bx
        # does the same pop-up open on the SRP?
        if first and r['pages'].get('srp'):
            page.evaluate(snippets.CLEAR_STORAGE)
            captures.goto(page, r['pages']['srp'], wait='domcontentloaded')
            res = page.evaluate(snippets.POPUP_POLL, {'selectors': [first['selector']] if not first['selector'].startswith('fixed:') else selectors, 'maxMs': 15000})
            r['popup']['on_srp'] = bool(res['hit'])
            r['popup']['srp_open_s'] = res['popupSec']
        store.check('popup', 'ok')
    except Exception as e:
        store.check('popup', 'failed', str(e))
    finally:
        ctx.close()
