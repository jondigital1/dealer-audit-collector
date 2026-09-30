"""The dealer site checks: set-up (the three pages), SEO META fields, vehicle links and inventory count, the menu
crawl, address, hours and phones, the customer-experience and content pages, the blog, the slider, empty blocks and
special hours. Each function records into store.results and saves; a failure marks the check and moves on."""
import re
from urllib.parse import urljoin, urlparse

from . import captures, config, snippets
from .store import domain_of

NEW_SRP_PATHS = ['/new-inventory/index.htm', '/new-inventory/', '/new-vehicles/', '/inventory/new/', '/new/', '/searchnew.aspx', '/new-inventory']
NOT_FOUND = re.compile(r'\b404\b|page not found|not found|no longer available', re.I)
SPECIALS_EMPTY = re.compile(r'NO RESULTS|No vehicles found|We are currently updating|no specials|currently no', re.I)
THIRD_PARTY = ('commercialtrucktrader.com', 'cars.com', 'autotrader.com', 'carfax.com', 'expressoil.com')


def slug(s):
    return re.sub(r'[^a-z0-9]+', '_', s.lower()).strip('_')[:40] or 'item'


def setup_pages(store, page):
    """Step 1: the home page, the new inventory SRP and the first in-stock new VDP with a real price."""
    r = store.results
    home = r['pages']['home']
    resp = captures.goto(page, home)
    r['preflight'] = r['preflight'] or {}
    r['pages']['home'] = page.url
    # the SRP: the New menu item first, then the usual paths
    links = page.evaluate(snippets.MENU_LINKS)
    new_item = next((l for l in links if re.search(r'^(new|view new|new inventory|new vehicles|shop new)', l['label'], re.I) and 'specials' not in l['path']), None)
    srp = new_item['href'] if new_item else None
    if not srp:
        for p in NEW_SRP_PATHS:
            try:
                rr = captures.goto(page, urljoin(page.url, p))
                if rr and rr.status == 200 and not NOT_FOUND.search(page.title()):
                    srp = page.url
                    break
            except Exception:
                continue
    if not srp:
        store.check('setup_srp', 'failed', 'could not find the new inventory SRP; give the URL in the request')
        return
    captures.goto(page, srp)
    r['pages']['srp'] = page.url
    txt = page.evaluate('() => document.body.innerText')
    m = re.search(r'(\d[\d,]*)\s+(new\s+)?(vehicles?|results?|matches?|cars?)', txt, re.I)
    if m:
        r['pages']['srp_new_count'] = int(m.group(1).replace(',', ''))
        r['pages']['srp_new_count_text'] = m.group(0)
    try:
        captures.element_shot(store, page, 'h1, .srp-header, [class*="results-count"], [class*="inventory-count"]', 'srp_header.png', pad=20)
    except Exception as e:
        store.not_captured('srp_header.png', str(e))
    # the first vehicle card with a price
    vdp = page.evaluate("""() => { const money = /\\$\\s?\\d[\\d,]{3,}/; for (const a of document.querySelectorAll('a[href*="/inventory/"], a[href*="/new/"], a[href*="/vehicle"]')) {
        const card = a.closest('li, article, [class*="card"], [class*="vehicle"]') || a; if (money.test(card.innerText || '')) return { href: a.href, text: (card.innerText || '').trim().slice(0, 160) }; } return null; }""")
    if not vdp:
        store.check('setup_vdp', 'failed', 'no vehicle card with a price on the SRP')
        return
    captures.goto(page, vdp['href'])
    r['pages']['vdp'] = page.url
    r['pages']['vdp_vehicle'] = re.sub(r'\s+', ' ', vdp['text'])[:120]
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
            rec = {'title': m['title'], 'title_len': m['titleLen'], 'meta': m['meta'], 'meta_len': m['metaLen'], 'h': m['h'], 'h1_visible': m['h1Visible']}
            if key == 'home':
                rec.update({'images': m['images'], 'no_alt': m['noAlt'], 'no_title': m['noTitle']})
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
        page.evaluate(snippets.SCROLL_PASS)
        l = page.evaluate(snippets.SRP_LINKS)
        store.results['links'] = {'srp_vehicle_links': l['links'], 'srp_http_links': l['http'], 'example_http_link': l['example']}
        store.check('srp_links', 'ok')
    except Exception as e:
        store.check('srp_links', 'failed', str(e))


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
        item = {'top': l['top'], 'label': l['label'], 'href_host': l['host'], 'path': l['path'], 'status': None, 'result': None,
                'landed_host': None, 'landed_path': None, 'capture_menu': None, 'capture_dest': None}
        try:
            resp = captures.goto(page, l['href'], wait='domcontentloaded')
            page.wait_for_timeout(1200)
            landed = urlparse(page.url)
            item['status'] = resp.status if resp else None
            item['landed_host'] = landed.netloc
            item['landed_path'] = landed.path
            lh = domain_of(page.url)
            if (resp and resp.status == 404) or NOT_FOUND.search(page.title() or ''):
                item['result'] = '404'
            elif lh == dealer and landed.path in ('', '/') and l['path'] not in ('', '/'):
                item['result'] = 'home_redirect'
            elif lh == dealer:
                item['result'] = 'ok'
            elif group_host and lh == group_host:
                item['result'] = 'group_site'
            elif lh in sisters:
                item['result'] = 'sister_site'
            elif any(lh.endswith(t) for t in THIRD_PARTY):
                item['result'] = 'third_party'
            else:
                item['result'] = 'offsite'
            if item['result'] != 'ok':
                name = f'dest_{slug(l["label"])}.png'
                captures.shot(store, page, name, full_page=False, zoom=config.DEALER_ZOOM)
                item['capture_dest'] = f'captures/{name}'
        except Exception as e:
            item['result'] = 'error'
            item['status'] = f'{type(e).__name__}'
        items.append(item)
    # the menu hovered open for every item that is not ok
    captures.goto(page, home)
    for item in items:
        if item['result'] in (None, 'ok', 'error') or not item['top']:
            continue
        try:
            top = page.get_by_text(item['top'], exact=False).first
            top.hover()
            page.wait_for_timeout(700)
            page.evaluate("""(label) => { for (const a of document.querySelectorAll('nav a, header a')) if (a.innerText.trim() === label) { a.style.outline = '3px solid #D93025'; a.style.outlineOffset = '2px'; } }""", item['label'])
            name = f'menu_{slug(item["label"])}.png'
            captures.shot(store, page, name)
            item['capture_menu'] = f'captures/{name}'
            page.mouse.move(config.VIEWPORT['width'] - 1, 10)
        except Exception as e:
            store.not_captured(f'menu open on {item["label"]}', str(e))
    r['menu'] = {'items_total': len(links), 'opened': len(items), 'items': items}
    store.check('menu', 'ok')


