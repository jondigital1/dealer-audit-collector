"""Step 3: the Bing listing. bing.com/maps?q=[dealer and street address], the left panel captured at the skill's
zoom 1.35 (about 575 px wide, the fixture's width), the website link read out of the bing.com/alink/link?url=
wrapper with its query keys, every button and link in the panel with its text, host and path, the hours behind the
"More hours" toggle (span.op_mht: script click, read the rows, click again to close before the capture), the rating
and its source, the description present or not. Confirmed on a live panel Sep 30, 2026: the entity card is
#lcmaginfocard inside the sidebar's card column (div.b_lcmgzsubcrd), the rating reads "2/5 (13 reviews)", and the
review-source block reads "2.0/5 Yelp (13 reviews)"."""
import re
from urllib.parse import parse_qs, urlparse, unquote

from . import captures, config, snippets
from .store import now_et

BING_ZOOM = 1.35
CARD = '#lcmaginfocard'

PANEL = """() => {
  const card = document.querySelector('#lcmaginfocard'); if (!card) return null;
  const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const box = e => { const r = e.getBoundingClientRect(); return { x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height }; };
  // the entity card (photos, name, rating, address, hours, phone, Directions), then the cards under it in the same
  // column (About, the review sources) up to the first Sponsored card or a gap
  const col = card.closest('.b_lcmgzentitycard, .b_lcmgzsubcrd, .cards') || card;
  const colBox = box(col);
  const cards = [...document.querySelectorAll('.cards, .b_lcmgzsubcrd, .b_loccardans')].filter(vis).map(e => ({ e, b: box(e) }))
    .filter(c => c.b.y >= colBox.y + colBox.h - 8 && Math.abs(c.b.x - colBox.x) < 40 && Math.abs(c.b.w - colBox.w) < 60 && c.b.h > 20 && !col.contains(c.e) && !c.e.contains(col)).sort((a, b) => a.b.y - b.b.y || b.b.h - a.b.h);
  let bottom = colBox.y + colBox.h; const under = [];
  for (const c of cards) { if (/Sponsored/.test(c.e.innerText || '') || c.b.y > bottom + 300) break; if (c.b.y + c.b.h <= bottom) continue; under.push(c.e); bottom = c.b.y + c.b.h; if (bottom - colBox.y > 1500) break; }
  colBox.h = Math.min(bottom - colBox.y, 1500);
  const aboutBlocks = under.filter(e => /\\bAbout\\b/.test(e.innerText || ''));
  const ratingBlocks = under.filter(e => /\\d(\\.\\d)?\\/5/.test(e.innerText || ''));
  const text = (col.innerText || '') + '\\n' + under.map(e => e.innerText).join('\\n');
  const links = [...col.querySelectorAll('a[href]'), ...under.flatMap(e => [...e.querySelectorAll('a[href]')])].filter(vis).map(a => ({ text: a.innerText.trim().replace(/\\s+/g, ' ').slice(0, 60), href: a.href, aria: a.getAttribute('aria-label') || '' }));
  const web = links.find(l => /alink\\/link\\?url=/.test(l.href));
  const rating = (text.match(/(\\d(?:\\.\\d)?)\\s*\\/\\s*5\\s*\\((\\d[\\d,]*)\\s*reviews?\\)/i) || [])[0] || null;
  const src = (text.match(/\\d(?:\\.\\d)?\\/5\\s*\\n?\\s*(Yelp|Facebook|Tripadvisor|SureCritic|Surecritic|DealerRater|Cars\\.com|Google|Foursquare)/) || [])[1] || null;
  const name = (card.querySelector('a, h2, [class*="title"]') || {}).innerText || null;
  const addr = (text.match(/\\d+[^\\n]{3,80},\\s*[A-Z]{2}\\s*\\d{5}(?:-\\d{4})?/) || [])[0] || null;
  const category = (text.match(/\\)\\s*·\\s*([^\\n·]{3,60}?)\\s*(?:in|·)/) || [])[1] || null;
  const about = /\\bAbout\\b/.test(text) && text.split(/\\bAbout\\b/)[1] ? text.split(/\\bAbout\\b/)[1].trim().slice(0, 300) : null;
  const more = [...document.querySelectorAll('span.op_mht, [class*="op_mht"]')].find(vis);
  return { colBox, under: under.map(e => (e.innerText || '').replace(/\\s+/g, ' ').slice(0, 30) + ' @' + Math.round(box(e).y) + '+' + Math.round(box(e).h)), colClass: (col.className || '').toString().slice(0, 60), text: text.slice(0, 4000), links, web: web ? web.href : null, rating, src, name, addr, category, about, hasMore: !!more };
}"""

MORE_HOURS = """(open) => { const more = [...document.querySelectorAll('span.op_mht, [class*="op_mht"]')].find(e => e.getBoundingClientRect().width > 0); if (!more) return null;
  more.click(); const rows = [...document.querySelectorAll('tr')].map(t => t.innerText.trim().replace(/\\s+/g, ' ')).filter(t => /am|pm|closed/i.test(t) && t.length < 60);
  if (!open) more.click(); return rows.slice(0, 10); }"""


