"""The dealer site checks: set-up (the three pages), SEO META fields, vehicle links and inventory count, the menu
crawl, address, hours and phones, the customer-experience and content pages, the blog, the slider, empty blocks and
special hours. Each function records into store.results and saves; a failure marks the check and moves on."""
import re
from urllib.parse import urljoin, urlparse

from PIL import Image

from . import captures, config, snippets
from .store import domain_of

NEW_SRP_PATHS = ['/new-inventory/index.htm', '/new-inventory/', '/new-vehicles/', '/inventory/new/', '/new/', '/searchnew.aspx', '/new-inventory']
HOLIDAYS = r"(Christmas Eve|Christmas Day|Christmas|New Year's Eve|New Year's Day|New Years Eve|New Years Day|Thanksgiving|Labor Day|Memorial Day|Independence Day|July 4th|Fourth of July|Easter|Good Friday|Veterans Day|Columbus Day|Juneteenth|MLK Day|Martin Luther King|Presidents'? Day)"
NOT_FOUND = re.compile(r'\b404\b|page not found|not found|no longer available', re.I)
# a page that opens but has nothing on it (the fixture's Used body-style pages read 0 Vehicles; Testimonials and News
# read "Sorry, no ... available at this time"); the words are recorded and Claude judges the page from its capture
EMPTY_PAGE = re.compile(r'\b0 (vehicles?|results?|matches)\b|check back soon|no (vehicles|results|posts|news|testimonials|specials|offers)\b[^\n]{0,60}|sorry, no [^\n]{0,80}(available|found|matched)|currently no [^\n]{0,40}|we are currently updating', re.I)
SPECIALS_EMPTY = re.compile(r'NO RESULTS|No vehicles found|We are currently updating|no specials|currently no', re.I)
THIRD_PARTY = ('commercialtrucktrader.com', 'cars.com', 'autotrader.com', 'carfax.com', 'expressoil.com')


def slug(s):
    return re.sub(r'[^a-z0-9]+', '_', s.lower()).strip('_')[:40] or 'item'


def pick_new_srp(links):
    """The new inventory SRP from the main menu: the New menu's inventory item first (New Vehicles, New Inventory,
    View All New, or any item whose path names new inventory), then a top-level New link only when its path says new
    (Bay Hyundai's top New link opens /all-inventory/, new and used together)."""
    def is_new_path(p):
        return bool(re.search(r'new-inventory|new-vehicles|inventory/new|/new/?$|searchnew|newinventory', p, re.I)) and 'special' not in p.lower()
    cands = [l for l in links if is_new_path(l['path']) and not re.search(r'specials|offers|featured|hybrid|electric|sedan|suv|truck|research', l['path'] + ' ' + l['label'], re.I)]
    for pat in (r'^(new vehicles|new inventory|view all new|all new|shop all new|shop new|new cars)', r'^new\b'):
        hit = next((l for l in cands if re.search(pat, l['label'], re.I)), None)
        if hit:
            return hit
    return cands[0] if cands else None


# The first vehicle card on the SRP with a real price: the nearest ancestor of a vehicle link whose text carries a
# dollar figure (DDC wraps the link in a media div with no price, so the anchor's closest card is not enough)
FIRST_VEHICLE = """() => {
  const money = /\\$\\s?\\d[\\d,]{3,}/;
  // Dealer.com links VDPs as /new/Make/...htm, DealerOn as /new-<town>-<year>-<make>-<model>-<VIN>; a VIN at the end of a
  // path marks a vehicle link on any platform
  const sels = 'a[href*="/new/"], a[href*="/inventory/"], a[href*="/vehicle"], a[href*="/vdp"], a[href*="vin="], a[href*="/detail"], a[href*="/new-"]';
  const vinEnd = /[A-HJ-NPR-Z0-9]{17}\\/?$/;
  const all = [...document.querySelectorAll(sels)]; for (const a of document.querySelectorAll('a[href]')) if (vinEnd.test(a.href.split('?')[0]) && !all.includes(a)) all.push(a);
  for (const a of all) {
    if (/specials|promotions|research|inventory\\/index|new-inventory\\/index|searchnew|searchused|new-vehicles\\/?$|new-inventory\\/?$/i.test(a.getAttribute('href') || '')) continue;
    let c = a, hops = 0;
    while (c && c !== document.body && hops < 8) { const t = (c.innerText || ''); if (money.test(t) && t.length < 2500) return { href: a.href, text: t.trim().replace(/\\s+/g, ' ').slice(0, 220), tag: c.tagName, cls: (c.className || '').toString().slice(0, 60) }; c = c.parentElement; hops++; }
  }
  return null;
}"""

SRP_COUNT = """() => {
  const el = document.querySelector('.vehicle-count, [class*="vehicle-count"], [class*="results-count"], [class*="result-count"], [class*="inventory-count"], [class*="srp-count"], [class*="total-results"], [class*="matches"], [class*="results-title"], [class*="result-title"], [class*="results-heading"]');
  return { el: el ? el.innerText.trim().slice(0, 80) : null, body: document.body.innerText.slice(0, 6000) };
}"""