def contact_info(store, page):
    """Step 4: the site's address, hours and phones from the header, footer, hours blocks, tel: links and JSON-LD."""
    captures.goto(page, store.results['pages']['home'])
    c = page.evaluate(snippets.CONTACT_TEXT)
    phones = []
    for t in c['tel']:
        digits = re.sub(r'\D', '', t['number'])[-10:]
        if len(digits) == 10:
            phones.append({'where': 'tel link', 'dept': t['text'][:40], 'number': f'({digits[:3]}) {digits[3:6]}-{digits[6:]}'})
    ld_dealer = None
    for obj in c['ld']:
        for o in (obj if isinstance(obj, list) else [obj]):
            if isinstance(o, dict) and str(o.get('@type', '')).lower().endswith(('dealer', 'autodealer', 'localbusiness', 'organization')):
                ld_dealer = o
                break
    addr = None
    if ld_dealer and isinstance(ld_dealer.get('address'), dict):
        a = ld_dealer['address']
        addr = ' '.join(str(a.get(k, '')) for k in ('streetAddress', 'addressLocality', 'addressRegion', 'postalCode')).strip()
    store.results['address_hours'] = {
        'site_address': addr, 'site_address_source': 'schema.org' if addr else None, 'google_address': None, 'bing_address': None, 'group_card_address': None,
        'site_name_schema': ld_dealer.get('name') if ld_dealer else None,
        'schema_hours': ld_dealer.get('openingHours') or ld_dealer.get('openingHoursSpecification') if ld_dealer else None,
        'hours_blocks': c['hoursBlocks'], 'header_text': c['header'], 'footer_text': c['footer'],
        'hours': {'sales': {'site': None, 'google': None, 'bing': None, 'group_card': None}, 'service': {'site': None, 'google': None, 'bing': None, 'group_card': None}, 'parts': {'site': None, 'google': None, 'bing': None, 'group_card': None}},
        'mismatches': [], 'captures': []}
    store.results['phones'] = phones
    if c['specialHours']:
        holidays = re.findall(r"(Christmas Eve|Christmas Day|Christmas|New Year's Eve|New Year's Day|Thanksgiving|Labor Day|Memorial Day|Independence Day|July 4th|Easter|Good Friday|Veterans Day|Columbus Day|Juneteenth|MLK Day|Presidents'? Day)", c['specialHours'], re.I)
        store.results['special_hours'] = {'where': 'home page', 'text': c['specialHours'][:1200], 'holidays': sorted(set(holidays), key=holidays.index)}
    try:
        captures.element_shot(store, page, '[class*="hours"], #hours, [id*="hours"]', 'hours_site.png', pad=12)
        store.results['address_hours']['captures'].append('captures/hours_site.png')
    except Exception as e:
        store.not_captured('hours_site.png', str(e))
    store.check('contact_info', 'ok')


