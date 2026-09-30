"""PageSpeed: the numbers by the PageSpeed Insights API, the pictures from the report page (SPEC.md section 3).

API: https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url=&strategy=mobile|desktop&category=performance&key=
The response's lighthouseResult holds the lab run (categories, audits, full-page screenshot, treemap data) and
loadingExperience holds the field data (Chrome UX Report) for the URL; no metrics there means No Data.
Report page: https://pagespeed.web.dev/analysis?url=<page>&form_factor=mobile, captured the way the skill describes.
The report page's selectors below are the VM build's first thing to confirm against a live report."""
import base64
import io
import re
import time
from urllib.parse import quote

import requests
from PIL import Image

from . import config, captures, snippets
from .store import time_et

API = 'https://www.googleapis.com/pagespeedonline/v5/runPagespeed'
POPUP_WORDS = re.compile(r'chat|invite|gubagoo|podium|coupon|popup|pop-up|modal|overlay|bouncex|wunderkind', re.I)


def run_api(url, strategy):
    """One keyed API run. Returns the parsed numbers plus the raw pieces later steps need."""
    if not config.PSI_API_KEY:
        raise RuntimeError('PSI_API_KEY is empty: the report page supplies the numbers (report_pictures), not the API')
    r = requests.get(API, params={'url': url, 'strategy': strategy, 'category': 'performance', 'key': config.PSI_API_KEY},
                     timeout=config.PSI_TIMEOUT / 1000)
    r.raise_for_status()
    j = r.json()
    lhr = j.get('lighthouseResult', {})
    a = lhr.get('audits', {})

    def num(k):
        v = a.get(k, {}).get('numericValue')
        return None if v is None else v

    def disp(k):
        return a.get(k, {}).get('displayValue')

    lcp_el = None
    items = a.get('largest-contentful-paint-element', {}).get('details', {}).get('items', [])
    for it in items:
        for sub in it.get('items', [it]):
            node = sub.get('node') if isinstance(sub, dict) else None
            if node:
                lcp_el = {'label': node.get('nodeLabel'), 'snippet': node.get('snippet'), 'selector': node.get('selector')}
                break
        if lcp_el:
            break
    fe = j.get('loadingExperience', {})
    metrics = fe.get('metrics') or {}

    def fm(k):
        m = metrics.get(k)
        return None if not m else {'percentile': m.get('percentile'), 'category': m.get('category')}
    field = {'status': ('No Data' if not metrics else {'FAST': 'Passed', 'AVERAGE': 'Failed', 'SLOW': 'Failed'}.get(fe.get('overall_category'), fe.get('overall_category'))),
             'overall_category': fe.get('overall_category'),
             'lcp': fm('LARGEST_CONTENTFUL_PAINT_MS'), 'inp': fm('INTERACTION_TO_NEXT_PAINT'), 'cls': fm('CUMULATIVE_LAYOUT_SHIFT_SCORE'),
             'fcp': fm('FIRST_CONTENTFUL_PAINT_MS'), 'ttfb': fm('EXPERIMENTAL_TIME_TO_FIRST_BYTE')}
    score = lhr.get('categories', {}).get('performance', {}).get('score')
    nodes = a.get('script-treemap-data', {}).get('details', {}).get('nodes', []) or []
    gtm = [n.get('name') for n in nodes if 'googletagmanager.com' in (n.get('name') or '')]
    fps = a.get('full-page-screenshot', {}).get('details', {}).get('screenshot', {})
    return {
        'source': 'api', 'at': time_et(), 'strategy': strategy, 'url': url,
        'score': None if score is None else round(score * 100),
        'fcp_s': None if num('first-contentful-paint') is None else round(num('first-contentful-paint') / 1000, 1),
        'lcp_s': None if num('largest-contentful-paint') is None else round(num('largest-contentful-paint') / 1000, 1),
        'tbt_ms': None if num('total-blocking-time') is None else round(num('total-blocking-time')),
        'cls': None if num('cumulative-layout-shift') is None else round(num('cumulative-layout-shift'), 3),
        'si_s': None if num('speed-index') is None else round(num('speed-index') / 1000, 1),
        'display': {k: disp(k) for k in ('first-contentful-paint', 'largest-contentful-paint', 'total-blocking-time', 'cumulative-layout-shift', 'speed-index')},
        'lcp_element': lcp_el, 'lcp_is_popup': bool(lcp_el and POPUP_WORDS.search((lcp_el.get('label') or '') + ' ' + (lcp_el.get('snippet') or ''))),
        'field': field, 'gtm_names': gtm, 'gtm_count': len(gtm), 'scripts_total': len(nodes),
        'full_page_screenshot': {'data': fps.get('data'), 'width': fps.get('width'), 'height': fps.get('height')} if fps else None,
        'lighthouse_version': lhr.get('lighthouseVersion'), 'fetch_time': lhr.get('fetchTime'),
    }


def api_with_rerun(store, url, strategy):
    """The skill's LCP rule: when the LCP element is a pop-up's image, run again and keep both runs."""
    runs = [run_api(url, strategy)]
    if runs[0]['lcp_is_popup']:
        store.log(f'PageSpeed {strategy} LCP is a pop-up element ({runs[0]["lcp_element"]}), rerunning once')
        time.sleep(5)
        runs.append(run_api(url, strategy))
    main = next((r for r in runs if not r['lcp_is_popup']), runs[-1])
    return main, runs


