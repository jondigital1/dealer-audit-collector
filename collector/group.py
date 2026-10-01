"""Phase 4, step 2: group sites. For a group request (group_site plus stores, each with its sister_sites), the group
site gets the home-page PageSpeed run (the same rule as a store: numbers, gauges, field cards, treemap and GTM count),
its new inventory count, and every store card wherever cards appear (the home page, a locations page, the Finance and
Service pages): the card's name, address, hours and phone as printed, and where each card link lands after redirects
(a redirect domain instead of the store's live domain is the finding, as on Chief). Then each store's address and
hours are compared across its own site, Bing, the sister sites' pages that name it and the group site's cards, every
mismatch recorded with its captures. Group-site pages are captured like store pages (full page, scrolled once)."""
import re
from urllib.parse import urlparse

from . import captures, config, flags, pagespeed, preflight, site, snippets
from .flags import address_key, norm_hours
from .store import Store, domain_of, now_et

CARD_PAGES = re.compile(r'location|dealership|our-stores|stores|dealers|finance|service|contact|about|hours|directions', re.I)
PHONE = re.compile(r'\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}')
ADDRESS = re.compile(r'\d+\s[^\n]*?,?\s*[A-Z][A-Za-z .]+,\s*[A-Z]{2}\s*\d{5}(?:-\d{4})?')

# Every block on the page naming one of the stores with a phone number or a zip code in it, innermost first; a hidden
# block (a map info window) is kept with its text, a visible one with its box for the capture
GROUP_CARDS = """(names) => { const vis = e => { const r = e.getBoundingClientRect(); return r.width > 120 && r.height > 20; };
  const contact = /\\(?\\d{3}\\)?[\\s.-]\\d{3}[\\s.-]\\d{4}|\\b\\d{5}(-\\d{4})?\\b/; const txt = e => (e.innerText && e.innerText.trim()) ? e.innerText : (e.textContent || ''); const out = [];
  for (const name of names) { const els = [...document.querySelectorAll('body *')].filter(e => e.children.length < 60 && txt(e).includes(name) && txt(e).length < 1500 && contact.test(txt(e)));
    const inner = els.filter(e => !els.some(o => o !== e && e.contains(o)));
    for (const c of inner) { const r = c.getBoundingClientRect(); out.push({ name, visible: vis(c), where: c.tagName.toLowerCase() + '.' + (c.className || '').toString().trim().split(/\\s+/).slice(0, 2).join('.'),
      text: txt(c).replace(/[ \\t]+/g, ' ').replace(/\\n\\s*\\n+/g, '\\n').trim().slice(0, 1200), links: [...c.querySelectorAll('a[href]')].map(a => ({ text: (a.innerText || '').trim().slice(0, 40), href: a.href })).filter(l => !/^(tel|mailto|javascript)/.test(l.href)).slice(0, 6),
      box: { x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height } }); } }
  return out; }"""


def parse_card(text):
    """The address, phone(s) and hours lines as printed on a card."""
    t = text.replace('\u00a0', ' ')
    m = ADDRESS.search(t.replace('\n', ' '))
    hours = [ln.strip() for ln in t.split('\n') if re.search(r'\b(mon|tue|wed|thu|fri|sat|sun)[a-z]*\b', ln, re.I) and re.search(r'am|pm|closed|\d{1,2}:\d{2}', ln, re.I)]
    return {'address': re.sub(r'\s+', ' ', m.group(0)).strip() if m else None, 'phones': PHONE.findall(t)[:4], 'hours_lines': hours[:14]}


def land(page, href):
    """Where a link lands after redirects: status, final host and path."""
    try:
        resp = captures.goto(page, href, wait='domcontentloaded')
        page.wait_for_timeout(800)
        return {'status': resp.status if resp else None, 'final_host': urlparse(page.url).netloc, 'final_path': urlparse(page.url).path}
    except Exception as e:
        return {'status': None, 'error': f'{type(e).__name__}: {str(e)[:120]}'}