PAGES = [
    # (key, menu pattern, fallback paths, capture name)
    ('specials_service', r'service (&|and) parts specials|service specials|service offers|service coupons', ['/specials/service.htm', '/service-specials/', '/promotions/service/'], 'specials_service.png'),
    ('specials_new', r'new (vehicle )?specials|new specials|special offers', ['/specials/new.htm', '/new-specials/'], 'specials_new.png'),
    ('schedule_service', r'schedule (service|an appointment)|service appointment', ['/service/schedule-service.htm', '/schedule-service/'], 'schedule_service.png'),
    ('trade_in', r'value (your|my) trade|trade[- ]in', ['/value-your-trade.htm', '/trade-in/'], 'trade_in.png'),
    ('finance_app', r'apply for (financing|credit)|finance application|credit app', ['/finance/apply-for-financing.htm', '/financing/apply/'], 'finance_app.png'),
    ('about_us', r'about us|about', ['/about-us.htm', '/about/', '/dealership/about.htm'], 'about_us.png'),
    ('finance', r'^finance|financing|finance center', ['/financing/index.htm', '/finance/'], 'finance.png'),
    ('lease', r'lease', ['/lease/', '/financing/lease.htm'], 'lease.png'),
    ('hours_page', r'hours (&|and) directions|hours', ['/dealership/directions.htm', '/hours-directions/'], 'hours_page.png'),
    ('blog', r'blog|news', ['/blog/', '/news/'], 'blog.png'),
]


def pages(store, page):
    """Steps 14 to 16: the pages a shopper uses to act, the content pages, the blog, each captured full-page at zoom
    1.4, with the text flags, the empty-block candidates and the special hours read on each."""
    r = store.results
    home = r['pages']['home']
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
            entry['cards'] = page.evaluate("""() => [...document.querySelectorAll('[class*="special"], [class*="offer"], [class*="coupon"], article, .card')].slice(0, 30).map(c => ({
                title: ((c.querySelector('h1,h2,h3,h4') || {}).innerText || '').trim().slice(0, 100), price_text: ((c.innerText || '').match(/\\$?\\s?\\d[\\d,]*(\\.\\d\\d)?/) || [''])[0], has_image: !!c.querySelector('img') })).filter(c => c.title)""")
            entry['vendor_banners'] = page.evaluate("""() => [...document.querySelectorAll('img[alt]')].map(i => i.alt).filter(a => /sunbit|affirm|kbb|carfax|autocheck|synchrony|drive ?plus/i.test(a)).slice(0, 10)""")
            r['cx'].append(entry)
        elif key in ('about_us', 'finance', 'lease'):
            r['content'].append(entry)
            if key == 'about_us':
                r['about_us_first_para'] = entry['first_300']
        elif key == 'blog':
            posts = page.evaluate("""() => document.querySelectorAll('article, .post, [class*="blog-post"], [class*="entry"]').length""")
            nop = re.search(r'no posts|nothing found|no results', text, re.I)
            r['blog'] = {'url': url, 'posts': posts, 'no_posts_text': nop.group(0) if nop else None, 'capture': f'captures/{name}'}
        elif key == 'hours_page':
            sp = page.evaluate(snippets.CONTACT_TEXT).get('specialHours')
            if sp:
                holidays = re.findall(r"(Christmas Eve|Christmas Day|Christmas|New Year's Eve|New Year's Day|Thanksgiving|Labor Day|Memorial Day|Independence Day|Easter|Veterans Day|Juneteenth)", sp, re.I)
                r['special_hours'] = {'where': 'hours page', 'text': sp[:1200], 'holidays': sorted(set(holidays), key=holidays.index), 'capture': f'captures/{name}'}
        else:
            r['cx'].append(entry)
        # empty-block candidates on this page, with the page captured and each candidate boxed
        try:
            blocks = page.evaluate(snippets.EMPTY_BLOCKS)
            if blocks:
                ename = f'empty_{key}.png'
                captures.shot(store, page, ename, full_page=True)
                for b in blocks:
                    captures.red_box(store, ename, (b['x'], b['y'], b['x'] + b['w'], b['y'] + b['h']))
                    r['empty_blocks'].append({'page': key, 'url': url, **{k: b[k] for k in ('x', 'y', 'w', 'h', 'tag', 'id', 'cls')}, 'capture': f'captures/{ename}'})
        except Exception as e:
            store.not_captured(f'empty blocks on {key}', str(e))
        opened.append(key)
    # every page the Research menu opens (model research pages)
    research = [l for l in links if re.search(r'research|model', l['top'] or '', re.I) and l['host'] == urlparse(home).netloc][:12]
    for l in research:
        if store.over_budget():
            break
        try:
            captures.goto(page, l['href'], wait='domcontentloaded')
            page.wait_for_timeout(800)
            name = f'research_{slug(l["label"])}.png'
            captures.shot(store, page, name, full_page=True, zoom=config.DEALER_ZOOM)
            text = page.evaluate('() => document.body.innerText')
            years = sorted(set(re.findall(r'\b(20[2-3]\d)\b', text)))
            r['cx'].append({'page': 'research', 'label': l['label'], 'url': page.url, 'capture': f'captures/{name}', 'model_years': years, 'first_300': re.sub(r'\s+', ' ', text)[:300]})
        except Exception as e:
            store.not_captured(f'research page {l["label"]}', str(e))
    store.check('pages', 'ok')