# ---- the report page (pictures) ----
REPORT_URL = 'https://pagespeed.web.dev/analysis?url={url}&form_factor={ff}'
# Selectors to confirm on a live report (the VM build's first PageSpeed job): the gauge block with METRICS, the field
# data card, the View Treemap button, and the form-factor tabs.
SEL_GAUGE_BLOCK = '.lh-category .lh-gauge__wrapper, .lh-scores-container'
SEL_METRICS = '.lh-audit-group--metrics'
SEL_FIELD_CARD = '[data-testid="field-data"], .field-data, .lh-crc'
SEL_TREEMAP_BTN = 'text=View Treemap'
SEL_DESKTOP_TAB = 'text=Desktop'


def report_pictures(store, page, url, which):
    """Open the report page headless, wait for it, and capture the gauge block and the field card for mobile and
    desktop, at page zoom 1.15 with the mouse parked off the report. Returns the report's numbers when the page
    exposes its LHR, else only the capture names. Any failure is recorded and left to Chrome; the audit never waits."""
    out = {'report_url': None, 'captures': {}, 'numbers': {}}
    try:
        captures.goto(page, REPORT_URL.format(url=quote(url, safe=''), ff='mobile'), wait='domcontentloaded')
        page.wait_for_selector(SEL_METRICS, timeout=config.PSI_TIMEOUT)
        page.wait_for_timeout(3000)
        out['report_url'] = page.url
        for ff in ('mobile', 'desktop'):
            if ff == 'desktop':
                page.click(SEL_DESKTOP_TAB)
                page.wait_for_timeout(2500)
            lhr = page.evaluate(snippets.PSI_PAGE_LHR)
            if lhr.get('found'):
                out['numbers'][ff] = summarize_lhr(lhr['lhr'])
            captures.element_shot(store, page, SEL_GAUGE_BLOCK, f'psi_{which}_{ff}_gauges.png', zoom=config.PSI_ZOOM, pad=8)
            out['captures'][f'{ff}_gauges'] = f'psi_{which}_{ff}_gauges.png'
            try:
                captures.element_shot(store, page, SEL_FIELD_CARD, f'psi_{which}_{ff}_field.png', zoom=config.PSI_ZOOM, pad=8)
                out['captures'][f'{ff}_field'] = f'psi_{which}_{ff}_field.png'
            except Exception as e:
                store.not_captured(f'psi_{which}_{ff}_field.png', f'field card not found on the report page: {e}')
    except Exception as e:
        store.not_captured(f'PageSpeed report pictures for {which}', f'{type(e).__name__}: {e}')
    return out


def treemap_picture(store, page):
    """A real click on View Treemap opens the treemap app in a new page; screenshot it and count the GTM nodes there."""
    try:
        with page.context.expect_page(timeout=20000) as new_page:
            page.click(SEL_TREEMAP_BTN)
        tm = new_page.value
        tm.wait_for_load_state('load', timeout=config.PSI_TIMEOUT)
        tm.wait_for_timeout(3000)
        counts = tm.evaluate(snippets.TREEMAP_GTM)
        captures.shot(store, tm, 'treemap_home.png')
        tm.close()
        return counts
    except Exception as e:
        store.not_captured('treemap_home.png', f'{type(e).__name__}: {e}')
        return None


def summarize_lhr(lhr):
    a = lhr.get('audits', {})
    n = lambda k: a.get(k, {}).get('numericValue')
    return {'score': round((lhr.get('categories', {}).get('performance', {}).get('score') or 0) * 100),
            'fcp_s': n('first-contentful-paint') and round(n('first-contentful-paint') / 1000, 1),
            'lcp_s': n('largest-contentful-paint') and round(n('largest-contentful-paint') / 1000, 1),
            'tbt_ms': n('total-blocking-time') and round(n('total-blocking-time')),
            'cls': n('cumulative-layout-shift') and round(n('cumulative-layout-shift'), 3),
            'si_s': n('speed-index') and round(n('speed-index') / 1000, 1)}


def phone_screens(store, fps, scale=1.25, outline=(255, 45, 85), border=4):
    """Cut the mobile full-page render (412 px wide) into 412 x 823 phone screens with the 4 px #FF2D55 outline, saved at
    1.25 scale to match the decks so far (about 505 x 997 px each). Returns the file names."""
    if not fps or not fps.get('data'):
        return []
    data = fps['data']
    raw = base64.b64decode(data.split(',', 1)[1])
    im = Image.open(io.BytesIO(raw)).convert('RGB')
    if im.size[0] != 412:
        im = im.resize((412, round(im.size[1] * 412 / im.size[0])))
    names = []
    for i in range(4):
        y0 = i * 823
        if y0 >= im.size[1]:
            break
        screen = Image.new('RGB', (412, 823), 'white')
        screen.paste(im.crop((0, y0, 412, min(y0 + 823, im.size[1]))), (0, 0))
        from PIL import ImageDraw
        ImageDraw.Draw(screen).rectangle((0, 0, 411, 822), outline=outline, width=border)
        screen = screen.resize((round(412 * scale), round(823 * scale)), Image.LANCZOS)
        name = f'vdp_phone_{i + 1}.png'
        screen.save(store.captures / name)
        store.record_capture(name, store.results['pages'].get('vdp'), screen.size)
        names.append(name)
    return names
