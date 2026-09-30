"""PageSpeed on the home page only (Jonathan, Sep 30, 2026: "we do not need to determine page speed on any page outside of
the homepage"): the numbers by the report page (or the API), the pictures from the report page (SPEC.md section 3).

API: https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url=&strategy=mobile|desktop&category=performance&key=
The response's lighthouseResult holds the lab run (categories, audits, the full-page screenshot, the treemap data) and
loadingExperience holds the field data (Chrome UX Report) for the URL; no metrics there means No Data.

Report page: https://pagespeed.web.dev/analysis?url=<page>&form_factor=mobile. Confirmed on a live report, Sep 30,
2026 (Lighthouse 13.5.0): one load runs mobile and desktop together and exposes both results as
window.__LIGHTHOUSE_MOBILE_JSON__ and window.__LIGHTHOUSE_DESKTOP_JSON__ (audits, categories, the treemap nodes, the
full-page render under fullPageScreenshot; no CrUX block and no node label for the LCP element). The gauge block is
the visible #performance .lh-category-header plus its .lh-audit-group--metrics (which carries the "Captured at" meta
rows). The field card is the div that starts "Core Web Vitals Assessment", cropped above "Other notable metrics". The
tabs are #mobile_tab and #desktop_tab; both reports stay in the DOM, the other one hidden, so every read and capture
takes the visible one. View Treemap is button.lh-report-icon--treemap and opens the treemap app in a new page."""
import base64
import io
import re
import time
from urllib.parse import quote

import requests
from PIL import Image, ImageDraw

from . import config, captures, snippets
from .store import now_et, time_et

API = 'https://www.googleapis.com/pagespeedonline/v5/runPagespeed'
POPUP_WORDS = re.compile(r'chat|invite|gubagoo|podium|coupon|popup|pop-up|modal|overlay|bouncex|wunderkind|bx-|dialog', re.I)
RETRY_WORDS = re.compile(r'DEADLINE_EXCEEDED|resource_exhausted|throttled|Unable to resolve|FAILED_DOCUMENT_REQUEST|Something went wrong', re.I)
FIELD_STATUS = {'FAST': 'Passed', 'AVERAGE': 'Failed', 'SLOW': 'Failed'}


# ---- the API ----
def lcp_element_of(audits):
    """The LCP element's node (label, snippet, selector) where the skill reads it: audits['lcp-breakdown-insight']
    .details, whose items hold the subpart table and, when Lighthouse attributed the LCP to an element, a
    {type: "node"} item (Lighthouse 13.5, confirmed Sep 30, 2026 on the Bay Hyundai VDP reports; the home reports
    carried no node). The older largest-contentful-paint-element audit is read the same way when present."""
    for key in ('lcp-breakdown-insight', 'largest-contentful-paint-element', 'lcp-discovery-insight'):
        det = (audits.get(key) or {}).get('details') or {}
        stack = [det]
        while stack:
            x = stack.pop()
            if isinstance(x, dict):
                node = x.get('node') if isinstance(x.get('node'), dict) else (x if x.get('type') == 'node' or x.get('nodeLabel') else None)
                if node and (node.get('nodeLabel') or node.get('snippet')):
                    return {'label': node.get('nodeLabel'), 'snippet': node.get('snippet'), 'selector': node.get('selector'),
                            'boundingRect': node.get('boundingRect'), 'from': f'{key}.details'}
                stack.extend(v for v in x.values() if isinstance(v, (dict, list)))
            elif isinstance(x, list):
                stack.extend(x)
    return None


def lcp_breakdown_of(audits):
    det = (audits.get('lcp-breakdown-insight') or {}).get('details') or {}
    for it in det.get('items') or []:
        rows = it.get('items') if isinstance(it, dict) else None
        if isinstance(rows, list) and rows and isinstance(rows[0], dict) and 'duration' in rows[0]:
            return {r.get('subpart') or r.get('label'): round(r['duration']) for r in rows if isinstance(r.get('duration'), (int, float))}
    return None


