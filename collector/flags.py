"""Tier 2: the skill's thresholds as numbers (SPEC.md section 6). Each flag is a candidate with the skill's standard
line attached; Claude confirms every one against references/02_steps.md. Phase 3 emits the flags whose numbers it
has; Phase 4 completes the set. Nothing here puts anything on a slide."""


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
            failing = [k.upper() for k in ('lcp', 'inp', 'cls') if (fd.get(k) or {}).get('category') in ('SLOW', 'AVERAGE')]
            side = 'phones' if ff == 'mobile' else 'desktops'
            F(f'cwv_{ff}', 'Core Web Vitals', failing, 'Passed', f'{r.get("store")} fails Core Web Vitals on {side}', caps('field', ff))
    p = r.get('popup') or {}
    if p.get('open_s') is not None:
        F('popup', 'Homepage Pop-Up', p['open_s'], 0, 'Delay homepage pop-ups 15 seconds to improve website load time', p.get('captures', []))
    home = (r.get('seo_meta') or {}).get('home') or {}
    if home.get('images') and (home.get('no_alt') or home.get('no_title')):
        # The skill's comment names the biggest miss; the decks so far lead with ALT text whenever any image lacks it
        # (Bay Hyundai: "46 of 52 images are missing ALT text" with 51 lacking TITLE), so ALT comes first.
        miss, what = (home['no_alt'], 'ALT text') if home.get('no_alt') else (home['no_title'], 'TITLE text')
        F('images', 'Unoptimized Images', {'no_alt': home.get('no_alt'), 'no_title': home.get('no_title')}, 0, f'{miss} of {home["images"]} images are missing {what}', ['typed grid'])
    for key, label in (('home', 'home'), ('srp', 'SRP')):
        m = (r.get('seo_meta') or {}).get(key) or {}
        if m.get('title_len', 0) > 60 or m.get('meta_len', 0) > 160:
            F(f'title_meta_{key}', 'Titles and Meta Descriptions', {'title': m.get('title_len'), 'meta': m.get('meta_len')}, {'title': 60, 'meta': 160}, f'The {label} title runs {m.get("title_len")} characters, the meta {m.get("meta_len")}', ['typed grid'])
    if home.get('h') and home['h'][0] == 0:
        F('headers_home', 'Headers', home['h'], None, 'The home page has no H1', ['typed grid'])
    srp = (r.get('seo_meta') or {}).get('srp') or {}
    if srp.get('h') and (srp['h'][0] > 1 or srp['h'][1] == 0):
        F('headers_srp', 'Headers', srp['h'], None, 'Optimize the SRP template down to one H1' if srp['h'][0] > 1 else 'The SRP has no H2', ['typed grid'])
    l = r.get('links') or {}
    if l.get('srp_http_links'):
        F('vehicle_links', 'Vehicle Links', l['srp_http_links'], 0, f'All {l["srp_vehicle_links"]} vehicle links use http:// on an https:// site' if l['srp_http_links'] == l['srp_vehicle_links'] else f'{l["srp_http_links"]} of {l["srp_vehicle_links"]} vehicle links use http:// on an https:// site', ['typed grid'])
    for it in ((r.get('menu') or {}).get('items') or []):
        if it['result'] in ('404', 'home_redirect'):
            F('broken_link', 'Broken Link', it['label'], None, f'The {it["label"]} menu link opens a 404 page' if it['result'] == '404' else f'The {it["label"]} menu link sends shoppers back to the home page', [it.get('capture_menu'), it.get('capture_dest')])
        elif it['result'] in ('offsite', 'third_party', 'group_site', 'sister_site'):
            F('offsite_link', 'Off-Site Link', it['label'], None, f'The {it["top"] or it["label"]} menu sends shoppers to {it["landed_host"]}', [it.get('capture_menu'), it.get('capture_dest')])
    s = r.get('spyfu') or {}
    if s.get('keywords') is not None:
        if s['keywords'] < 1500:
            F('organic_low', 'Organic Search', s['keywords'], 1500, f'{s["keywords"]:,} keywords leaves a lot of room to grow', ['SpyFu card in Chrome'])
        if s.get('keywords_12m_ago') and s['keywords'] < s['keywords_12m_ago']:
            F('organic_down', 'Organic Search', s['keywords'], s['keywords_12m_ago'], f'Down from about {s["keywords_12m_ago"]:,} keywords to {s["keywords"]:,} in 12 months', ['SpyFu card in Chrome'])
        if s.get('rank_change_1m') is not None and s['rank_change_1m'] < 0:
            F('rank_loss', 'Organic Search', s['rank_change_1m'], 0, f'Rankings fell a net {abs(s["rank_change_1m"]):,} spots last month', ['SpyFu card in Chrome'])
        for c in s.get('competitors') or []:
            if c.get('keywords') and c['keywords'] > s['keywords']:
                F('competitor_ahead', 'Organic Search', c['keywords'], s['keywords'], f'{c["name"]} leads with {c["keywords"]:,} keywords', ['SpyFu card in Chrome'])
    cv = r.get('conversion') or {}
    if cv.get('big_price_is') and cv['big_price_is'].startswith('fee'):
        F('price_stack', 'Conversion Optimization SRP-VDP', cv['big_price_is'], 'selling price', 'The VDP\'s big price is a fee', cv.get('captures', []))
    for c in cv.get('ctas') or []:
        if c.get('leaves_site'):
            F('cta_offsite', 'Conversion Optimization SRP-VDP', c['text'], None, f'The {c["text"]} CTA sends shoppers off the site', cv.get('captures', []))
    if cv.get('vdp_lcp_s') and cv['vdp_lcp_s'] > 2.5:
        F('vdp_lcp', 'Conversion Optimization SRP-VDP', cv['vdp_lcp_s'], 2.5, f'On a phone, the VDP\'s main content takes {cv["vdp_lcp_s"]} s to load', cv.get('captures', []))
    for cx in r.get('cx') or []:
        if cx.get('text_flags'):
            F('specials_empty', 'Customer Experience', cx['text_flags'][0], None, f'The {cx["page"].replace("specials_", "").title()} Specials page is empty', [cx.get('capture')])
    srp_years = set((r.get('pages') or {}).get('srp_new_count_text') and [] or [])
    b = r.get('blog') or {}
    if b and b.get('posts') == 0:
        F('blog_empty', 'Empty Image Spaces', 0, 1, 'The blog has no posts', [b.get('capture')])
    sh = r.get('special_hours') or {}
    if sh.get('holidays'):
        F('special_hours', 'Out-of-Date Hours', sh['holidays'], 'the next holiday only', f'The site still shows {" and ".join(sh["holidays"][:2])} hours', [sh.get('capture')])
    store.save()
    return r['flags']
