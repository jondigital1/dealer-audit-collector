"""Step 3: the Bing listing. bing.com/maps?q=[dealer and street address], the left panel captured at about 700 px
wide, the website link read out of the bing.com/alink/link?url= wrapper with its query keys, every button's text,
host and path, the hours behind the "More hours" toggle (span.op_mht: script click, read, click again to close before
the capture), the rating and its source, the description present or not. Whether Bing Maps renders for a headless
browser is one of the platform test's questions; a failure here is recorded and left to Chrome."""
import re
from urllib.parse import parse_qs, urlparse, unquote

from . import captures

PANEL = '.b_entityTP, .lm_panel, [class*="entity"], #maps_sidebar, .taskbar'


def listing(store, page):
    r = store.results
    q = f"{store.req.get('store', '')} {store.results['address_hours']['site_address'] or ''}".strip() or store.req['url']
    url = f'https://www.bing.com/maps?q={q}'
    b = {'exists': None, 'name': None, 'rating': None, 'rating_source': None, 'website_host': None, 'website_url': None, 'utm_keys': [],
         'hours': None, 'description_present': None, 'lead_photo_note': None, 'buttons': [], 'capture': None, 'query': q, 'status': None}
    try:
        captures.goto(page, url, wait='domcontentloaded')
        page.wait_for_timeout(5000)   # the photos take a few seconds to load
        info = page.evaluate("""() => {
          const links = [...document.querySelectorAll('a[href]')].map(a => ({ text: a.innerText.trim().slice(0, 60), href: a.href })).filter(l => l.text);
          const web = links.find(l => /alink\\/link\\?url=/.test(l.href));
          const rating = (document.body.innerText.match(/(\\d\\.\\d)\\s*\\/\\s*5\\s*\\(?(\\d[\\d,]*)?\\s*reviews?\\)?/i) || [])[0] || null;
          const source = (document.body.innerText.match(/\\b(Yelp|Facebook|Tripadvisor|SureCritic|DealerRater|Cars\\.com|Google)\\b/) || [])[1] || null;
          const more = document.querySelector('span.op_mht, [class*="op_mht"]');
          let hours = null;
          if (more) { more.click(); hours = [...document.querySelectorAll('tr')].map(t => t.innerText.trim()).filter(t => /am|pm|closed/i.test(t)).slice(0, 8).join(' | '); more.click(); }
          const desc = /About|description/i.test(document.body.innerText) && document.body.innerText.length > 200;
          const name = (document.querySelector('h1, h2, .b_entityTitle, [class*="title"]') || {}).innerText || null;
          return { links: links.slice(0, 60), web: web ? web.href : null, rating, source, hours, desc, name, text: document.body.innerText.slice(0, 3000) };
        }""")
        b['exists'] = bool(info['web'] or info['name'])
        b['name'] = (info['name'] or '').strip()[:80] or None
        b['rating'] = info['rating']
        b['rating_source'] = info['source']
        b['hours'] = info['hours']
        b['description_present'] = bool(info['desc'])
        if info['web']:
            real = unquote(parse_qs(urlparse(info['web']).query).get('url', [''])[0])
            b['website_url'] = real
            u = urlparse(real)
            b['website_host'] = u.netloc
            b['utm_keys'] = [k for k in parse_qs(u.query) if k.startswith('utm_')]
        for l in info['links']:
            href = l['href']
            if 'alink/link?url=' in href:
                href = unquote(parse_qs(urlparse(href).query).get('url', [href])[0])
            u = urlparse(href)
            b['buttons'].append({'text': l['text'], 'host': u.netloc, 'path': u.path, 'href': href})
        try:
            captures.element_shot(store, page, PANEL, 'bing_panel.png', pad=6)
            b['capture'] = 'captures/bing_panel.png'
        except Exception as e:
            captures.shot(store, page, 'bing_panel.png', clip={'x': 0, 'y': 0, 'width': 720, 'height': 1019})
            b['capture'] = 'captures/bing_panel.png'
            store.log(f'bing panel captured as the left 720 px (no panel element matched: {e})')
        b['status'] = 'ok'
        r['bing'] = b
        store.check('bing', 'ok')
    except Exception as e:
        b['status'] = 'failed'
        r['bing'] = b
        store.check('bing', 'failed', f'{type(e).__name__}: {e}')