def lab_numbers(lhr):
    """Score and the five metrics from a Lighthouse result (the API's or the report page's), as displayed."""
    a = lhr.get('audits') or {}

    def num(k):
        return (a.get(k) or {}).get('numericValue')

    def disp(k):
        d = (a.get(k) or {}).get('displayValue')
        return d.replace(' ', ' ') if isinstance(d, str) else d
    score = ((lhr.get('categories') or {}).get('performance') or {}).get('score')
    lcp_el = lcp_element_of(a)
    # Lighthouse 13.5 (Sep 30, 2026) ships no LCP node in the API or the page: the largest-contentful-paint-element audit
    # is gone and the lcp-breakdown-insight table has no node column. What is left is the discovery checklist, which says
    # whether the LCP is an image request found in the initial HTML; the collector records that and leaves the element
    # itself to be confirmed (its own headless load observes the LCP element separately, see popups.timing).
    lcp_note = None
    disc = ((a.get('lcp-discovery-insight') or {}).get('details') or {}).get('items') or []
    for it in disc:
        chk = it.get('items') if isinstance(it, dict) else None
        if isinstance(chk, dict) and chk:
            parts = [f"{v.get('label')}: {'yes' if v.get('value') else 'no'}" for v in chk.values() if isinstance(v, dict)]
            lcp_note = 'LCP is an image request (lcp-discovery-insight): ' + '; '.join(parts)
            break
    nodes = ((a.get('script-treemap-data') or {}).get('details') or {}).get('nodes') or []
    gtm = [n.get('name') for n in nodes if 'googletagmanager.com' in (n.get('name') or '')]
    fps = (lhr.get('fullPageScreenshot') or {}).get('screenshot') or ((a.get('full-page-screenshot') or {}).get('details') or {}).get('screenshot') or {}
    return {
        'score': None if score is None else round(score * 100),
        'fcp_s': None if num('first-contentful-paint') is None else round(num('first-contentful-paint') / 1000, 1),
        'lcp_s': None if num('largest-contentful-paint') is None else round(num('largest-contentful-paint') / 1000, 1),
        'tbt_ms': None if num('total-blocking-time') is None else round(num('total-blocking-time')),
        'cls': None if num('cumulative-layout-shift') is None else round(num('cumulative-layout-shift'), 3),
        'si_s': None if num('speed-index') is None else round(num('speed-index') / 1000, 1),
        'display': {'fcp': disp('first-contentful-paint'), 'lcp': disp('largest-contentful-paint'), 'tbt': disp('total-blocking-time'),
                    'cls': disp('cumulative-layout-shift'), 'si': disp('speed-index')},
        'lcp_element': lcp_el, 'lcp_element_note': lcp_note if not lcp_el else None,
        'lcp_is_popup': (bool(POPUP_WORDS.search((lcp_el.get('label') or '') + ' ' + (lcp_el.get('snippet') or '') + ' ' + (lcp_el.get('selector') or ''))) if lcp_el else None),
        'lcp_breakdown_ms': lcp_breakdown_of(a),
        'gtm_names': gtm, 'gtm_count': len(gtm), 'scripts_total': len(nodes),
        'full_page_screenshot': {'data': fps.get('data'), 'width': fps.get('width'), 'height': fps.get('height')} if fps.get('data') else None,
        'lighthouse_version': lhr.get('lighthouseVersion'), 'fetch_time': lhr.get('fetchTime'),
        'run_warnings': lhr.get('runWarnings') or [],
    }


def field_of(loading_experience):
    fe = loading_experience or {}
    metrics = fe.get('metrics') or {}

    def fm(k):
        m = metrics.get(k)
        return None if not m else {'percentile': m.get('percentile'), 'category': m.get('category')}
    return {'status': 'No Data' if not metrics else FIELD_STATUS.get(fe.get('overall_category'), fe.get('overall_category')),
            'overall_category': fe.get('overall_category'), 'id': fe.get('id'),
            'lcp': fm('LARGEST_CONTENTFUL_PAINT_MS'), 'inp': fm('INTERACTION_TO_NEXT_PAINT'), 'cls': fm('CUMULATIVE_LAYOUT_SHIFT_SCORE'),
            'fcp': fm('FIRST_CONTENTFUL_PAINT_MS'), 'ttfb': fm('EXPERIMENTAL_TIME_TO_FIRST_BYTE')}