def scan_pages(store, page, base_url, names, prefix, max_pages=8, land_links=True, store_domains=None):
    """The home page and every card-bearing page under the menu: each captured full page, each card naming a store
    recorded, visible cards captured, each card link's landing resolved."""
    r = store.results
    captures.goto(page, base_url)
    page.wait_for_timeout(1500)
    links = page.evaluate(snippets.MENU_LINKS)
    host = urlparse(page.url).netloc
    urls = [page.url] + [l['href'] for l in links if l['host'] == host and CARD_PAGES.search(l['label'] + ' ' + l['path']) and l['href'] != page.url]
    seen, cards, pages = set(), [], []
    for url in urls:
        if store.over_budget() or len(pages) >= max_pages:
            break
        u = url.split('#')[0]
        if u in seen:
            continue
        seen.add(u)
        try:
            if page.url != u:
                captures.goto(page, u, wait='domcontentloaded')
                page.wait_for_timeout(1200)
            name = f'{prefix}_{site.slug(urlparse(page.url).path.strip("/") or "home")}.png'
            found = page.evaluate(GROUP_CARDS, names)
            if found or len(pages) == 0:
                captures.shot(store, page, name, full_page=True, zoom=config.DEALER_ZOOM)
            pages.append({'url': page.url, 'title': (page.title() or '')[:100], 'capture': f'captures/{name}' if (found or len(pages) == 0) else None, 'cards': len(found)})
            for i, c in enumerate(found):
                card = {'store': c['name'], 'page': page.url, 'visible': c['visible'], 'where': c['where'], 'text': c['text'], **parse_card(c['text']), 'links': c['links'], 'capture': None, 'read_at': now_et()}
                if c['visible']:
                    try:
                        cname = f'{prefix}_card_{site.slug(c["name"])}_{site.slug(urlparse(page.url).path.strip("/") or "home")}_{i + 1}.png'
                        captures.box_shot(store, page, c['box'], cname, pad=10)
                        card['capture'] = f'captures/{cname}'
                    except Exception as e:
                        store.not_captured(cname, str(e))
                cards.append(card)
        except Exception as e:
            pages.append({'url': u, 'error': f'{type(e).__name__}: {str(e)[:120]}'})
    # where each card link lands (one navigation per distinct href)
    if land_links:
        landed = {}
        for card in cards:
            dom = (store_domains or {}).get(card['store'])
            for l in card['links']:
                if l['href'] not in landed:
                    landed[l['href']] = land(page, l['href'])
                l.update(landed[l['href']])
                l['host'] = urlparse(l['href']).netloc
                if dom:
                    l['points_at_live_domain'] = domain_of(l['href']) == dom
                    l['lands_on_live_domain'] = domain_of('https://' + (l.get('final_host') or '')) == dom if l.get('final_host') else None
                    l['redirect_domain'] = bool(l.get('final_host')) and not l['points_at_live_domain'] and l['lands_on_live_domain']
    return pages, cards


def new_count(store, page, base_url):
    """The group site's new inventory count, when it has an inventory page."""
    captures.goto(page, base_url)
    links = page.evaluate(snippets.MENU_LINKS)
    item = site.pick_new_srp(links)
    cands = ([item['href']] if item else []) + [base_url.rstrip('/') + p for p in site.NEW_SRP_PATHS]
    for c in cands[:6]:
        try:
            resp = captures.goto(page, c, wait='domcontentloaded')
            if not resp or resp.status != 200 or site.NOT_FOUND.search(page.title() or ''):
                continue
            page.wait_for_timeout(1500)
            cnt = page.evaluate(site.SRP_COUNT)
            m = re.search(r'(\d[\d,]*)\s*(new\s+)?(vehicles?|results?|matches?|cars?|listings?)', cnt['el'] or '', re.I) or re.search(r'(\d[\d,]*)\s+(new\s+)?(vehicles?|results?|matches?|cars?|listings?)', cnt['body'], re.I)
            if m:
                return {'url': page.url, 'count': int(m.group(1).replace(',', '')), 'text': m.group(0), 'read_at': now_et()}
            return {'url': page.url, 'count': None, 'text': None, 'note': 'inventory page found, no count read'}
        except Exception:
            continue
    return None


