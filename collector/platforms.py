"""The platform test (Decision 7, SPEC.md section 7): one live store per platform, plus pagespeed.web.dev and
bing.com/maps, opened headless the way the collector opens every page. Writes platforms.json: per platform, headless
"ok" or "chrome_only", with the evidence (status, title, whether the main content rendered, any challenge page text,
the platform the pre-flight's markers detect, the time to load).
The store list comes from platforms.test.json beside this package; the VM build fills it with one store per platform
(from the census, or from the Dealer Audit Requests archive), never a store that is in progress on the sheet."""
import json
import re
import time
from pathlib import Path

from . import captures, config

# What a firewall or challenge page says. "forbidden" alone is not here: a normal page can carry the word.
CHALLENGE = re.compile(r'access denied|attention required|checking your browser|cloudflare|incapsula|captcha|verify you are human|'
                       r'request blocked|you don\'t have permission|bot detection|pardon our interruption|errors\.edgesuite\.net', re.I)
TEST_FILE = Path(__file__).resolve().parent.parent / 'platforms.test.json'
OUT_FILE = Path(__file__).resolve().parent.parent / 'platforms.json'

DEFAULT_TESTS = {
    'Dealer.com': None, 'DealerOn': None, 'Dealer Inspire': None, 'Sincro': None,
    'pagespeed.web.dev': 'https://pagespeed.web.dev/analysis?url=https%3A%2F%2Fwww.google.com&form_factor=mobile',
    'bing.com/maps': 'https://www.bing.com/maps?q=Panama%20City%20FL',
}

# What "the main content rendered" means for a dealer home page: a menu (a run of links, not always inside a nav
# element: Sincro sites have none) and a vehicle or model card (an image beside a price or a model name), or failing
# that a page with real text and images. A challenge page has none of these.
MAIN_CONTENT = """() => {
  const links = [...document.querySelectorAll('a[href]')].filter(a => a.offsetWidth || a.offsetHeight);
  const menuHost = document.querySelector('nav, [role="navigation"], header, [class*="nav"], [id*="nav"], [class*="menu"]');
  const menuLinks = menuHost ? menuHost.querySelectorAll('a[href]').length : 0;
  const money = /\\$\\s?\\d[\\d,]{2,}/;
  const cards = [...document.querySelectorAll('li, article, div')].filter(e => e.children.length && e.children.length < 30 && e.querySelector('img') && money.test(e.innerText || '')).length;
  const modelWords = /(new|used|pre-owned|certified)\\s+(inventory|vehicles|cars|trucks|suvs)/i;
  return { links: links.length, menu_links: menuLinks, images: document.images.length, vehicle_cards: cards,
           text_chars: (document.body.innerText || '').trim().length, inventory_words: modelWords.test(document.body.innerText || '') };
}"""


def judge(rec, url):
    """ok when the page came back without a challenge and its content rendered; chrome_only otherwise."""
    if rec.get('challenge') or (rec.get('status') and rec['status'] >= 400) or rec.get('error'):
        return 'chrome_only'
    c = rec.get('content') or {}
    if 'pagespeed' in url or 'bing.com' in url:
        return 'ok' if c.get('text_chars', 0) > 200 else 'chrome_only'
    menu = c.get('menu_links', 0) >= 8 or c.get('links', 0) >= 20
    body = c.get('images', 0) >= 3 and c.get('text_chars', 0) >= 500
    return 'ok' if (menu and body) else 'chrome_only'


def run():
    from . import preflight
    tests = json.loads(TEST_FILE.read_text()) if TEST_FILE.exists() else DEFAULT_TESTS
    results = {}
    with captures.Browser() as b:
        for platform, url in tests.items():
            if not url:
                results[platform] = {'headless': 'untested', 'note': 'no test store named in platforms.test.json'}
                print(f'{platform}: untested (name a store in platforms.test.json)')
                continue
            ctx = b.context()
            page = ctx.new_page()
            t0 = time.time()
            rec = {'url': url, 'status': None, 'title': None, 'main_content': None, 'content': None, 'challenge': None,
                   'detected_platform': None, 'seconds_to_dom': None, 'seconds': None, 'browser': b.browser.version, 'tested_at': None}
            try:
                resp = captures.goto(page, url, wait='domcontentloaded')
                rec['seconds_to_dom'] = round(time.time() - t0, 1)
                page.wait_for_timeout(4000)
                rec['status'] = resp.status if resp else None
                rec['title'] = (page.title() or '')[:120]
                text = page.evaluate('() => document.body.innerText.slice(0, 4000)')
                m = CHALLENGE.search(text + ' ' + rec['title'])
                rec['challenge'] = m.group(0) if m else None
                rec['content'] = page.evaluate(MAIN_CONTENT)
                if 'pagespeed' not in url and 'bing.com' not in url:
                    rec['detected_platform'] = preflight.detect_platform(page)
            except Exception as e:
                rec['error'] = f'{type(e).__name__}: {str(e)[:200]}'
            rec['headless'] = judge(rec, url)
            c = rec.get('content') or {}
            rec['main_content'] = rec['headless'] == 'ok'
            rec['seconds'] = round(time.time() - t0, 1)
            from .store import now_et
            rec['tested_at'] = now_et()
            results[platform] = rec
            print(f'{platform}: {rec["headless"]}  status {rec["status"]}  title "{rec["title"]}"  challenge {rec["challenge"]}  '
                  f'detected {rec["detected_platform"]}  menu {c.get("menu_links")} links {c.get("links")} imgs {c.get("images")} cards {c.get("vehicle_cards")}  '
                  f'{rec["seconds_to_dom"]} s to DOM, {rec["seconds"]} s total' + (f'  error {rec["error"]}' if rec.get('error') else ''))
            ctx.close()
    OUT_FILE.write_text(json.dumps(results, indent=1))
    print('wrote', OUT_FILE)
    return results


def load():
    return json.loads(OUT_FILE.read_text()) if OUT_FILE.exists() else {}