def setup_pages(store, page):
    """Step 1: the home page, the new inventory SRP and the first in-stock new VDP with a real price."""
    r = store.results
    home = r['pages']['home']
    captures.goto(page, home)
    r['pages']['home'] = page.url
    links = page.evaluate(snippets.MENU_LINKS)
    new_item = pick_new_srp(links)
    srp = new_item['href'] if new_item else None
    if srp:
        r['pages']['srp_from'] = f'main menu: {new_item["top"] + " > " if new_item["top"] else ""}{new_item["label"]}'
    if not srp:
        for p in NEW_SRP_PATHS:
            try:
                rr = captures.goto(page, urljoin(page.url, p))
                if rr and rr.status == 200 and not NOT_FOUND.search(page.title()):
                    srp = page.url
                    r['pages']['srp_from'] = f'usual path {p}'
                    break
            except Exception:
                continue
    if not srp:
        store.check('setup_srp', 'failed', 'could not find the new inventory SRP; give the URL in the request')
        return
    captures.goto(page, srp)
    page.wait_for_timeout(1500)
    r['pages']['srp'] = page.url
    c = page.evaluate(SRP_COUNT)
    # the model years on the SRP's cards (the research and slider checks compare against the newest one)
    years = page.evaluate("""() => { const out = {}; for (const h of document.querySelectorAll('h2, h3, [class*="vehicle-card-title"], [class*="vehicle-title"], [class*="title"]')) { const m = (h.innerText || '').match(/\\b(20[2-3]\\d)\\b/); if (m) out[m[1]] = (out[m[1]] || 0) + 1; } return out; }""")
    if years:
        r['pages']['srp_model_years'] = sorted(int(y) for y in years)
        r['pages']['srp_model_year_counts'] = years
    m = None
    if c['el']:
        m = re.search(r'(\d[\d,]*)\s*(new\s+)?(vehicles?|results?|matches?|cars?|listings?)', c['el'], re.I)
        if not m:   # Dealer Inspire: "477 New HYUNDAI in Jacksonville, FL"
            m = re.search(r'(\d[\d,]*)\s+(new\s+)?([A-Za-z][A-Za-z-]+)', c['el'].split('\n')[0], re.I)
    if not m:
        m = re.search(r'(\d[\d,]*)\s+(new\s+)?(vehicles?|results?|matches?|cars?|listings?)', c['body'], re.I)
    if m:
        r['pages']['srp_new_count'] = int(m.group(1).replace(',', ''))
        r['pages']['srp_new_count_text'] = m.group(0) + (f' (count element: {c["el"]})' if c['el'] and c['el'] != m.group(0) else '')
    try:
        captures.union_shot(store, page, ['h1', '.vehicle-count, [class*="vehicle-count"], [class*="results-count"], [class*="result-count"], [class*="inventory-count"], [class*="srp-count"]'],
                            'srp_header.png', pad=20, zoom=config.DEALER_ZOOM)
    except Exception as e:
        store.not_captured('srp_header.png', str(e))
    vdp = page.evaluate(FIRST_VEHICLE)
    if not vdp:
        store.check('setup_vdp', 'failed', 'no vehicle card with a price on the SRP')
        return
    captures.goto(page, vdp['href'])
    r['pages']['vdp'] = page.url.split('?')[0] if 'priorityType' in page.url else page.url
    r['pages']['vdp_vehicle'] = vdp['text'][:160]
    store.check('setup', 'ok')


def seo_meta(store, page):
    """Step 9: the skill's SEO META script on the home page, SRP and VDP (image counts from the home page only)."""
    for key in ('home', 'srp', 'vdp'):
        url = store.results['pages'].get(key)
        if not url:
            continue
        try:
            captures.goto(page, url)
            m = page.evaluate(snippets.SEO_META)
            rec = {'title': m['title'], 'title_len': m['titleLen'], 'meta': m['meta'], 'meta_len': m['metaLen'], 'h': m['h'], 'h1_text': m['h1All'], 'h1_visible': m['h1Visible']}
            if key == 'home':
                rec.update({'images': m['images'], 'no_alt': m['noAlt'], 'no_title': m['noTitle'], 'read_at': store.results['captured_at'],
                            'images_note': 'the page\'s own images after a stepwise scroll to the bottom' + (f'; a map widget adds {m["mapImages"]} more, counted under images_with_map' if m.get('withMap') else '')})
                if m.get('withMap'):
                    rec['images_with_map'] = {'images': m['withMap']['images'], 'no_alt': m['withMap']['noAlt'], 'no_title': m['withMap']['noTitle']}
                if m.get('pixels'):
                    px = m['pixels']
                    rec['tracking_pixels'] = {'images': px['images'], 'no_alt': px['noAlt'], 'no_title': px['noTitle'], 'srcs': px['srcs'],
                                              'note': 'zero or one px images and ad or analytics hosts; the raw counts above include them, the flag\'s ALT-or-TITLE choice leaves them out'}
                    rec['no_alt_excluding_pixels'] = m['noAlt'] - px['noAlt']
                    rec['no_title_excluding_pixels'] = m['noTitle'] - px['noTitle']
                if m.get('carousel', {}).get('images'):
                    c = m['carousel']
                    rec['images_in_carousels'] = {'images': c['images'], 'no_alt': c['noAlt'], 'cloned_slides': c['cloned'], 'cloned_no_alt': c['clonedNoAlt'],
                                                  'note': 'carousels clone slides and swap lazy images as they rotate, so a read\'s counts depend on the carousel\'s state at read time'}
            store.results['seo_meta'][key] = rec
        except Exception as e:
            store.check(f'seo_meta_{key}', 'failed', str(e))
    store.check('seo_meta', 'ok')