def run(spec, out_dir, plat):
    """The group site's run, into DIR/group/: pre-flight, PageSpeed home, the new count, the store cards everywhere
    they appear with their link landings, then each sister site's pages that name a store."""
    stores = spec.get('stores') or []
    names = [s['store'] for s in stores]
    store_domains = {s['store']: domain_of(s['url']) for s in stores}
    req = {'store': spec.get('group') or 'group site', 'url': spec['group_site'], 'group': spec.get('group'), 'group_site': None, 'stores': names}
    gs = Store(req, out_dir, folder='group')
    gs.results['group_cards'] = []
    gs.results['group_pages'] = []
    gs.results['sister_cards'] = []
    gs.log(f'group site {spec["group_site"]} for {len(stores)} stores')
    try:
        with captures.Browser() as b:
            ctx = b.context()
            page = ctx.new_page()
            pf = preflight.run(gs, page, plat)
            if pf and pf['loads'] and pf.get('platform_headless') != 'chrome_only':
                base = page.url
                gs.results['pages']['home'] = base
                rp = ctx.new_page()
                try:
                    pagespeed.home(gs, rp, base)
                except Exception as e:
                    gs.check('pagespeed_home', 'failed', f'{type(e).__name__}: {str(e)[:200]}')
                rp.close()
                try:
                    gs.results['group_new_count'] = new_count(gs, page, base)
                    gs.check('group_new_count', 'ok' if gs.results['group_new_count'] and gs.results['group_new_count'].get('count') is not None else 'failed', None if gs.results['group_new_count'] else 'no inventory page found on the group site')
                except Exception as e:
                    gs.check('group_new_count', 'failed', str(e)[:200])
                try:
                    pages, cards = scan_pages(gs, page, base, names, 'group', store_domains=store_domains)
                    gs.results['group_pages'] = pages
                    gs.results['group_cards'] = cards
                    gs.check('group_cards', 'ok' if cards else 'failed', None if cards else 'no store card found on the group site\'s pages')
                except Exception as e:
                    gs.check('group_cards', 'failed', f'{type(e).__name__}: {str(e)[:200]}')
                gs.save()
            # the sister sites' pages that name each store (each store's sister sites: the group's other stores and any listed)
            try:
                sisters = {}
                for s in stores:
                    for d in [domain_of(o['url']) for o in stores if o is not s] + [domain_of(x) for x in (s.get('sister_sites') or spec.get('sister_sites') or [])]:
                        sisters.setdefault(d, set()).add(s['store'])
                for d, who in sisters.items():
                    if gs.over_budget():
                        break
                    try:
                        pages, cards = scan_pages(gs, page, f'https://{d}', sorted(who), f'sister_{site.slug(d)}', max_pages=5, land_links=False)
                        for c in cards:
                            c['sister_site'] = d
                        gs.results['sister_cards'].extend(cards)
                        gs.results.setdefault('sister_pages', []).extend([{**p, 'sister_site': d} for p in pages])
                    except Exception as e:
                        gs.not_captured(f'sister site {d}', f'{type(e).__name__}: {str(e)[:120]}')
                gs.check('sister_cards', 'ok')
            except Exception as e:
                gs.check('sister_cards', 'failed', f'{type(e).__name__}: {str(e)[:200]}')
            ctx.close()
    except Exception as e:
        gs.check('browser', 'failed', f'{type(e).__name__}: {str(e)[:300]}')
    # group-level flags: a card link that points at a redirect domain instead of the store's live domain
    for c in gs.results['group_cards']:
        for l in c['links']:
            if l.get('redirect_domain'):
                gs.flag('group_card_redirect_domain', 'Group Site', l['host'], store_domains.get(c['store']), f'The group site\'s card for {c["store"]} points at {l["host"]}, a redirect domain, not {store_domains.get(c["store"])}', [c.get('capture') or next((p.get('capture') for p in gs.results['group_pages'] if p.get('url') == c['page']), None)])
    captures.contact_sheet(gs)
    gs.finish()
    return gs


