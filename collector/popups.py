"""Step 8: homepage pop-up timing. First one normal load (navigator.webdriver true, the browser the rest of the run
uses), polled for the vendor overlays the skill names and for any fixed element that appears after load covering a
third of the viewport. Then the timing pass in a second browser with the automation flag off, the skill's method:
a fresh context, the home page, the poll, screenshots before and after, then cookies and storage cleared and the page
loaded again so a cookie-capped pop-up is seen twice, then the SRP for the same pop-up. Gubagoo's invite renders only
with the flag off (Sep 30, 2026, Bay Hyundai), which is why the pass exists; Jonathan's call, Sep 30: the flag is off
for this pass only, after the normal pass has loaded the site. Every load says which way it ran."""
import re

from . import captures, config, snippets
from .store import now_et


# What a firewall or challenge page says (the platform test's list); a normal page never carries these
CHALLENGE = re.compile(r'access denied|attention required|checking your browser|cloudflare|incapsula|captcha|verify you are human|'
                       r'request blocked|you don\'t have permission|bot detection|pardon our interruption|errors\.edgesuite\.net', re.I)


def real_page(page, resp):
    """Did the normal pass load the real page: a status under 400, no challenge words, and a menu with images."""
    status = resp.status if resp else None
    if status is not None and status >= 400:
        return False, f'HTTP {status}'
    st = page.evaluate("""() => ({ text: (document.body.innerText || '').slice(0, 4000), title: document.title, links: document.querySelectorAll('a[href]').length, imgs: document.images.length })""")
    m = CHALLENGE.search(st['text'] + ' ' + st['title'])
    if m:
        return False, f'challenge page: "{m.group(0)}"'
    if st['links'] < 10 or st['imgs'] < 1:
        return False, f'no real content: {st["links"]} links, {st["imgs"]} images'
    return True, f'HTTP {status}, {st["links"]} links, {st["imgs"]} images'


def one_load(store, page, home, selectors, n, shot=True):
    resp = captures.goto(page, home, wait='domcontentloaded')
    page._collector_resp = resp
    if shot:
        page.wait_for_timeout(400)
        captures.shot(store, page, 'popup_before.png', keep_overlays=True)
    res = page.evaluate(snippets.POPUP_POLL, {'selectors': selectors, 'maxMs': config.POPUP_POLL_MS})
    try:   # the load event's time, read once it has fired (a pop-up can open before it)
        page.wait_for_load_state('load', timeout=30000)
        res['loadSec'] = page.evaluate("() => { const n = performance.getEntriesByType('navigation')[0]; return n && n.loadEventEnd ? +(n.loadEventEnd / 1000).toFixed(1) : null; }")
    except Exception:
        pass
    vendor = None
    if res['hit']:
        vendor = next((v['vendor'] for v in config.POPUP_VENDORS if v['selector'] == res['hit']['selector']), res['hit']['selector'])
    open_s = res['popupSec']
    if vendor == 'Gubagoo' and res.get('gubagooSec'):
        open_s = res['gubagooSec']   # the invite renders before a poll can start; its avatar's start time marks it
    lcp = page.evaluate(snippets.LCP_READ)
    load = {'n': n, 'vendor': vendor, 'selector': res['hit']['selector'] if res['hit'] else None, 'open_s': open_s, 'load_s': res['loadSec'],
            'after_load_s': None if open_s is None or res['loadSec'] is None else round(open_s - res['loadSec'], 1),
            'bouncex': res.get('bouncex'), 'at': now_et(),
            'lcp_observed': lcp and {**lcp, 'source': "the collector's own headless load (PerformanceObserver), not PageSpeed"}}
    if res['hit']:
        load['size'] = f'{res["hit"].get("w")} x {res["hit"].get("h")}'
        load['text'] = (res['hit'].get('text') or '').replace('\n', ' ')[:200]
    if res['hit'] and shot:
        page.wait_for_timeout(500)
        captures.shot(store, page, 'popup_after.png', keep_overlays=True)
    return load