def srp_links(store, page):
    """Step 10: vehicle links written as http:// on an https:// SRP."""
    url = store.results['pages'].get('srp')
    if not url:
        return
    try:
        captures.goto(page, url)
        # a slow pass: DealerOn's SRP adds its cards as the page scrolls (Natchez Nissan read 3 vehicles at a fast pass, 12 at this one)
        page.evaluate("""async () => { const h = document.body.scrollHeight; for (let y = 0; y < h; y += 400) { window.scrollTo(0, y); await new Promise(r => setTimeout(r, 300)); } await new Promise(r => setTimeout(r, 2500)); window.scrollTo(0, 0); }""")
        l = page.evaluate(snippets.SRP_LINKS)
        store.results['links'] = {'srp_vehicle_links': l['links'], 'srp_vehicle_links_unique': l['unique'], 'srp_http_links': l['http'],
                                  'example_http_link': l['example'] or None, 'selector': l['selector'], 'skill_selector_links': l['skill_selector_links'],
                                  'srp_is_https': url.startswith('https://'), 'read_at': store.results['captured_at']}
        store.check('srp_links', 'ok')
    except Exception as e:
        store.check('srp_links', 'failed', str(e))


def classify_landing(page, resp, dealer, href_path, group_host=None, sisters=()):
    """Where a real navigation landed: 404, home_redirect, empty, ok, group_site, sister_site, third_party or offsite."""
    landed = urlparse(page.url)
    lh = domain_of(page.url)
    body = page.evaluate('() => (document.body.innerText || "").slice(0, 20000)') if lh == dealer else ''
    if (resp and resp.status == 404) or NOT_FOUND.search(page.title() or ''):
        return '404', None
    if lh == dealer and landed.path in ('', '/') and href_path not in ('', '/'):
        return 'home_redirect', None
    if lh == dealer and EMPTY_PAGE.search(body) and not re.search(r'inventory/index|all-inventory', landed.path):
        return 'empty', EMPTY_PAGE.search(body).group(0).strip()
    if lh == dealer:
        return 'ok', None
    if group_host and lh == group_host:
        return 'group_site', None
    if lh in sisters:
        return 'sister_site', None
    if any(lh.endswith(t) for t in THIRD_PARTY):
        return 'third_party', None
    return 'offsite', None


def crawl_links(store, page, links, dealer, prefix, max_links=24):
    """Open each link with a real navigation and classify where it lands; the landed page captured when it is not ok."""
    out = []
    start_url = page.url
    for l in links[:max_links]:
        if store.over_budget():
            store.not_captured(f'{prefix} links', 'store time budget reached; the rest are unopened')
            break
        item = {'label': l.get('label'), 'href': l.get('href'), 'path': l.get('path'), 'status': None, 'result': None, 'landed_host': None, 'landed_path': None, 'capture_dest': None}
        try:
            resp = captures.goto(page, l['href'], wait='domcontentloaded')
            page.wait_for_timeout(1000)
            item['status'] = resp.status if resp else None
            item['landed_host'] = urlparse(page.url).netloc
            item['landed_path'] = urlparse(page.url).path
            item['result'], note = classify_landing(page, resp, dealer, l.get('path') or '')
            if note:
                item['empty_text'] = note
            if item['result'] != 'ok':
                name = f'dest_{prefix}_{slug(l.get("label") or l.get("path") or "link")}.png'
                captures.shot(store, page, name, full_page=False, zoom=config.DEALER_ZOOM)
                item['capture_dest'] = f'captures/{name}'
        except Exception as e:
            item['result'] = 'error'
            item['status'] = type(e).__name__
        out.append(item)
    try:
        captures.goto(page, start_url, wait='domcontentloaded')
    except Exception:
        pass
    return out