def compare(spec, out_dir, group_results):
    """Each store's address and hours across its own site, Bing, the sister sites' pages that name it and the group
    site's cards; every mismatch into the store's results.json (cross_site) with its captures, and a flag."""
    import json
    from pathlib import Path
    for s in spec.get('stores') or []:
        d = domain_of(s['url'])
        path = Path(out_dir) / d / 'results.json'
        if not path.exists():
            continue
        st = Store(s, out_dir)
        st.results = json.loads(path.read_text())
        r = st.results
        ah = r.get('address_hours') or {}
        reads = []
        if ah.get('site_address'):
            reads.append({'where': 'the site', 'address': ah['site_address'], 'hours': {k: (v.get('site_block') or v.get('site')) for k, v in (ah.get('hours') or {}).items() if v.get('site') or v.get('site_block')}, 'capture': next((c for c in ah.get('captures', []) if 'address_site' in c), None)})
        if ah.get('bing_address'):
            reads.append({'where': 'Bing', 'address': ah['bing_address'], 'hours': {'sales': ' | '.join(ah.get('bing_hours_rows') or [])} if ah.get('bing_hours_rows') else {}, 'capture': 'captures/bing_panel.png'})
        for c in group_results.get('group_cards') or []:
            if c['store'] == s['store']:
                reads.append({'where': f'the group site card on {urlparse(c["page"]).path or "/"}', 'address': c.get('address'), 'hours': {'card': ' | '.join(c.get('hours_lines') or [])} if c.get('hours_lines') else {}, 'phones': c.get('phones'), 'capture': c.get('capture') or f'../group/{next((p.get("capture") for p in group_results.get("group_pages", []) if p.get("url") == c["page"]), "") or ""}'})
        for c in group_results.get('sister_cards') or []:
            if c['store'] == s['store']:
                reads.append({'where': f'{c["sister_site"]} on {urlparse(c["page"]).path or "/"}', 'address': c.get('address'), 'hours': {'card': ' | '.join(c.get('hours_lines') or [])} if c.get('hours_lines') else {}, 'phones': c.get('phones'), 'capture': f'../group/{next((p.get("capture") for p in group_results.get("sister_pages", []) if p.get("url") == c["page"]), "") or ""}'})
        mism = []
        base_addr = address_key(ah.get('site_address'))
        for rd in reads[1:]:
            if rd.get('address') and base_addr and address_key(rd['address']) != base_addr:
                mism.append({'what': 'address', 'where': rd['where'], 'site': ah.get('site_address'), 'other': rd['address'], 'capture': rd.get('capture')})
        site_hours = {k: norm_hours(v) for k, v in (reads[0]['hours'] if reads else {}).items()} if reads else {}
        for rd in reads[1:]:
            for dept, text in (rd.get('hours') or {}).items():
                nh = norm_hours(text)
                if not nh:
                    continue
                against = site_hours.get(dept) or site_hours.get('sales')
                if against:
                    diffs = {day: (against.get(day), nh.get(day)) for day in nh if day in against and against[day] != nh[day]}
                    if diffs:
                        mism.append({'what': 'hours', 'dept': dept, 'where': rd['where'], 'diffs': diffs, 'capture': rd.get('capture')})
        r['cross_site'] = {'reads': reads, 'mismatches': mism, 'compared_at': now_et()}
        for m in mism:
            if m['what'] == 'address':
                st.flag('address_format_group', 'Address and Hours', {'site': m['site'], m['where']: m['other']}, 'one format', 'Use one address format on Google, Bing, the site and the group site', [c for c in (m.get('capture'),) if c])
            else:
                st.flag('hours_group', 'Address and Hours', m['diffs'], 'same schedule', 'Confirm the hours and match them on each site, Google and Bing', [c for c in (m.get('capture'),) if c])
        st.finish(close=False)
