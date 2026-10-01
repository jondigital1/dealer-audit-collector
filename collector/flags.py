"""Tier 2: the skill's thresholds as numbers (SPEC.md section 6). Each flag is a candidate with the skill's standard
line attached; Claude confirms every one against references/02_steps.md. Phase 3 emits the flags whose numbers it
has; Phase 4 completes the set. Nothing here puts anything on a slide."""
import re

HOLIDAY_ORDER = ['New Year\'s Day', 'MLK Day', 'Presidents Day', 'Good Friday', 'Easter', 'Memorial Day', 'Juneteenth', 'Independence Day', 'July 4th',
                 'Labor Day', 'Columbus Day', 'Veterans Day', 'Thanksgiving', 'Christmas Eve', 'Christmas Day', 'Christmas', 'New Year\'s Eve']


def norm_hours(text):
    """Hours text into a comparable form: 'mon 9:00am-7:00pm' rows, so '9 AM - 7 PM' and '9:00am - 7:00pm' agree."""
    if not text:
        return None
    t = text if isinstance(text, str) else ' | '.join(text)
    t = t.lower().replace('\u2013', '-').replace('\u2014', '-').replace(' to ', '-')   # a scraped en or em dash becomes a hyphen
    rows = {}
    for m in re.finditer(r'\b(mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?\s*[:|]?\s*(closed|(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*-\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm))', t):
        day = m.group(1)
        if m.group(2) == 'closed':
            rows[day] = 'closed'
            continue
        h1, m1, p1, h2, m2, p2 = m.group(3), m.group(4) or '00', m.group(5), m.group(6), m.group(7) or '00', m.group(8)
        p1 = p1 or ('am' if int(h1) < 12 else 'pm')
        rows[day] = f'{int(h1)}:{m1}{p1}-{int(h2)}:{m2}{p2}'
    return rows or None


def address_key(a):
    """An address with every format difference kept (W. against W, Street against St), only case and spacing dropped."""
    return re.sub(r'\s+', ' ', (a or '').strip().lower()) or None