def menu_crawl(store, page, max_items=72):
    """Step 10: every main-menu link opened with a real navigation, its result classified, the menu and the landed
    page captured for anything that is not ok. Never judged by a fetch (a firewall answers a burst with 403 pages)."""
    r = store.results
    home = r['pages']['home']
    dealer = domain_of(home)
    sisters = set(store.req.get('sister_sites') or [])
    group_host = domain_of(store.req['group_site']) if store.req.get('group_site') else None
    captures.goto(page, home)
    links = page.evaluate(snippets.MENU_LINKS)[:max_items]
    items = []
    for l in links:
        if store.over_budget():
            store.not_captured('menu crawl', 'store time budget reached; the rest of the menu is unopened')
            break
        item = {'top': l['top'], 'label': l['label'], 'href': l['href'], 'href_host': l['host'], 'path': l['path'], 'status': None, 'result': None,
                'landed_host': None, 'landed_path': None, 'capture_menu': None, 'capture_dest': None}
        try:
            resp = captures.goto(page, l['href'], wait='domcontentloaded')
            page.wait_for_timeout(1200)
            landed = urlparse(page.url)
            item['status'] = resp.status if resp else None
            item['landed_host'] = landed.netloc
            item['landed_path'] = landed.path
            lh = domain_of(page.url)
            body = page.evaluate('() => (document.body.innerText || "").slice(0, 20000)') if lh == dealer else ''
            if (resp and resp.status == 404) or NOT_FOUND.search(page.title() or ''):
                item['result'] = '404'
            elif lh == dealer and landed.path in ('', '/') and l['path'] not in ('', '/'):
                item['result'] = 'home_redirect'
            elif lh == dealer and EMPTY_PAGE.search(body) and not re.search(r'inventory/index|all-inventory', landed.path):
                item['result'] = 'empty'
                item['empty_text'] = EMPTY_PAGE.search(body).group(0).strip()
            elif lh == dealer:
                item['result'] = 'ok'
                item['title'] = (page.title() or '')[:120]
            elif group_host and lh == group_host:
                item['result'] = 'group_site'
            elif lh in sisters:
                item['result'] = 'sister_site'
            elif any(lh.endswith(t) for t in THIRD_PARTY):
                item['result'] = 'third_party'
            else:
                item['result'] = 'offsite'
            if item['result'] != 'ok':
                name = f'dest_{slug(l["label"] or (l["top"] + " " + l["path"]))}.png'
                captures.shot(store, page, name, full_page=False, zoom=config.DEALER_ZOOM)
                item['capture_dest'] = f'captures/{name}'
        except Exception as e:
            item['result'] = 'error'
            item['status'] = f'{type(e).__name__}'
        items.append(item)
    # the menu hovered open for every item that is not ok, boxed in red, shot with the mouse still on it
    captures.goto(page, home)
    page.wait_for_timeout(800)
    for item in items:
        if item['result'] in (None, 'ok', 'error'):
            continue
        try:
            page.mouse.move(config.VIEWPORT['width'] - 1, config.VIEWPORT['height'] - 1)
            page.wait_for_timeout(300)
            geo = page.evaluate(snippets.MENU_GEOMETRY, [item['label'], item.get('href'), item['top']])
            if not geo['item'] and not geo['top']:
                raise RuntimeError('neither the item nor its top entry is in the menu')
            hovered = None
            if geo['top'] and geo['top']['visible']:
                page.mouse.move(geo['top']['cx'], geo['top']['cy'])
                hovered = 'top'
            else:   # under an overflow entry (Dealer Inspire's "More"): hover the visible entries with children, last first
                for ob in reversed(geo['overflow']):
                    page.mouse.move(ob['cx'], ob['cy'])
                    page.wait_for_timeout(600)
                    geo = page.evaluate(snippets.MENU_GEOMETRY, [item['label'], item.get('href'), item['top']])
                    if geo['item'] and geo['item']['visible']:
                        hovered = 'overflow'
                        break
                    if geo['top'] and geo['top']['visible']:
                        page.mouse.move(geo['top']['cx'], geo['top']['cy'])
                        hovered = 'overflow then top'
                        break
            page.wait_for_timeout(700)
            geo = page.evaluate(snippets.MENU_GEOMETRY, [item['label'], item.get('href'), item['top']])
            if geo['item'] and geo['item']['visible'] and hovered != 'top':
                pass   # the item is showing; the mouse stays where it opened the menu
            page.evaluate(snippets.HIDE, config.HIDE_BEFORE_CAPTURE)
            page.evaluate(snippets.MENU_OUTLINE, [item['label'], item.get('href')])
            name = f'menu_{slug(item["label"] or (item["top"] + " " + item["path"]))}.png'
            path = store.captures / name
            page.screenshot(path=str(path), type='png')
            store.record_capture(name, page.url, Image.open(path).size)
            store.log(f'captured {name} (menu open by {hovered or "nothing"}; item visible: {bool(geo["item"] and geo["item"]["visible"])})')
            item['capture_menu'] = f'captures/{name}'
            if not (geo['item'] and geo['item']['visible']):
                item['capture_menu_note'] = 'the item did not show in the open menu; the shot has the menu as it opened'
            page.evaluate(snippets.MENU_OUTLINE, ['', None])
        except Exception as e:
            store.not_captured(f'menu open on {item["label"] or item["path"]}', f'{type(e).__name__}: {str(e)[:160]}')
    r['menu'] = {'items_total': len(links), 'opened': len(items), 'items': items}
    store.check('menu', 'ok')


DEPT_WORDS = {'sales': 'Sales', 'service': 'Service', 'parts': 'Parts', 'collision': 'Collision', 'body': 'Body Shop', 'finance': 'Finance', 'main': 'Main'}


def dept_of(text):
    t = (text or '').lower()
    for k, v in DEPT_WORDS.items():
        if k in t:
            return v
    return None


def fmt_phone(raw):
    digits = re.sub(r'\D', '', raw or '')
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    return f'({digits[:3]}) {digits[3:6]}-{digits[6:]}' if len(digits) == 10 else None


def ampm(t):
    """'19:00' to '7:00pm', the way the site's own hours blocks read."""
    m = re.match(r'^(\d{1,2}):(\d{2})', str(t))
    if not m:
        return str(t)
    h, mi = int(m.group(1)), m.group(2)
    return f'{h % 12 or 12}:{mi}{"am" if h < 12 else "pm"}'


