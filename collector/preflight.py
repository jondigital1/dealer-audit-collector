"""Pre-flight (SPEC.md section 2, last row): in seconds, before an hour of capture, find the stores that should not
be captured at all. The site loads over https (two tries); the final host after redirects (a different domain means
a rename or a sale); the dealer's name in the site's title and JSON-LD against the request; the old domain's fate when
the request names one; the platform from the page's markers; and, for a group, the group site's card for the store.
Google's listing check (the website link must match the domain) is Claude's, in Chrome: no Places API."""
import json
import re
from urllib.parse import urlparse

from . import captures, config, snippets
from .store import domain_of


def detect_platform(page):
    html = page.content().lower()
    hosts = page.evaluate("() => [...document.querySelectorAll('script[src], link[href]')].map(e => e.src || e.href).join(' ')").lower()
    blob = html[:200000] + ' ' + hosts
    for name, markers in config.PLATFORM_MARKERS.items():
        if any(m.lower() in blob for m in markers):
            return name
    return 'other'


def run(store, page, platforms):
    req = store.req
    pf = {'loads': False, 'status': None, 'final_host': None, 'redirected_to_other_domain': False, 'site_name': None, 'name_matches': None,
          'old_domain_result': None, 'platform': None, 'platform_headless': None, 'notes': []}
    url = req['url'] if '://' in req['url'] else 'https://' + req['url']
    for attempt in (1, 2):
        try:
            resp = captures.goto(page, url, wait='domcontentloaded')
            pf['status'] = resp.status if resp else None
            pf['loads'] = bool(resp) and resp.status < 400
            break
        except Exception as e:
            pf['notes'].append(f'load attempt {attempt}: {type(e).__name__}: {e}')
    if not pf['loads']:
        store.results['preflight'] = pf
        store.check('preflight', 'failed', 'the site does not load: ' + '; '.join(pf['notes'][-2:]))
        return pf
    pf['final_host'] = urlparse(page.url).netloc
    pf['redirected_to_other_domain'] = domain_of(page.url) != domain_of(url)
    if pf['redirected_to_other_domain']:
        pf['notes'].append(f'{domain_of(url)} redirects to {domain_of(page.url)}: a rename or a sale until proven otherwise')
    title = page.title() or ''
    ld_name = None
    for s in page.evaluate("() => [...document.querySelectorAll('script[type=\"application/ld+json\"]')].map(s => s.textContent)"):
        try:
            o = json.loads(s)
            for x in (o if isinstance(o, list) else [o]):
                if isinstance(x, dict) and x.get('name') and 'dealer' in str(x.get('@type', '')).lower() + str(x.get('name', '')).lower():
                    ld_name = x['name']
                    break
        except Exception:
            continue
    pf['site_name'] = ld_name or title.split('|')[0].strip()[:80]
    want = (req.get('store') or '').lower()
    words = [w for w in re.findall(r'[a-z0-9]+', want) if len(w) > 2]
    pf['name_matches'] = bool(words) and all(w in (pf['site_name'] or '').lower() + ' ' + title.lower() for w in words[:2])
    if req.get('store') and not pf['name_matches']:
        pf['notes'].append(f'the request says "{req["store"]}" but the site says "{pf["site_name"]}" ({title[:80]})')
    pf['platform'] = detect_platform(page)
    pf['platform_headless'] = (platforms or {}).get(pf['platform'], {}).get('headless', 'untested')
    if pf['platform_headless'] == 'chrome_only':
        pf['notes'].append(f'{pf["platform"]} is marked chrome_only in platforms.json: this store goes to Chrome')
    if req.get('old_domain'):
        try:
            resp = captures.goto(page, 'https://' + domain_of(req['old_domain']), wait='domcontentloaded')
            pf['old_domain_result'] = f'{resp.status if resp else "no response"} -> {urlparse(page.url).netloc}'
        except Exception as e:
            pf['old_domain_result'] = f'{type(e).__name__}'
    if req.get('group_site'):
        try:
            captures.goto(page, req['group_site'], wait='domcontentloaded')
            page.wait_for_timeout(1500)
            card = page.evaluate("""(name) => { const vis = e => { const r = e.getBoundingClientRect(); return r.width > 120 && r.height > 20; };
                const contact = /\\(?\\d{3}\\)?[\\s.-]\\d{3}[\\s.-]\\d{4}|\\b\\d{5}(-\\d{4})?\\b/;
                const txt = e => (e.innerText && e.innerText.trim()) ? e.innerText : (e.textContent || '');
                const els = [...document.querySelectorAll('body *')].filter(e => e.children.length < 60 && txt(e).includes(name) && txt(e).length < 1200 && contact.test(txt(e)));
                // the visible block first (a hidden map info window carries the same card), then the shortest
                const c = els.sort((a, b) => (vis(b) - vis(a)) || (txt(a).length - txt(b).length))[0]; if (!c) return null; const r = c.getBoundingClientRect();
                return { text: txt(c).trim().replace(/[ \\t]+/g, ' ').replace(/\\n\\s*\\n/g, '\\n'), visible: vis(c), where: c.tagName.toLowerCase() + '.' + (c.className || '').toString().trim().split(/\\s+/).slice(0, 2).join('.'),
                         links: [...c.querySelectorAll('a[href]')].map(a => ({ text: a.innerText.trim().slice(0, 40), href: a.href, host: new URL(a.href).host })), box: { x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height } }; }""", req.get('store') or '')
            if card:
                store.results['group_card'] = {'text': card['text'][:800], 'where': card['where'], 'visible': card['visible'], 'links': card['links'], 'capture': None,
                                               'address': None, 'hours': None, 'phone': None, 'new_count': None}
                m = re.search(r'\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}', card['text'])
                if m:
                    store.results['group_card']['phone'] = m.group(0)
                m = re.search(r'(\d+\s[^\n]*?,\s*[A-Z]{2}\s*\d{5}(?:-\d{4})?)', card['text'].replace('\n', ' '))
                if m:
                    store.results['group_card']['address'] = re.sub(r'\s+', ' ', m.group(1)).strip()
                store.results['group_card']['url'] = page.url
                if card['visible']:
                    try:
                        captures.box_shot(store, page, card['box'], 'group_card.png', pad=10)
                        store.results['group_card']['capture'] = 'captures/group_card.png'
                    except Exception as e:
                        store.not_captured('group_card.png', str(e))
                else:
                    store.not_captured('group_card.png', f'the group site\'s card for this store is in a hidden block ({card["where"]}); its text is recorded')
            else:
                pf['notes'].append('the group site shows no card for this store')
        except Exception as e:
            pf['notes'].append(f'group site: {type(e).__name__}: {e}')
    store.results['preflight'] = pf
    store.results['platform'] = pf['platform']
    store.results['collector']['platform_headless'] = pf['platform_headless']
    store.check('preflight', 'ok')
    return pf