def run_api(url, strategy, store=None):
    """One keyed API run, with the skill's retry: a DEADLINE_EXCEEDED, resource_exhausted or Unable to resolve answer,
    or a read timeout, waits 20 s and tries once more. Returns the parsed numbers plus the raw pieces later steps need."""
    if not config.PSI_API_KEY:
        raise RuntimeError('PSI_API_KEY is empty: the report page supplies the numbers (report_pictures), not the API')
    last = None
    for attempt in (1, 2):
        t0 = time.time()
        try:
            r = requests.get(API, params={'url': url, 'strategy': strategy, 'category': 'performance', 'key': config.PSI_API_KEY},
                             timeout=(20, config.PSI_API_TIMEOUT_S))
            j = r.json()
        except (requests.RequestException, ValueError) as e:   # the message is never kept: it can carry the request URL and its key
            last = f'{type(e).__name__} after {round(time.time() - t0)} s'
            j = None
        if j is not None and 'error' in j:
            msg = (j['error'].get('message') or str(j['error']))[:300]
            last = f'API error {j["error"].get("code")}: {msg}'
            if not RETRY_WORDS.search(msg) and r.status_code < 500:
                raise RuntimeError(last)
        elif j is not None and 'lighthouseResult' in j:
            lhr = j['lighthouseResult']
            out = {'source': 'api', 'at': now_et(), 'strategy': strategy, 'url': url, 'seconds': round(time.time() - t0),
                   'final_url': lhr.get('finalDisplayedUrl') or lhr.get('finalUrl'), **lab_numbers(lhr),
                   'field': field_of(j.get('loadingExperience')), 'origin_field': field_of(j.get('originLoadingExperience'))}
            return out
        if attempt == 1:
            if store:
                store.log(f'PageSpeed API {strategy} on {url}: {last}; waiting 20 s and trying once more')
            time.sleep(20)
    raise RuntimeError(f'PageSpeed API {strategy} failed twice: {last}')


def api_with_rerun(store, url, strategy):
    """The skill's LCP rule: when the LCP element is a pop-up's image, run again and keep both runs."""
    runs = [run_api(url, strategy, store)]
    if runs[0]['lcp_is_popup']:   # None means the run named no LCP element, so there is nothing to rerun for
        store.log(f'PageSpeed API {strategy} LCP is a pop-up element ({runs[0]["lcp_element"]}), rerunning once')
        time.sleep(5)
        runs.append(run_api(url, strategy, store))
    main = next((r for r in runs if not r['lcp_is_popup']), runs[-1])
    return main, runs


# ---- the report page (pictures, and the numbers when there is no key) ----
REPORT_URL = 'https://pagespeed.web.dev/analysis?url={url}&form_factor={ff}'
SEL_METRICS = '.lh-audit-group--metrics'
SEL_TREEMAP_BTN = 'button.lh-report-icon--treemap'
TAB = {'mobile': '#mobile_tab', 'desktop': '#desktop_tab'}
ERROR_WORDS = re.compile(r'Something went wrong|Unable to resolve|failed to retrieve|Lighthouse returned error|DEADLINE_EXCEEDED|resource_exhausted|'
                         r'render server throttled|FAILED_DOCUMENT_REQUEST|could not load', re.I)