def timing(store, browser):
    r = store.results
    home = r['pages']['home']
    selectors = [v['selector'] for v in config.POPUP_VENDORS]
    r['popup'] = {'vendor': None, 'selector': None, 'open_s': None, 'load_s': None, 'loads': [], 'second_vendor': None, 'on_srp': None, 'on_vdp_load': None,
                  'normal_pass': None, 'method': None, 'lcp_observed': None, 'vendors_present': None, 'captures': []}
    # 1. the normal pass, in the run's own browser (navigator.webdriver true)
    ctx = browser.context()
    ctx.add_init_script(snippets.LCP_OBSERVER)
    page = ctx.new_page()
    ok, why = False, None
    try:
        normal = one_load(store, page, home, selectors, 1, shot=False)
        normal['webdriver'] = True
        ok, why = real_page(page, page._collector_resp)
        normal['real_page'] = ok
        normal['real_page_note'] = why
        r['popup']['normal_pass'] = normal
        r['popup']['vendors_present'] = page.evaluate(snippets.VENDOR_SCRIPTS)
        r['popup']['lcp_observed'] = normal.get('lcp_observed')
    except Exception as e:
        why = f'{type(e).__name__}: {str(e)[:200]}'
        r['popup']['normal_pass'] = {'error': why, 'webdriver': True, 'real_page': False}
    finally:
        ctx.close()
    store.save()
    if not ok:
        # a blocked or challenged load: no flag-off pass (that would be routing around the block); the platform is
        # marked chrome_only for this store and the timing goes to Chrome
        r['popup']['method'] = f'timing pass not run: the normal pass did not load the real page ({why})'
        store.results['collector']['platform_headless'] = 'chrome_only'
        if store.results.get('preflight'):
            store.results['preflight']['platform_headless'] = 'chrome_only'
            store.results['preflight']['notes'].append(f'the pop-up step\'s normal load was blocked or challenged ({why}); marked chrome_only')
        store.check('popup', 'skipped', f'the normal pass did not load the real page ({why}); no flag-off pass, pop-up timing goes to Chrome')
        return
    # 2. the timing pass, with the automation flag off, the skill's two loads and the SRP
    loads = []
    try:
        with browser.sibling(automation_flag=False) as b2:
            ctx = b2.context()
            ctx.add_init_script(snippets.LCP_OBSERVER)
            page = ctx.new_page()
            for n in range(2):
                load = one_load(store, page, home, selectors, n + 1, shot=(n == 0))
                load['webdriver'] = False
                loads.append(load)
                page.evaluate(snippets.CLEAR_STORAGE)
            hits = [l for l in loads if l['vendor']]
            first = hits[0] if hits else None
            r['popup'].update({'vendor': first['vendor'] if first else None, 'selector': first['selector'] if first else None,
                               'open_s': first['open_s'] if first else None, 'load_s': first['load_s'] if first else (loads[0]['load_s'] if loads else None),
                               'after_load_s': first.get('after_load_s') if first else None, 'text': first.get('text') if first else None, 'loads': loads,
                               'method': 'timing pass with navigator.webdriver off (the normal pass keeps it on and is recorded under normal_pass); '
                                         'two loads, cookies and storage cleared between them; seconds from navigation start',
                               'captures': ['captures/popup_before.png'] + (['captures/popup_after.png'] if first else [])})
            bx = next((l['bouncex'] for l in loads if l.get('bouncex')), None)
            if bx:
                r['popup']['wunderkind_campaigns'] = bx
            if first and r['pages'].get('srp'):
                page.evaluate(snippets.CLEAR_STORAGE)
                captures.goto(page, r['pages']['srp'], wait='domcontentloaded')
                res = page.evaluate(snippets.POPUP_POLL, {'selectors': [first['selector']] if not first['selector'].startswith('fixed:') else selectors, 'maxMs': 15000})
                r['popup']['on_srp'] = bool(res['hit'])
                r['popup']['srp_open_s'] = res['popupSec'] if not (first['vendor'] == 'Gubagoo' and res.get('gubagooSec')) else res['gubagooSec']
            ctx.close()
        if not r['popup']['vendor'] and r['popup']['vendors_present']:
            store.not_captured('homepage pop-up timing', f'no overlay opened in {config.POPUP_POLL_MS // 1000} s on the normal pass or the timing pass, though these vendors\' scripts loaded: {", ".join(r["popup"]["vendors_present"])}')
        if r['popup']['vendor'] and not (r['popup']['normal_pass'] or {}).get('vendor'):
            store.results['collector']['notes'].append(f'{r["popup"]["vendor"]} pop-up opened only with the automation flag off; the normal pass (webdriver true) saw nothing')
        store.check('popup', 'ok')
    except Exception as e:
        r['popup']['loads'] = loads
        store.check('popup', 'failed', f'{type(e).__name__}: {str(e)[:200]}')