def hours_text(spec):
    """An openingHoursSpecification list as one line per day group: 'Mon to Fri 7:30am to 6:00pm; Sat ...'."""
    if isinstance(spec, str):
        return spec
    if not isinstance(spec, list):
        return None
    out = []
    for h in spec:
        if not isinstance(h, dict):
            continue
        days = h.get('dayOfWeek') or []
        days = [days] if isinstance(days, str) else days
        days = [str(d).split('/')[-1][:3] for d in days]
        span = f'{days[0]} to {days[-1]}' if len(days) > 2 else ' and '.join(days) if days else ''
        if h.get('opens') and h.get('closes'):
            out.append(f'{span} {ampm(h["opens"])} to {ampm(h["closes"])}')
        else:
            out.append(f'{span} closed')
    return '; '.join(out) or None


def walk_ld(obj):
    """Every dict in a JSON-LD document, departments and graphs included."""
    stack = [obj]
    while stack:
        x = stack.pop()
        if isinstance(x, dict):
            yield x
            for k in ('@graph', 'department', 'subOrganization', 'parentOrganization', 'itemListElement', 'location'):
                v = x.get(k)
                if isinstance(v, (list, dict)):
                    stack.append(v)
        elif isinstance(x, list):
            stack.extend(x)


def contact_info(store, page):
    """Step 4: the site's address, hours and phones from the header, footer, hours blocks, tel: links and JSON-LD
    (the whole graph: Dealer.com puts the store as AutomotiveBusiness with AutoDealer, AutoRepair and AutoPartsStore
    departments, each with its own phone and hours)."""
    r = store.results
    captures.goto(page, r['pages']['home'])
    page.wait_for_timeout(1000)
    c = page.evaluate(snippets.CONTACT_TEXT)
    at = store.results['captured_at']
    phones, seen = [], set()

    def add_phone(where, dept, raw):
        num = fmt_phone(raw)
        if num and (num, dept) not in seen:
            seen.add((num, dept))
            phones.append({'where': where, 'dept': dept, 'number': num})
    for t in c['tel']:
        add_phone('site header and footer (tel links)', dept_of(t['text']) or t['text'][:30] or 'unlabeled', t['number'])
    # schema.org: the business and its departments
    schema = {'business': None, 'departments': []}
    addr = None
    for o in [x for ld in c['ld'] for x in walk_ld(ld)]:
        typ = str(o.get('@type', ''))
        if not re.search(r'AutomotiveBusiness|AutoDealer|AutoRepair|AutoPartsStore|AutoBodyShop|LocalBusiness|Organization|Dealer|Store', typ):
            continue
        a = o.get('address')
        a_txt = None
        if isinstance(a, dict):
            parts = [str(a.get(k, '')).strip() for k in ('streetAddress', 'addressLocality', 'addressRegion', 'postalCode')]
            a_txt = re.sub(r'\s+', ' ', f'{parts[0]}, {parts[1]}, {parts[2]} {parts[3]}').strip(' ,')
        elif isinstance(a, str):
            a_txt = a
        rec = {'type': typ, 'name': o.get('name'), 'address': a_txt, 'telephone': o.get('telephone'),
               'hours': hours_text(o.get('openingHoursSpecification') or o.get('openingHours'))}
        if re.search(r'AutoDealer|AutoRepair|AutoPartsStore|AutoBodyShop', typ) and o.get('name') and dept_of(o.get('name')):
            schema['departments'].append(rec)
            add_phone(f'home page schema ({typ} {o.get("name")})', dept_of(o.get('name')), o.get('telephone'))
        elif schema['business'] is None or 'AutomotiveBusiness' in typ:
            schema['business'] = rec
            add_phone(f'home page schema ({typ})', dept_of(o.get('name')) or 'Main', o.get('telephone'))
        addr = addr or a_txt
    addr_src = 'schema.org' if addr else None
    if not addr:
        for blob, src in ((c['header'], 'site header'), (c['footer'], 'site footer')):
            m = re.search(r'\d+\s[^\n]{3,60}?\s*\n?\s*[A-Z][A-Za-z .]+,\s*[A-Z]{2}\s*\d{5}(?:-\d{4})?', '\n'.join(blob))
            if m:
                addr, addr_src = re.sub(r'\s+', ' ', m.group(0)).strip(), src
                break
    hours = {'sales': {'site': None, 'google': None, 'bing': None, 'group_card': None}, 'service': {'site': None, 'google': None, 'bing': None, 'group_card': None},
             'parts': {'site': None, 'google': None, 'bing': None, 'group_card': None}}
    for d in schema['departments']:
        key = (dept_of(d['name']) or '').lower()
        if key in hours and d['hours']:
            hours[key]['site'] = d['hours'] + ' (schema)'
    if schema['business'] and schema['business']['hours'] and not hours['sales']['site']:
        hours['sales']['site'] = schema['business']['hours'] + ' (schema)'
    blocks = []
    for b in c['hoursBlocks']:
        label = dept_of(b.get('heading') or '') or dept_of(b['text'][:60]) or ('Sales' if not blocks else None)
        blocks.append({'where': b['where'], 'label_from': b.get('heading'), 'dept': label, 'text': b['text']})
        if label and label.lower() in hours and not hours[label.lower()].get('site_block'):
            hours[label.lower()]['site_block'] = re.sub(r'\s+', ' ', b['text'])[:300]
    store.results['address_hours'] = {
        'site_address': addr, 'site_address_source': addr_src, 'google_address': None, 'bing_address': None, 'group_card_address': (r.get('group_card') or {}).get('address'),
        'site_name_schema': (schema['business'] or {}).get('name'), 'schema': schema, 'read_at': at,
        'hours': hours, 'hours_blocks': blocks, 'header_text': c['header'], 'footer_text': c['footer'],
        'mismatches': [], 'captures': []}
    store.results['phones'] = phones
    if c['specialHours']:
        holidays = re.findall(r"(Christmas Eve|Christmas Day|Christmas|New Year's Eve|New Year's Day|Thanksgiving|Labor Day|Memorial Day|Independence Day|July 4th|Easter|Good Friday|Veterans Day|Columbus Day|Juneteenth|MLK Day|Presidents'? Day)", c['specialHours'], re.I)
        store.results['special_hours'] = {'where': 'home page', 'text': c['specialHours'][:1200], 'holidays': sorted(set(holidays), key=holidays.index)}
    try:
        # the collapsed Service Hours and Parts Hours panels opened first (read-only toggles), then the block that holds
        # every schedule, so the shot carries all three
        clicked = page.evaluate(snippets.EXPAND_HOURS)
        if clicked:
            page.wait_for_timeout(700)
        hb = page.evaluate(snippets.HOURS_UNION)
        if hb:
            captures.box_shot(store, page, {'x': hb['x'], 'y': hb['y'], 'w': hb['w'], 'h': hb['h']}, 'hours_site.png', pad=12)
            store.results['address_hours']['hours_capture_note'] = f'{hb["blocks"]} hours block(s) in the shot' + (f', {clicked} panel(s) expanded first' if clicked else '')
        else:
            captures.element_shot(store, page, '[class*="ws-hours"], [id*="hours-app"], [class*="hours"], #hours, [id*="hours"]', 'hours_site.png', pad=12)
        store.results['address_hours']['captures'].append('captures/hours_site.png')
    except Exception as e:
        store.not_captured('hours_site.png', str(e))
    if addr:
        try:
            first = re.match(r'\d+\s+\S+', addr)
            zipm = re.search(r'\b\d{5}(?:-\d{4})?\b', addr)
            captures.text_shot(store, page, first.group(0) if first else addr[:12], 'address_site.png', pad=6, also=zipm.group(0) if zipm else None)
            store.results['address_hours']['captures'].append('captures/address_site.png')
        except Exception as e:
            store.not_captured('address_site.png', str(e))
    store.check('contact_info', 'ok')


