"""The platform test (Decision 7, SPEC.md section 7): one live store per platform, plus pagespeed.web.dev and
bing.com/maps, opened headless the way the collector opens every page. Writes platforms.json: per platform, headless
"ok" or "chrome_only", with the evidence (status, title, whether the main content rendered, any challenge page text).
The store list comes from platforms.test.json beside this package; the VM build fills it with one store per platform
(from the census, or from the Dealer Audit Requests archive), never a store that is in progress on the sheet."""
import json
import re
import time
from pathlib import Path

from . import captures, config

CHALLENGE = re.compile(r'access denied|attention required|cloudflare|incapsula|captcha|verify you are human|request blocked|forbidden|bot detection|pardon our interruption', re.I)
TEST_FILE = Path(__file__).resolve().parent.parent / 'platforms.test.json'
OUT_FILE = Path(__file__).resolve().parent.parent / 'platforms.json'

DEFAULT_TESTS = {
    'Dealer.com': None, 'DealerOn': None, 'Dealer Inspire': None, 'Sincro': None,
    'pagespeed.web.dev': 'https://pagespeed.web.dev/analysis?url=https%3A%2F%2Fwww.google.com&form_factor=mobile',
    'bing.com/maps': 'https://www.bing.com/maps?q=Panama%20City%20FL',
}


def run():
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
            rec = {'url': url, 'status': None, 'title': None, 'main_content': None, 'challenge': None, 'seconds': None}
            try:
                resp = captures.goto(page, url, wait='domcontentloaded')
                page.wait_for_timeout(4000)
                rec['status'] = resp.status if resp else None
                rec['title'] = (page.title() or '')[:120]
                text = page.evaluate('() => document.body.innerText.slice(0, 4000)')
                m = CHALLENGE.search(text + ' ' + rec['title'])
                rec['challenge'] = m.group(0) if m else None
                rec['main_content'] = bool(page.query_selector('nav a, header a')) and (bool(page.query_selector('img')) or 'pagespeed' in url)
                rec['headless'] = 'chrome_only' if (rec['challenge'] or (rec['status'] and rec['status'] >= 400) or not rec['main_content']) else 'ok'
            except Exception as e:
                rec['headless'] = 'chrome_only'
                rec['error'] = f'{type(e).__name__}: {e}'
            rec['seconds'] = round(time.time() - t0, 1)
            results[platform] = rec
            print(f'{platform}: {rec["headless"]}  status {rec["status"]}  title "{rec["title"]}"  challenge {rec["challenge"]}  {rec["seconds"]} s')
            ctx.close()
    OUT_FILE.write_text(json.dumps(results, indent=1))
    print('wrote', OUT_FILE)
    return results


def load():
    return json.loads(OUT_FILE.read_text()) if OUT_FILE.exists() else {}