def apply(store):
    r = store.results
    F = store.flag
    ps = r.get('pagespeed') or {}

    def pick(k):   # the API run when there is a key, else the report page's numbers
        rec = ps.get(k) or {}
        return rec.get('api') or rec.get('report') or {}
    hm, hd = pick('home_mobile'), pick('home_desktop')
    caps = lambda k, ff: [f'captures/psi_home_{ff}_{k}.png']
    if hm.get('score') is not None and hm['score'] < 20:
        F('site_speed_mobile', 'Site Speed', hm['score'], 20, 'Mobile site speed is below 20', caps('gauges', 'mobile'))
    if hd.get('score') is not None and hd['score'] < 50:
        F('site_speed_desktop', 'Site Speed', hd['score'], 50, 'Desktop site speed is below 50', caps('gauges', 'desktop'))
    if hm.get('lcp_s') is not None and hm['lcp_s'] > 2.5:
        F('mobile_lcp', 'Site Speed', hm['lcp_s'], 2.5, f'On a phone, the main content takes {hm["lcp_s"]} s to load', caps('gauges', 'mobile'))
    if hd.get('lcp_s') is not None and hd['lcp_s'] > 2.5:
        F('desktop_lcp', 'Site Speed', hd['lcp_s'], 2.5, f'On desktop, the main content takes {hd["lcp_s"]} s to load', caps('gauges', 'desktop'))
    elif hd.get('tbt_ms'):
        F('desktop_tbt', 'Site Speed', hd['tbt_ms'], None, f'On desktop, scripts block the page for a combined {hd["tbt_ms"]:,} ms', caps('gauges', 'desktop'))
    g = r.get('gtm') or {}
    if g.get('count') is not None and g['count'] >= 8:
        F('gtm', 'Core Web Vitals-Site Speed', g['count'], 8, f'{g["count"]} GTMs loading on the home page', ['captures/treemap_home.png'])
    for ff, rec in (('mobile', hm), ('desktop', hd)):
        fd = rec.get('field') or {}
        if fd.get('status') == 'Failed':
            failing = []
            for k in ('lcp', 'inp', 'cls'):
                v = fd.get(k)
                if isinstance(v, dict) and v.get('category') in ('SLOW', 'AVERAGE'):
                    failing.append(k.upper())
                elif isinstance(v, str):   # the report card's display value: judged against the metric's good limit
                    num = float(re.sub(r'[^\d.]', '', v) or 0)
                    limit = {'lcp': 2.5, 'inp': 200, 'cls': 0.1}[k]
                    if (k == 'inp' and 'ms' in v and num > limit) or (k == 'lcp' and num > limit) or (k == 'cls' and num > limit):
                        failing.append(k.upper())
            side = 'phones' if ff == 'mobile' else 'desktops'
            F(f'cwv_{ff}', 'Core Web Vitals', failing, 'Passed', f'{r.get("store")} fails Core Web Vitals on {side}', caps('field', ff))
    p = r.get('popup') or {}
    if p.get('open_s') is not None:
        F('popup', 'Homepage Pop-Up', p['open_s'], 0, 'Delay homepage pop-ups 15 seconds to improve website load time', p.get('captures', []))
    home = (r.get('seo_meta') or {}).get('home') or {}
    if home.get('images') and (home.get('no_alt') or home.get('no_title')):
        # The skill's comment names the biggest miss; the decks so far lead with ALT text whenever any real image lacks
        # it (Bay Hyundai: "46 of 52 images are missing ALT text" with 51 lacking TITLE), so ALT comes first. Tracking
        # pixels do not count toward that choice (Natchez Nissan: the 3 without ALT were all pixels, the miss is TITLE);
        # the raw counts are reported unchanged.
        real_no_alt = home.get('no_alt_excluding_pixels', home.get('no_alt')) or 0
        miss, what = (home['no_alt'], 'ALT text') if real_no_alt else (home['no_title'], 'TITLE text')
        F('images', 'Unoptimized Images', {'images': home['images'], 'no_alt': home.get('no_alt'), 'no_title': home.get('no_title'), 'no_alt_excluding_pixels': home.get('no_alt_excluding_pixels')}, 0, f'{miss} of {home["images"]} images are missing {what}', ['typed grid'])
    for key, label in (('home', 'home'), ('srp', 'SRP')):
        m = (r.get('seo_meta') or {}).get(key) or {}
        if (m.get('title_len') or 0) > 60 or (m.get('meta_len') or 0) > 160:
            F(f'title_meta_{key}', 'Titles and Meta Descriptions', {'title': m.get('title_len'), 'meta': m.get('meta_len')}, {'title': 60, 'meta': 160}, f'The {label} title runs {m.get("title_len")} characters, the meta {m.get("meta_len")}', ['typed grid'])
    if home.get('title') and re.match(r'\s*home\b', home['title'], re.I):
        F('title_generic_home', 'Titles and Meta Descriptions', home['title'], None, 'Its title starts with "Home"', ['typed grid'])
    if home.get('h') and home['h'][0] == 0:
        F('headers_home', 'Headers', home['h'], None, 'The home page has no H1', ['typed grid'])
    srp = (r.get('seo_meta') or {}).get('srp') or {}
    if srp.get('h') and (srp['h'][0] > 1 or srp['h'][1] == 0):
        F('headers_srp', 'Headers', srp['h'], None, 'Optimize the SRP template down to one H1' if srp['h'][0] > 1 else 'The SRP has no H2', ['typed grid'])
    l = r.get('links') or {}
    if l.get('srp_http_links') and l.get('srp_is_https', True):
        n, tot = l['srp_http_links'], l.get('srp_vehicle_links')
        F('vehicle_links', 'Vehicle Links', n, 0, f'All {tot} vehicle links use http:// on an https:// site' if n == tot else f'{n} of {tot} vehicle links use http:// on an https:// site', ['typed grid'])
    # the manufacturer's own parts and accessories integration (GM's accessories.chevrolet.com, Hyundai's
    # hyundaiaccessories.com) goes in the notes, not on a slide (references/02_steps.md); the flag says so
    oem_parts = re.compile(r'accessories\.(chevrolet|cadillac|buick|gmc|ford|toyota|honda|nissan|kia|hyundai)\.com|[a-z0-9]+\.(hyundai|kia|nissan|toyota|honda|ford|mopar|gm)accessories\.com|hyundaiaccessories\.com|parts\.(ford|gm|toyota)\.com', re.I)
    for it in ((r.get('menu') or {}).get('items') or []):
        ev = [c for c in (it.get('capture_menu'), it.get('capture_dest')) if c]
        label = it.get('label') or it.get('path')
        if it['result'] in ('404', 'home_redirect'):
            F('broken_link', 'Broken Link', label, None, f'The {label} menu link opens a 404 page' if it['result'] == '404' else f'The {label} menu link sends shoppers back to the home page', ev)
        elif it['result'] in ('offsite', 'third_party', 'group_site', 'sister_site'):
            F('offsite_link', 'Off-Site Link', label, None, f'The {it["top"] or label} menu sends shoppers to {it["landed_host"]}', ev)
            if it.get('landed_host') and oem_parts.search(it['landed_host']):
                r['flags'][-1]['note'] = 'the manufacturer\'s parts and accessories integration: the skill puts it in the notes, not on a slide'
        elif it['result'] == 'empty':
            F('empty_page', 'Customer Experience', it.get('empty_text') or 'empty', None, f'The {label} page is empty' + (f' ("{it["empty_text"]}")' if it.get('empty_text') else ''), ev)
    for rl in r.get('research_links') or []:
        if rl.get('result') == 'empty':
            F('empty_page', 'Customer Experience', rl.get('empty_text') or 'empty', None, f'The {rl.get("label")} research page is empty' + (f' ("{rl["empty_text"]}")' if rl.get('empty_text') else ''), [c for c in (rl.get('capture_dest'),) if c])
    for rl in r.get('research_links') or []:
        ev = [c for c in (rl.get('capture_dest'),) if c]
        if rl.get('result') in ('404', 'home_redirect'):
            F('broken_link', 'Broken Link', rl.get('label'), None, f'The {rl.get("label")} research link opens a 404 page' if rl['result'] == '404' else f'The {rl.get("label")} research link sends shoppers back to the home page', ev)
        elif rl.get('result') in ('offsite', 'third_party'):
            F('offsite_link', 'Off-Site Link', rl.get('label'), None, f'The {rl.get("label")} research link sends shoppers to {rl.get("landed_host")}', ev)
    # hours and address: Bing against the site (Google's come from Claude's Chrome read)
    ah = r.get('address_hours') or {}
    site_addr, bing_addr = address_key(ah.get('site_address')), address_key(ah.get('bing_address'))
    if site_addr and bing_addr and site_addr != bing_addr:
        F('address_format', 'Address and Hours', {'site': ah.get('site_address'), 'bing': ah.get('bing_address')}, 'one format', 'Use one address format on Google, Bing and the site',
          [c for c in ah.get('captures', []) if 'address' in c])
    site_sales = norm_hours(((ah.get('hours') or {}).get('sales') or {}).get('site_block') or ((ah.get('hours') or {}).get('sales') or {}).get('site'))
    bing_hours = norm_hours(ah.get('bing_hours_rows'))
    if site_sales and bing_hours:
        diffs = {d: (site_sales.get(d), bing_hours.get(d)) for d in bing_hours if d in site_sales and site_sales[d] != bing_hours[d]}
        if diffs:
            F('hours_bing', 'Address and Hours', diffs, 'same schedule', 'Confirm the hours and match them on each site, Google and Bing', [c for c in ah.get('captures', []) if 'hours' in c] + ['captures/bing_panel.png'])
    cv = r.get('conversion') or {}
    if cv.get('big_price_kind') == 'fee':
        F('price_stack', 'Conversion Optimization SRP-VDP', cv['big_price_is'], 'selling price', f'The VDP\'s big price is the {cv["big_price_is"].split(" (")[0]}', cv.get('captures', []))
    elif cv.get('price_stack') and not any(p.get('label_kind') == 'selling' for p in cv['price_stack']):
        F('price_stack_no_selling', 'Conversion Optimization SRP-VDP', cv.get('big_price_is'), 'selling price', 'The VDP shows no selling price', cv.get('captures', []))
    for c in cv.get('ctas') or []:
        if c.get('leaves_site') and not c.get('tel'):
            F('cta_offsite', 'Conversion Optimization SRP-VDP', c['text'], None, f'The {c["text"]} CTA sends shoppers off the site', cv.get('captures', []))
    if cv.get('popup_on_load'):
        F('vdp_popup', 'Conversion Optimization SRP-VDP', cv.get('mobile_layout', {}).get('popup_detail'), None, 'A pop-up opens over the SRP and VDP on load' if (r.get('popup') or {}).get('on_srp') else 'A pop-up opens over the VDP on load', cv.get('captures', []))
    if cv.get('promo_banner_top'):
        F('vdp_promo_banner', 'Conversion Optimization SRP-VDP', (cv.get('mobile_layout') or {}).get('top_third_text', '')[:120], None, 'A promotion banner takes the top of the first phone screen', cv.get('captures', []))
    if cv.get('click_to_call') is False:
        F('click_to_call', 'Conversion Optimization SRP-VDP', False, True, 'Add click to call to improve mobile conversions', cv.get('captures', []))
    for cx in r.get('cx') or []:
        if cx.get('text_flags'):
            what = re.sub(r'\b(specials?|special offers?|offers?)\b', '', (cx.get('label') or cx['page'].replace('specials_', '').replace('_', ' ')), flags=re.I)
            what = re.sub(r'\s+', ' ', what).strip().title()
            F('specials_empty', 'Customer Experience', cx['text_flags'][0], None, f'The {what + " " if what else ""}Specials page is empty', [cx.get('capture')])
        if cx.get('page') == 'research' and cx.get('model_years') and (r.get('pages') or {}).get('srp_model_years'):
            newest = max(int(y) for y in r['pages']['srp_model_years'])
            page_years = [int(y) for y in cx['model_years']]
            if max(page_years) < newest:
                F('research_stale', 'Model Research Pages', page_years, newest, f'The {cx.get("label")} research page is built for {max(page_years)} while {newest}s are in stock', [cx.get('capture')])
    yrs = [int(y) for y in (r.get('pages') or {}).get('srp_model_years') or []]
    if yrs:
        for sl in r.get('slider') or []:
            m = re.search(r'\b(20[2-3]\d)\b', sl.get('alt') or '')
            if m and int(m.group(1)) < max(yrs):
                F('slider_stale', 'Content Quality', sl['alt'], max(yrs), f'The home page slider still runs a {m.group(1)} slide', [sl.get('capture')])
    b = r.get('blog') or {}
    if b and (b.get('posts') == 0 or b.get('no_posts_text')):
        F('blog_empty', 'Empty Image Spaces', b.get('no_posts_text') or 0, 1, 'The blog has no posts', [b.get('capture')])
    sh = r.get('special_hours') or {}
    if sh.get('holidays'):
        F('special_hours', 'Out-of-Date Hours', sh['holidays'], 'the next holiday only', f'The site still shows {" and ".join(sh["holidays"][:2])} hours', [sh.get('capture')])
    store.save()
    return r['flags']