# The visible report's boxes, in the screenshot frame (device scale 1, after the document zoom is set): the gauge block
# (category header plus the metrics group), the field card cut above "Other notable metrics", and the card's text.
REPORT_BOXES = """() => {
  const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const box = e => { const r = e.getBoundingClientRect(); return { x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height }; };
  const union = (a, b) => { const x = Math.min(a.x, b.x), y = Math.min(a.y, b.y); return { x, y, w: Math.max(a.x + a.w, b.x + b.w) - x, h: Math.max(a.y + a.h, b.y + b.h) - y }; };
  const cat = [...document.querySelectorAll('#performance.lh-category, .lh-category#performance')].find(vis);
  const header = cat && cat.querySelector('.lh-category-header');
  const metrics = cat && [...cat.querySelectorAll('.lh-audit-group--metrics')].find(vis);
  const gauge = header && metrics ? union(box(header), box(metrics)) : null;
  const all = [...document.querySelectorAll('body div')].filter(vis);
  const has = (e, s) => (e.textContent || '').includes(s);
  const area = e => { const r = e.getBoundingClientRect(); return r.width * r.height; };
  const cards = all.filter(e => has(e, 'Core Web Vitals Assessment') && (has(e, 'Latest 28-day period') || /No Data|sufficient real-world/i.test(e.textContent || ''))).sort((a, b) => area(a) - area(b));
  const card = cards[0] || null;
  let field = null, fieldText = null;
  if (card) {
    const cb = box(card);
    const other = [...card.querySelectorAll('*')].filter(e => vis(e) && /^other notable metrics$/i.test((e.textContent || '').trim())).sort((a, b) => area(a) - area(b))[0];
    const cut = other ? box(other).y - 14 : cb.y + cb.h;
    field = { x: cb.x, y: cb.y, w: cb.w, h: Math.max(60, cut - cb.y) };
    fieldText = (card.innerText || '').replace(/\\u00a0/g, ' ').trim();
  }
  const treemap = [...document.querySelectorAll('button.lh-report-icon--treemap')].find(vis);
  return { gauge, field, fieldText, treemap: treemap ? box(treemap) : null, scrollY, innerWidth, innerHeight };
}"""

HIDE_COOKIE_BAR = """() => { for (const e of document.querySelectorAll('body *')) { if (e.children.length < 6 && /Ok, Got it\\./.test(e.textContent || '')) {
  let p = e; for (let i = 0; i < 8 && p && p !== document.body; i++) { if (getComputedStyle(p).position === 'fixed') { p.style.display = 'none'; return true; } p = p.parentElement; } } } return false; }"""

PAGE_LHR = """(ff) => { const l = ff === 'desktop' ? window.__LIGHTHOUSE_DESKTOP_JSON__ : window.__LIGHTHOUSE_MOBILE_JSON__; if (!l || !l.audits) return null;
  const a = l.audits, pick = {}; for (const k of ['first-contentful-paint','largest-contentful-paint','total-blocking-time','cumulative-layout-shift','speed-index','largest-contentful-paint-element','lcp-breakdown-insight','lcp-discovery-insight','script-treemap-data']) if (a[k]) pick[k] = a[k];
  return { audits: pick, categories: l.categories, fullPageScreenshot: l.fullPageScreenshot, lighthouseVersion: l.lighthouseVersion, fetchTime: l.fetchTime, runWarnings: l.runWarnings, finalDisplayedUrl: l.finalDisplayedUrl || l.finalUrl, requestedUrl: l.requestedUrl }; }"""


def parse_field_text(text):
    """The field card's words into the capture brief's field block: status, and each metric's display value."""
    if not text:
        return None
    m = re.search(r'Core Web Vitals Assessment:\s*(Passed|Failed|No Data|N/A)', text, re.I)
    status = m.group(1) if m else ('No Data' if re.search(r'No Data|sufficient real-world', text, re.I) else None)
    out = {'status': status, 'source': 'report page card'}
    for key, label in (('lcp', 'Largest Contentful Paint'), ('inp', 'Interaction to Next Paint'), ('cls', 'Cumulative Layout Shift'),
                       ('fcp', 'First Contentful Paint'), ('ttfb', 'Time to First Byte')):
        mm = re.search(re.escape(label) + r' \([A-Z]+\)\s*\n?\s*([\d.,]+\s?(?:s|ms)?)', text)
        out[key] = mm.group(1).strip() if mm else None
    mm = re.search(r'(Latest 28-day period)', text)
    out['period'] = mm.group(1) if mm else None
    return out


def visible_box(page, js_key):
    b = page.evaluate(REPORT_BOXES)
    return b.get(js_key), b


STICKY_BAR_PX = 170   # the report page's sticky Mobile/Desktop tab bar (about 130 px at zoom 1.15) plus room