def listing(store, page):
    r = store.results
    ah = r.get('address_hours') or {}
    addr = ah.get('site_address') or ''
    street = addr.split(',')[0] if addr else ''
    city = store.req.get('city') or (addr.split(',')[1].strip() if addr.count(',') >= 2 else '')
    state = store.req.get('state') or (addr.split(',')[2].strip().split(' ')[0] if addr.count(',') >= 2 else '')
    q = f"{store.req.get('store', '')} {street} {city} {state}".strip() or store.req['url']
    q = re.sub(r'\s+', ' ', q)
    url = f'https://www.bing.com/maps?q={q}'
    b = {'exists': None, 'name': None, 'rating': None, 'rating_source': None, 'category': None, 'website_host': None, 'website_url': None, 'utm_keys': [],
         'hours': None, 'address': None, 'description_present': None, 'description': None, 'lead_photo_note': None, 'buttons': [], 'capture': None,
         'query': q, 'read_at': now_et(), 'status': None}
    try:
        captures.goto(page, url, wait='domcontentloaded')
        page.wait_for_timeout(6000)   # the photos take a few seconds to load
        info = page.evaluate(PANEL)
        if not info:
            b['exists'] = False
            b['status'] = 'no panel'
            r['bing'] = b
            store.check('bing', 'failed', f'Bing Maps showed no entity panel for "{q}"')
            return
        b['exists'] = True
        b['name'] = (info['name'] or '').strip()[:80] or None
        # the panel must be this store's: Bing answered "Bay Lincoln 704 W 15th Street" with Bay Hyundai's listing on the
        # same campus (Oct 1, 2026); a different name is recorded and kept out of the address and hours compare
        want = [w for w in re.findall(r'[a-z0-9]+', (store.req.get('store') or '').lower()) if len(w) > 2]
        got = (b['name'] or '').lower()
        b['name_matches'] = bool(want) and all(w in got for w in want[:2])
        if not b['name_matches']:
            b['note'] = f'the panel Bing showed is "{b["name"]}", not {store.req.get("store")}; its address and hours are recorded but not compared'
            store.noticed(f'Bing Maps showed "{b["name"]}" for the query "{q}"; no listing of its own found for {store.req.get("store")}', 'captures/bing_panel.png')
        b['rating'] = info['rating']
        b['rating_source'] = info['src']
        b['category'] = info['category']
        b['address'] = info['addr']
        b['description_present'] = bool(info['about'])
        b['description'] = info['about']
        if info['web']:
            real = unquote(parse_qs(urlparse(info['web']).query).get('url', [''])[0])
            b['website_url'] = real
            u = urlparse(real)
            b['website_host'] = u.netloc
            b['utm_keys'] = [k for k in parse_qs(u.query) if k.startswith('utm_')]
        seen = set()
        for l in info['links']:
            href = l['href']
            if 'alink/link?url=' in href:
                href = unquote(parse_qs(urlparse(href).query).get('url', [href])[0])
            u = urlparse(href)
            key = (l['text'] or l['aria'], href)
            if key in seen or href.startswith('javascript'):
                continue
            seen.add(key)
            b['buttons'].append({'text': l['text'] or l['aria'], 'host': u.netloc, 'path': u.path, 'href': href})
        if info['hasMore']:
            rows = page.evaluate(MORE_HOURS, False)
            b['hours'] = rows
            if b['name_matches']:
                ah['bing_hours_rows'] = rows
        if b['name_matches']:
            ah['bing_address'] = b['address']
        else:
            ah['bing_listing_note'] = b['note']
        # the panel, at the skill's zoom, the mouse parked off it
        page.evaluate(snippets.ZOOM, BING_ZOOM)
        page.wait_for_timeout(600)
        info2 = page.evaluate(PANEL)
        box = info2['colBox'] if info2 else None
        if box:
            # Bing Maps is a fixed-height app whose sidebar scrolls on its own, so a full-page capture ends at the
            # frame; the frame is made tall enough for the panel, then put back
            tall = int(min(max(config.VIEWPORT['height'], box['y'] + box['h'] + 40), 2400))
            if tall > config.VIEWPORT['height']:
                page.set_viewport_size({'width': config.VIEWPORT['width'], 'height': tall})
                page.wait_for_timeout(800)
                info3 = page.evaluate(PANEL)
                box = info3['colBox'] if info3 and info3.get('colBox') else box
            page.mouse.move(config.VIEWPORT['width'] - 1, 5)
            path = store.captures / 'bing_panel.png'
            page.screenshot(path=str(path), type='png', clip={'x': max(0, box['x'] - 4), 'y': max(0, box['y'] - 4), 'width': box['w'] + 8, 'height': min(box['h'] + 8, tall - box['y'] + 4)})
            page.set_viewport_size(config.VIEWPORT)
            from PIL import Image
            store.record_capture('bing_panel.png', page.url, Image.open(path).size)
            store.log(f'captured bing_panel.png {Image.open(path).size[0]}x{Image.open(path).size[1]} (entity card {box["h"]:.0f} px tall with the cards under it: {info2.get("under")})')
            b['capture'] = 'captures/bing_panel.png'
            if b['address']:
                try:
                    captures.text_shot(store, page, b['address'][:14], 'address_bing.png', pad=4)
                    ah.setdefault('captures', []).append('captures/address_bing.png')
                except Exception as e:
                    store.not_captured('address_bing.png', str(e))
        page.evaluate(snippets.ZOOM, 1)
        b['status'] = 'ok'
        r['bing'] = b
        store.check('bing', 'ok')
    except Exception as e:
        b['status'] = 'failed'
        r['bing'] = b
        store.check('bing', 'failed', f'{type(e).__name__}: {str(e)[:200]}')