PAGES = [
    # (key, menu pattern, fallback paths, capture name)
    # (key, menu pattern, fallback paths: Dealer.com's, Dealer Inspire's, DealerOn's .aspx pages, capture name)
    ('specials_service', r'service (&|and) parts specials|service specials|service offers|service coupons', ['/specials/service.htm', '/service-specials/', '/promotions/service/', '/service-parts-specials.html', '/service-specials.aspx'], 'specials_service.png'),
    ('specials_new', r'new (vehicle |car )?specials|new specials|new (vehicle )?(special )?offers|vehicle specials|^specials$', ['/specials/new.htm', '/new-specials/', '/new-vehicle-specials/', '/specials/new-vehicle-specials/', '/specials.aspx', '/newspecials.aspx'], 'specials_new.png'),
    ('schedule_service', r'schedule (service|an appointment)|service appointment|^service$', ['/service/schedule-service.htm', '/schedule-service/', '/serviceappmt.aspx', '/schedule-service.aspx'], 'schedule_service.png'),
    ('trade_in', r'value (your|my) trade|trade[- ]in|^trade$', ['/value-your-trade.htm', '/trade-in/', '/trade', '/tradein.aspx', '/value-your-trade/'], 'trade_in.png'),
    ('finance_app', r'apply for (financing|credit)|finance application|credit app|get pre-?approved|pre-?qualif', ['/finance/apply-for-financing.htm', '/financing/apply/', '/financeapp.aspx', '/finance-application.aspx', '/get-pre-qualified/'], 'finance_app.png'),
    ('about_us', r'about us|about|our dealership', ['/about-us.htm', '/about/', '/dealership/about.htm', '/aboutus.aspx', '/about-us/'], 'about_us.png'),
    ('finance', r'^finance|financing|finance center|finance department', ['/financing/index.htm', '/finance/', '/finance.aspx'], 'finance.png'),
    ('lease', r'lease', ['/lease/', '/financing/lease.htm', '/lease.aspx'], 'lease.png'),
    ('hours_page', r'hours (&|and) directions|hours|^map$|directions', ['/dealership/directions.htm', '/hours-directions/', '/hours.aspx', '/contact-us/', '/contactus.aspx'], 'hours_page.png'),
    ('blog', r'blog|news', ['/blog/', '/news/', '/blog'], 'blog.png'),
]