def clip_shot(store, page, name, box, pad=8):
    """Capture a page-coordinate box at scale 1: scroll it into the frame below the sticky tab bar, then clip in
    viewport coordinates. A block taller than the frame is captured from its top."""
    vh = config.VIEWPORT['height']
    y0 = max(0, box['y'] - pad - STICKY_BAR_PX)
    page.evaluate('(y) => window.scrollTo(0, y)', y0)
    page.wait_for_timeout(250)
    sy = page.evaluate('() => window.scrollY')
    top = box['y'] - pad - sy
    clip = {'x': max(0, box['x'] - pad), 'y': max(0, top), 'width': box['w'] + 2 * pad, 'height': max(1, min(box['h'] + 2 * pad, vh - max(0, top)))}
    page.evaluate(snippets.HIDE, config.HIDE_BEFORE_CAPTURE)
    page.evaluate(HIDE_COOKIE_BAR)
    page.mouse.move(config.VIEWPORT['width'] - 1, config.VIEWPORT['height'] // 2)
    path = store.captures / name
    page.screenshot(path=str(path), clip=clip, type='png')
    size = Image.open(path).size
    store.record_capture(name, page.url, size)
    store.log(f'captured {name} {size[0]}x{size[1]}')
    return path


def wait_for_report(page, timeout_s, ff='mobile'):
    """Wait for the report for one form factor to render (its Lighthouse result on window and its metrics group
    visible) or for the page to say it failed; raise with the page's words on failure. Mobile and desktop run together
    on one load, but the desktop result can land a minute after the mobile one."""
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        page.wait_for_timeout(1000)
        st = page.evaluate("""(ff) => { const vis = e => e.getBoundingClientRect().height > 0;
            const cat = [...document.querySelectorAll('#performance')].find(vis);
            const m = cat && [...cat.querySelectorAll('.lh-audit-group--metrics')].find(vis);
            const lhr = ff === 'desktop' ? window.__LIGHTHOUSE_DESKTOP_JSON__ : window.__LIGHTHOUSE_MOBILE_JSON__;
            const t = (document.body.innerText || '').slice(0, 3000); return { ready: !!m && !!(lhr && lhr.audits), text: t }; }""", ff)
        if st['ready']:
            return round(time.time() - t0)
        m = ERROR_WORDS.search(st['text'])
        if m and time.time() - t0 > 15:
            raise RuntimeError(f'the report page says "{m.group(0)}"')
    raise RuntimeError(f'the {ff} report did not render within {timeout_s} s')


def open_report(store, page, url, which, report_url=None):
    """Open a fresh analysis (or a saved report by its URL) and wait for the mobile report. The skill's retry: when
    the page says it failed ("Something went wrong", DEADLINE_EXCEEDED, throttled, Unable to resolve), wait 20 s and
    run it once more."""
    last = None
    for attempt in (1, 2):
        try:
            captures.goto(page, report_url or REPORT_URL.format(url=quote(url, safe=''), ff='mobile'), wait='domcontentloaded')
            return wait_for_report(page, config.PSI_REPORT_TIMEOUT_S)
        except Exception as e:
            last = e
            if attempt == 1:
                store.log(f'PageSpeed report for {which}: {type(e).__name__}: {str(e)[:160]}; waiting 20 s and running it again')
                time.sleep(20)
    raise last


def report_pictures(store, page, url, which, report_url=None, sides=('mobile', 'desktop')):
    """Open the report page headless (or a saved report by its URL), wait for it, and for mobile then desktop read the
    page's own Lighthouse result and the field card, and capture the gauge block and the field card at page zoom 1.15
    with the mouse parked off the report. Any failure is recorded and left to Chrome; the audit never waits."""
    out = {'report_url': report_url, 'captures': {}, 'numbers': {}, 'field': {}, 'seconds': None, 'at': now_et()}
    t0 = time.time()
    try:
        waited = open_report(store, page, url, which, report_url)
        out['report_url'] = page.url
        store.log(f'PageSpeed report for {which} rendered after {waited} s: {page.url}')
        page.wait_for_timeout(2500)
        page.evaluate(HIDE_COOKIE_BAR)
        for ff in sides:
            try:
                if ff == 'desktop':
                    page.click(TAB[ff])
                    waited = wait_for_report(page, config.PSI_REPORT_TIMEOUT_S, 'desktop')
                    if waited > 3:
                        store.log(f'PageSpeed desktop report for {which} rendered {waited} s after the tab click')
                    page.wait_for_timeout(1500)
                lhr = page.evaluate(PAGE_LHR, ff)
                if lhr:
                    nums = lab_numbers(lhr)
                    nums.update({'source': 'report', 'at': now_et(), 'strategy': ff, 'url': url, 'report_url': page.url.split('?')[0] + f'?form_factor={ff}',
                                 'final_url': lhr.get('finalDisplayedUrl')})
                    out['numbers'][ff] = nums
                page.evaluate(snippets.ZOOM, config.PSI_ZOOM)
                page.wait_for_timeout(500)
                boxes = page.evaluate(REPORT_BOXES)
                if boxes.get('fieldText'):
                    out['field'][ff] = parse_field_text(boxes['fieldText'])
                    if out['numbers'].get(ff) is not None:
                        out['numbers'][ff]['field'] = out['field'][ff]
                if boxes.get('gauge'):
                    clip_shot(store, page, f'psi_{which}_{ff}_gauges.png', boxes['gauge'])
                    out['captures'][f'{ff}_gauges'] = f'psi_{which}_{ff}_gauges.png'
                else:
                    store.not_captured(f'psi_{which}_{ff}_gauges.png', 'no visible performance category on the report page')
                if boxes.get('field'):
                    clip_shot(store, page, f'psi_{which}_{ff}_field.png', boxes['field'])
                    out['captures'][f'{ff}_field'] = f'psi_{which}_{ff}_field.png'
                else:
                    store.not_captured(f'psi_{which}_{ff}_field.png', 'no field data card found on the report page')
            except Exception as e:   # one side's failure (PageSpeed's own "Something went wrong" on the desktop run) leaves the other side's evidence in place
                store.not_captured(f'PageSpeed report {ff} for {which}', f'{type(e).__name__}: {str(e)[:300]}')
            finally:
                page.evaluate(snippets.ZOOM, 1)
                page.wait_for_timeout(300)
        # back to the mobile report, which is where View Treemap is clicked
        try:
            page.click(TAB['mobile'])
            wait_for_report(page, 30, 'mobile')
        except Exception as e:
            store.log(f'could not return to the mobile report: {type(e).__name__}')
    except Exception as e:
        store.not_captured(f'PageSpeed report pictures for {which}', f'{type(e).__name__}: {str(e)[:300]}')
    out['seconds'] = round(time.time() - t0)
    return out


def treemap_picture(store, page, name='treemap_home.png', report_url=None):
    """A real click on View Treemap (the visible one) opens the treemap app in a new page; count the GTM nodes there
    (the skill's snippet) and screenshot it. When no rendered report is showing (a rerun that PageSpeed failed), the
    saved report is reopened by its URL first; a saved report loads in a few seconds."""
    try:
        btn = page.locator(SEL_TREEMAP_BTN + ':visible').first
        if btn.count() == 0 and report_url:
            store.log(f'no report showing; reopening the saved report {report_url}')
            captures.goto(page, report_url.split('?')[0] + '?form_factor=mobile', wait='domcontentloaded')
            wait_for_report(page, 60, 'mobile')
            page.wait_for_timeout(1500)
            page.evaluate(HIDE_COOKIE_BAR)
            btn = page.locator(SEL_TREEMAP_BTN + ':visible').first
        btn.scroll_into_view_if_needed()
        with page.context.expect_page(timeout=20000) as new_page:
            btn.click()
        tm = new_page.value
        tm.wait_for_load_state('load', timeout=config.PSI_REPORT_TIMEOUT_S * 1000)
        tm.wait_for_function('() => window.__treemapOptions && document.querySelector(".lh-treemap, .webtreemap-node, canvas, svg")', timeout=30000)
        tm.wait_for_timeout(3000)
        counts = tm.evaluate(snippets.TREEMAP_GTM)
        counts['at'] = now_et()
        counts['url'] = tm.url
        tm.mouse.move(config.VIEWPORT['width'] - 1, config.VIEWPORT['height'] - 1)
        path = store.captures / name
        tm.screenshot(path=str(path), type='png')
        store.record_capture(name, tm.url, Image.open(path).size)
        store.log(f'captured {name}; {counts["count"]} googletagmanager.com scripts of {counts["total"]} in the treemap')
        tm.close()
        return counts
    except Exception as e:
        store.not_captured(name, f'{type(e).__name__}: {str(e)[:300]}')
        return None


def note_missing_lcp(store, run, which, ff):
    """The skill checks what the LCP is before quoting a load time; a run with no node goes to Chrome for that."""
    if not run or run.get('lcp_element'):
        return
    seen = (store.results.get('popup') or {}).get('lcp_observed') or {}
    own = f'; the collector\'s own headless load painted {seen.get("tag", "").lower()} {seen.get("src") or seen.get("text") or ""} largest at {seen.get("t")} ms'.rstrip() if seen else ''
    store.not_captured(f'LCP element, {which} {ff}', f'the {run.get("source", "")} run\'s lcp-breakdown-insight carried no node, so what the {run.get("lcp_s")} s LCP is (page content or a pop-up\'s image) '
                                                        f'is unread; confirm in Chrome before quoting the load time{own}')


def compare_runs(api, report):
    """SPEC section 3.3: a score more than 5 apart or an LCP more than 1 s apart between the API and the report."""
    if not api or not report:
        return None
    notes = []
    if api.get('score') is not None and report.get('score') is not None and abs(api['score'] - report['score']) > 5:
        notes.append(f'score api {api["score"]} vs report {report["score"]}')
    if api.get('lcp_s') is not None and report.get('lcp_s') is not None and abs(api['lcp_s'] - report['lcp_s']) > 1:
        notes.append(f'LCP api {api["lcp_s"]} s vs report {report["lcp_s"]} s')
    return notes


def home(store, rp, url):
    """PageSpeed on the home page. The report page first: its pictures and its own numbers are what the skill quotes
    (Jonathan, Sep 30, 2026). The API runs only for a side the report page did not give, since it adds nothing the deck
    needs beyond that. Then the treemap. Writes store.results['pagespeed'] and ['gtm'] and marks the checks."""
    r = store.results
    for ff in ('mobile', 'desktop'):
        r['pagespeed'][f'home_{ff}'] = {'api': None, 'report': None, 'report_url': None, 'runs': [], 'lcp_is_popup': None, 'captures': {}}
    pics = report_pictures(store, rp, url, 'home')
    # a run that warns (runWarnings, such as "The page loaded too slowly to finish within the time limit") runs once
    # more; every run stays in runs[] marked had_warning, and the quoted run is one without a warning when there is one
    warned = [ff for ff in ('mobile', 'desktop') if (pics['numbers'].get(ff) or {}).get('run_warnings')]
    earlier = {}
    if warned:
        store.log(f'PageSpeed home report warned on {", ".join(warned)} ({(pics["numbers"][warned[0]]["run_warnings"] or [""])[0][:80]}); running the report once more')
        earlier = {ff: n for ff, n in pics['numbers'].items()}
        pics2 = report_pictures(store, rp, url, 'home')
        extra = {}
        if pics2['numbers']:
            for ff in ('mobile', 'desktop'):
                a, b = earlier.get(ff), pics2['numbers'].get(ff)
                if b and (not b.get('run_warnings') or not a):
                    pics['numbers'][ff] = b
                    pics['captures'] = {**pics['captures'], **{k: v for k, v in pics2['captures'].items() if k.startswith(ff)}}
                elif b:
                    extra[ff] = b   # the rerun warned too: kept in runs[], the first run stays the quoted one
            pics['report_url'] = pics2.get('report_url') or pics['report_url']
    api = {}
    for ff in ('mobile', 'desktop'):
        rec = r['pagespeed'][f'home_{ff}']
        rec['report'] = pics['numbers'].get(ff)
        if earlier.get(ff) and earlier[ff] is not rec['report']:
            earlier[ff]['had_warning'] = bool(earlier[ff].get('run_warnings'))
            rec['runs'].append(earlier[ff])
        if extra.get(ff):
            extra[ff]['had_warning'] = True
            rec['runs'].append(extra[ff])
        if rec['report'] is not None:
            rec['report']['had_warning'] = bool(rec['report'].get('run_warnings'))
        rec['report_url'] = (rec['report'] or {}).get('report_url') or pics.get('report_url')
        rec['captures'] = {k.split('_', 1)[1]: f'captures/{v}' for k, v in pics['captures'].items() if k.startswith(ff)}
        if rec['report']:
            rec['runs'].append(rec['report'])
            rec['lcp_is_popup'] = rec['report']['lcp_is_popup']
            rec['source'] = 'report page'
            store.check(f'pagespeed_home_{ff}', 'ok')
        elif config.PSI_API_KEY:
            try:
                main, runs = api_with_rerun(store, url, ff)
                api[ff] = main
                rec.update({'api': main, 'runs': rec['runs'] + list(runs), 'lcp_is_popup': main['lcp_is_popup'], 'source': 'API (the report page gave no numbers for this side)'})
                store.log(f'PageSpeed API home {ff} (report page fallback): score {main["score"]}, LCP {main["lcp_s"]} s, field {main["field"]["status"]}, {main["seconds"]} s')
                store.check(f'pagespeed_home_{ff}', 'ok')
            except Exception as e:
                store.check(f'pagespeed_home_{ff}', 'failed', f'report page gave no numbers and the API failed: {type(e).__name__}: {str(e)[:200]}')
        else:
            store.check(f'pagespeed_home_{ff}', 'failed', 'no key and the report page gave no numbers; PageSpeed goes to Chrome')
        store.save()
    for ff in ('mobile', 'desktop'):
        rec = r['pagespeed'][f'home_{ff}']
        note_missing_lcp(store, rec.get('report') or rec.get('api'), 'home', ff)
    # the treemap and the GTM count
    src = pics['numbers'].get('mobile') or api.get('mobile') or pics['numbers'].get('desktop') or api.get('desktop')
    if src:
        r['gtm'] = {'count': src['gtm_count'], 'names': src['gtm_names'], 'scripts_total': src['scripts_total'],
                    'source': f'{src["source"]} script-treemap-data, {src["strategy"]} home run at {src["at"]}', 'capture': None}
    if pics.get('report_url'):
        tm = treemap_picture(store, rp, report_url=pics['report_url'])
        if tm:
            if r['gtm']:
                r['gtm']['capture'] = 'captures/treemap_home.png'
                r['gtm']['count_treemap_tab'] = tm['count']
                if tm['count'] != r['gtm']['count']:
                    store.noticed(f'GTM count differs: {r["gtm"]["count"]} in the {src["source"]} run, {tm["count"]} in the treemap tab', 'captures/treemap_home.png')
            else:
                r['gtm'] = {'count': tm['count'], 'names': tm['names'], 'scripts_total': tm['total'], 'source': 'treemap tab', 'capture': 'captures/treemap_home.png'}
    store.check('gtm', 'ok' if r['gtm'] else 'failed', None if r['gtm'] else 'no treemap data from the report page or the API')
    store.save()


def phone_screens(store, fps=None, image_path=None, scale=1.25, outline=(255, 45, 85), border=4, prefix='vdp_phone'):
    """Cut a phone-width full-page render (412 px wide: the collector's own, or a PageSpeed webp data URL) into 412 x 823
    phone screens with the 4 px #FF2D55 outline, saved at 1.25 scale to match the decks so far (about 505 x 997 px
    each). Returns the file names."""
    if image_path:
        im = Image.open(image_path).convert('RGB')
    elif fps and fps.get('data'):
        raw = base64.b64decode(fps['data'].split(',', 1)[1])
        im = Image.open(io.BytesIO(raw)).convert('RGB')
    else:
        return []
    if im.size[0] != 412:
        im = im.resize((412, round(im.size[1] * 412 / im.size[0])))
    names = []
    for i in range(4):
        y0 = i * 823
        if y0 >= im.size[1]:
            break
        screen = Image.new('RGB', (412, 823), 'white')
        screen.paste(im.crop((0, y0, 412, min(y0 + 823, im.size[1]))), (0, 0))
        ImageDraw.Draw(screen).rectangle((0, 0, 411, 822), outline=outline, width=border)
        screen = screen.resize((round(412 * scale), round(823 * scale)), Image.LANCZOS)
        name = f'{prefix}_{i + 1}.png'
        screen.save(store.captures / name)
        store.record_capture(name, store.results['pages'].get('vdp'), screen.size)
        names.append(name)
    return names