def pages(store, page):
    """Steps 14 to 16: the pages a shopper uses to act, the content pages, the blog, each captured full-page at zoom
    1.4, with the text flags, the empty-block candidates and the special hours read on each."""
    r = store.results
    home = r['pages']['home']
    r['cx'], r['content'], r['empty_blocks'], r['slider'] = [], [], [], []
    captures.goto(page, home)
    links = page.evaluate(snippets.MENU_LINKS)
    slider = page.evaluate(snippets.SLIDER_ALTS)
    r['slider'] = [{'n': i + 1, 'alt': s['alt'], 'src': s['src'], 'capture': None} for i, s in enumerate(slider)]
    opened = []
    for key, pat, fallbacks, name in PAGES:
        if store.over_budget():
            break
        link = next((l for l in links if re.search(pat, l['label'], re.I) and l['host'] == urlparse(home).netloc), None)
        cands = ([link['href']] if link else []) + [urljoin(home, p) for p in fallbacks]
        url = None
        for c in cands:
            try:
                resp = captures.goto(page, c, wait='domcontentloaded')
                if resp and resp.status == 200 and not NOT_FOUND.search(page.title() or ''):
                    url = page.url
                    break
            except Exception:
                continue
        if not url:
            store.not_captured(key, 'no such page in the menu or at the usual paths')
            continue
        page.wait_for_timeout(1000)
        captures.shot(store, page, name, full_page=True, zoom=config.DEALER_ZOOM)
        text = page.evaluate('() => document.body.innerText')
        entry = {'page': key, 'url': url, 'capture': f'captures/{name}', 'text_flags': [m.group(0) for m in SPECIALS_EMPTY.finditer(text)][:3], 'first_300': re.sub(r'\s+', ' ', text)[:300]}
        if key.startswith('specials'):
            sc = page.evaluate(snippets.SPECIALS_CARDS)
            entry['cards'] = sc['cards']
            entry['card_group'] = sc['card_group']
            entry['h1'] = sc['h1']
            entry['content_text_chars'] = sc['main_text_chars']
            entry['content_images'] = sc['content_images']
            if not sc['cards'] and sc['main_text_chars'] < 400:
                entry['text_flags'].append(f'looks empty: no offer cards, {sc["main_text_chars"]} characters of page content, {"no H1" if not sc["h1"] else "H1 " + sc["h1"]}')
            entry['vendor_banners'] = page.evaluate("""() => [...document.querySelectorAll('img[alt], img[title]')].map(i => (i.alt || '') + ' ' + (i.title || '')).map(a => a.trim()).filter(a => /sunbit|affirm|kbb|carfax|autocheck|synchrony|drive ?plus|cannon|service now/i.test(a)).slice(0, 10)""")
            r['cx'].append(entry)
        elif key in ('about_us', 'finance', 'lease'):
            r['content'].append(entry)
            if key == 'about_us':
                r['about_us_first_para'] = entry['first_300']
        elif key == 'blog':
            # posts: distinct post links inside the post wrappers (one post can sit in several nested wrappers)
            posts = page.evaluate("""() => { const wr = [...document.querySelectorAll('article, .post, [class*="blog-post"], [class*="entry"], [class*="post-item"], [class*="blog-item"]')];
                const hrefs = new Set(); for (const w of wr) for (const a of w.querySelectorAll('a[href]')) { const t = (a.innerText || '').trim(); if (t.length > 8 && !/read more|continue/i.test(t) && /\\/(blog|news|post)/i.test(a.href)) hrefs.add(a.href.split('?')[0]); }
                if (hrefs.size) return hrefs.size; const titled = wr.filter(w => w.querySelector('h1,h2,h3,h4') && !wr.some(o => o !== w && o.contains(w))); return titled.length; }""")
            nop = re.search(r'no posts|nothing found|no results|sorry, no [^\n]{0,60}available|check back', text, re.I)
            r['blog'] = {'url': url, 'posts': posts, 'no_posts_text': nop.group(0) if nop else None, 'capture': f'captures/{name}'}
        elif key == 'hours_page':
            sp = page.evaluate(snippets.CONTACT_TEXT).get('specialHours')
            if sp:
                holidays = re.findall(r"(Christmas Eve|Christmas Day|Christmas|New Year's Eve|New Year's Day|Thanksgiving|Labor Day|Memorial Day|Independence Day|Easter|Veterans Day|Juneteenth)", sp, re.I)
                r['special_hours'] = {'where': 'hours page', 'text': sp[:1200], 'holidays': sorted(set(holidays), key=holidays.index), 'capture': f'captures/{name}'}
        else:
            r['cx'].append(entry)
        # a Dealership Info sidebar: its text, and any holiday named in it counts as special hours
        try:
            di = page.evaluate(snippets.DEALERSHIP_INFO)
            if di and not r.get('dealership_info'):
                hol = re.findall(HOLIDAYS, di['text'], re.I)
                r['dealership_info'] = {'page': key, 'url': url, 'text': di['text'][:2000], 'holidays': sorted(set(hol), key=hol.index), 'capture': f'captures/{name}'}
                if hol and not r.get('special_hours'):
                    r['special_hours'] = {'where': f'Dealership Info sidebar on the {key} page', 'text': di['text'][:1200], 'holidays': sorted(set(hol), key=hol.index), 'capture': f'captures/{name}'}
        except Exception as e:
            store.not_captured(f'dealership info on {key}', str(e))
        # empty-block candidates on this page, with the page captured and each candidate boxed
        try:
            broken = page.evaluate(snippets.BROKEN_IMAGES)
            if broken:
                entry['broken_images'] = broken
            blocks = page.evaluate(snippets.EMPTY_BLOCKS)
            for b in blocks:
                b['method'] = 'DOM: no text, no media, no background image'
            # and the flat bands in the capture itself (a banner with no image set still carries invisible heading text)
            bands = captures.blank_regions(store.captures / name, zoom=config.DEALER_ZOOM)
            for b in bands:
                z = config.DEALER_ZOOM
                blocks.append({'x': round(b['x'] / z), 'y': round(b['y'] / z), 'w': round(b['w'] / z), 'h': round(b['h'] / z), 'tag': None, 'id': None, 'cls': None, 'color': b['color'], 'method': b['method']})
            if blocks:
                # the page's own zoom-1.4 capture with each candidate boxed in its pixels (DOM boxes scaled by the zoom)
                ename = f'empty_{key}.png'
                z = config.DEALER_ZOOM
                (store.captures / ename).write_bytes((store.captures / name).read_bytes())
                store.record_capture(ename, url, Image.open(store.captures / ename).size)
                for b in blocks:
                    captures.red_box(store, ename, (round(b['x'] * z), round(b['y'] * z), round((b['x'] + b['w']) * z), round((b['y'] + b['h']) * z)))
                    r['empty_blocks'].append({'page': key, 'url': url, **{k: b.get(k) for k in ('x', 'y', 'w', 'h', 'tag', 'id', 'cls', 'color', 'method')}, 'capture': f'captures/{ename}'})
        except Exception as e:
            store.not_captured(f'empty blocks on {key}', str(e))
        opened.append(key)
    # every other page the Specials menu opens (Parts, Accessory, Tire specials), captured the same way
    specials_menu = [l for l in links if (re.search(r'special|offer', l['top'] or '', re.I) or re.search(r'special|coupon', l['label'], re.I)) and l['host'] == urlparse(home).netloc
                     and not re.search(r'/inventory/|/new/|/used/', l['path']) and l['href'] not in {c['url'] for c in r['cx']}][:10]
    for l in specials_menu:
        if store.over_soft_budget():
            store.not_captured(f'specials page {l["label"]}', 'soft time budget reached')
            continue
        key = 'specials_' + slug(re.sub(r'\bspecials?\b', '', l['label'], flags=re.I).strip() or l['label'])
        if any(c['page'] == key for c in r['cx']):
            continue
        try:
            resp = captures.goto(page, l['href'], wait='domcontentloaded')
            page.wait_for_timeout(1000)
            if not resp or resp.status != 200 or NOT_FOUND.search(page.title() or '') or page.url in {c['url'] for c in r['cx']}:
                continue
            name = f'{key}.png'
            captures.shot(store, page, name, full_page=True, zoom=config.DEALER_ZOOM)
            text = page.evaluate('() => document.body.innerText')
            sc = page.evaluate(snippets.SPECIALS_CARDS)
            entry = {'page': key, 'label': l['label'], 'menu': l['top'], 'url': page.url, 'capture': f'captures/{name}', 'text_flags': [m.group(0) for m in SPECIALS_EMPTY.finditer(text)][:3],
                     'cards': sc['cards'], 'h1': sc['h1'], 'content_text_chars': sc['main_text_chars'], 'content_images': sc['content_images'], 'first_300': re.sub(r'\s+', ' ', text)[:300]}
            if not sc['cards'] and sc['main_text_chars'] < 400:
                entry['text_flags'].append(f'looks empty: no offer cards, {sc["main_text_chars"]} characters of page content, {"no H1" if not sc["h1"] else "H1 " + sc["h1"]}')
            r['cx'].append(entry)
        except Exception as e:
            store.not_captured(f'specials page {l["label"]}', str(e))
    # every page the Research menu opens (model research pages), and research pages elsewhere in the menu by path
    research = [l for l in links if (re.search(r'research|model', l['top'] or '', re.I) or re.search(r'research', l['path'] + ' ' + l['label'], re.I)) and l['host'] == urlparse(home).netloc][:12]
    for l in research:
        if store.over_soft_budget():
            store.not_captured(f'research page {l["label"]}', 'soft time budget reached')
            continue
        try:
            captures.goto(page, l['href'], wait='domcontentloaded')
            page.wait_for_timeout(800)
            name = f'research_{slug(l["label"])}.png'
            captures.shot(store, page, name, full_page=True, zoom=config.DEALER_ZOOM)
            text = page.evaluate('() => document.body.innerText')
            years = sorted(set(re.findall(r'\b(20[2-3]\d)\b', text)))
            entry = {'page': 'research', 'label': l['label'], 'url': page.url, 'capture': f'captures/{name}', 'model_years': years, 'first_300': re.sub(r'\s+', ' ', text)[:300]}
            # every model card's link on the page (LEARN MORE, View Details, the model name), opened the way the menu is
            # crawled: 404, home redirect, off-site, or ok. Natchez Nissan's LEAF card opened /2024-nissan-leaf.html, a 404.
            cards = page.evaluate(snippets.RESEARCH_CARD_LINKS)
            entry['card_links'] = crawl_links(store, page, cards, dealer=domain_of(home), prefix=f'research_{slug(l["label"])}', max_links=24)
            r['cx'].append(entry)
            if entry['card_links']:
                r.setdefault('research_links', []).extend([{**c, 'research_page': page.url if False else entry['url']} for c in entry['card_links']])
        except Exception as e:
            store.not_captured(f'research page {l["label"]}', str(e))
    store.check('pages', 'ok')
