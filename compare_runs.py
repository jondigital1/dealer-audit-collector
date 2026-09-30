"""The Phase 3 gate (SPEC.md section 10): the collector's results.json beside a facts.json from a Chrome-path capture
of the same store, every Tier 1 number side by side, with a verdict per row (counts exactly; PageSpeed scores within
normal run-to-run drift, 10 points and 2 s of LCP here, since Bay Hyundai's home page read 28 to 35 in one hour).

  python3 compare_runs.py out/bayhyundai.com/results.json ~/chrome/bay-hyundai/facts.json [--drift 10]
"""
import json
import re
import sys

from collector.flags import norm_hours


def g(d, *path):
    for p in path:
        if isinstance(d, dict):
            d = d.get(p)
        elif isinstance(d, list) and isinstance(p, int) and p < len(d):
            d = d[p]
        else:
            return None
    return d


def num(v):
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        m = re.search(r'-?\d[\d,]*(\.\d+)?', v)
        return float(m.group(0).replace(',', '')) if m else None
    return None


def hours_words(v):
    if not v:
        return None
    if isinstance(v, dict):
        return v.get('site') or v.get('site_block')
    if isinstance(v, list):
        return ' | '.join(v)
    return v


def rows(c, f):
    """(section, label, collector value, chrome value, kind) for every Tier 1 number the gate compares."""
    ps = lambda side, k: g(c, 'pagespeed', side, 'api', k) if g(c, 'pagespeed', side, 'api') else g(c, 'pagespeed', side, 'report', k)
    out = [
        ('Set-up', 'SRP', g(c, 'pages', 'srp'), g(f, 'pages', 'srp'), 'exact'),
        ('Set-up', 'VDP', g(c, 'pages', 'vdp'), g(f, 'pages', 'vdp'), 'exact'),
        ('Set-up', 'New vehicles on the SRP', g(c, 'pages', 'srp_new_count'), g(f, 'pages', 'srp_new_count'), 'exact'),
        ('Site speed', 'Home mobile score', ps('home_mobile', 'score'), g(f, 'pagespeed', 'home_mobile', 'score'), 'drift'),
        ('Site speed', 'Home mobile LCP s', ps('home_mobile', 'lcp_s'), g(f, 'pagespeed', 'home_mobile', 'lcp_s'), 'lcp'),
        ('Site speed', 'Home mobile TBT ms', ps('home_mobile', 'tbt_ms'), g(f, 'pagespeed', 'home_mobile', 'tbt_ms'), 'info'),
        ('Site speed', 'Home desktop score', ps('home_desktop', 'score'), g(f, 'pagespeed', 'home_desktop', 'score'), 'drift'),
        ('Site speed', 'Home desktop LCP s', ps('home_desktop', 'lcp_s'), g(f, 'pagespeed', 'home_desktop', 'lcp_s'), 'lcp'),
        ('Site speed', 'Home desktop TBT ms', ps('home_desktop', 'tbt_ms'), g(f, 'pagespeed', 'home_desktop', 'tbt_ms'), 'info'),
        ('Core Web Vitals', 'Mobile field', g(c, 'pagespeed', 'home_mobile', 'report', 'field', 'status') or g(c, 'pagespeed', 'home_mobile', 'api', 'field', 'status'), g(f, 'pagespeed', 'home_mobile', 'field', 'status'), 'exact'),
        ('Core Web Vitals', 'Mobile INP', g(c, 'pagespeed', 'home_mobile', 'report', 'field', 'inp') or g(c, 'pagespeed', 'home_mobile', 'api', 'field', 'inp', 'percentile'), g(f, 'pagespeed', 'home_mobile', 'field', 'inp'), 'info'),
        ('Core Web Vitals', 'Desktop field', g(c, 'pagespeed', 'home_desktop', 'report', 'field', 'status') or g(c, 'pagespeed', 'home_desktop', 'api', 'field', 'status'), g(f, 'pagespeed', 'home_desktop', 'field', 'status'), 'exact'),
        ('Tag load', 'GTM scripts', g(c, 'gtm', 'count'), g(f, 'gtm', 'count'), 'exact'),
        ('Pop-up', 'Vendor', g(c, 'popup', 'vendor'), g(f, 'popup', 'vendor'), 'info'),
        ('Pop-up', 'Opens at s', g(c, 'popup', 'open_s'), g(f, 'popup', 'open_s'), 'info'),
        ('SEO META', 'Home title length', g(c, 'seo_meta', 'home', 'title_len'), g(f, 'seo_meta', 'home', 'title_len'), 'exact'),
        ('SEO META', 'Home meta length', g(c, 'seo_meta', 'home', 'meta_len'), g(f, 'seo_meta', 'home', 'meta_len'), 'exact'),
        ('SEO META', 'Home H1 to H6', g(c, 'seo_meta', 'home', 'h'), g(f, 'seo_meta', 'home', 'h'), 'exact'),
        ('SEO META', 'Home images', g(c, 'seo_meta', 'home', 'images'), g(f, 'seo_meta', 'home', 'images'), 'exact'),
        ('SEO META', 'Home images without ALT', g(c, 'seo_meta', 'home', 'no_alt'), g(f, 'seo_meta', 'home', 'no_alt'), 'exact'),
        ('SEO META', 'Home images without TITLE', g(c, 'seo_meta', 'home', 'no_title'), g(f, 'seo_meta', 'home', 'no_title'), 'exact'),
        ('SEO META', 'SRP title length', g(c, 'seo_meta', 'srp', 'title_len'), g(f, 'seo_meta', 'srp', 'title_len'), 'exact'),
        ('SEO META', 'SRP meta length', g(c, 'seo_meta', 'srp', 'meta_len'), g(f, 'seo_meta', 'srp', 'meta_len'), 'exact'),
        ('SEO META', 'SRP H1 to H6', g(c, 'seo_meta', 'srp', 'h'), g(f, 'seo_meta', 'srp', 'h'), 'exact'),
        ('Links', 'SRP http:// vehicle links', g(c, 'links', 'srp_http_links'), g(f, 'links', 'srp_http_links'), 'exact'),
        ('Links', 'SRP vehicle links (unique)', g(c, 'links', 'srp_vehicle_links_unique'), g(f, 'links', 'srp_vehicle_links_unique'), 'info'),
        ('Menu', 'Items', g(c, 'menu', 'items_total'), g(f, 'menu', 'items_total'), 'info'),
        ('Menu', 'Not ok', sorted(i['label'] for i in (g(c, 'menu', 'items') or []) if i.get('result') not in ('ok', None)), sorted(i['label'] for i in (g(f, 'menu', 'items') or []) if i.get('result') not in ('ok', None)), 'info'),
        ('Address and hours', 'Site address', g(c, 'address_hours', 'site_address'), g(f, 'address_hours', 'site_address'), 'text'),
        ('Address and hours', 'Bing address', g(c, 'address_hours', 'bing_address'), g(f, 'address_hours', 'bing_address'), 'text'),
        ('Address and hours', 'Sales hours (site)', hours_words(g(c, 'address_hours', 'hours', 'sales')), hours_words(g(f, 'address_hours', 'hours', 'sales')), 'hours'),
        ('Address and hours', 'Service hours (site)', hours_words(g(c, 'address_hours', 'hours', 'service')), hours_words(g(f, 'address_hours', 'hours', 'service')), 'hours'),
        ('Address and hours', 'Phones', sorted({p['number'] for p in (c.get('phones') or [])}), sorted({re.sub(r'\D', '', p['number'])[-10:] for p in (f.get('phones') or [])}), 'phones'),
        ('Bing', 'Rating', g(c, 'bing', 'rating'), g(f, 'bing', 'rating'), 'text'),
        ('Bing', 'Rating source', g(c, 'bing', 'rating_source'), g(f, 'bing', 'rating_source'), 'text'),
        ('Bing', 'Website host', g(c, 'bing', 'website_host'), g(f, 'bing', 'website_host'), 'text'),
        ('Bing', 'UTM keys', g(c, 'bing', 'utm_keys'), g(f, 'bing', 'utm_keys'), 'exact'),
        ('Conversion', 'VDP mobile score', g(c, 'pagespeed', 'vdp_mobile', 'api', 'score') or g(c, 'pagespeed', 'vdp_mobile', 'report', 'score'), g(f, 'pagespeed', 'vdp_mobile', 'score'), 'drift'),
        ('Conversion', 'VDP mobile LCP s', g(c, 'conversion', 'vdp_lcp_s'), g(f, 'pagespeed', 'vdp_mobile', 'lcp_s'), 'lcp'),
        ('Conversion', 'CTAs in the stack', g(c, 'conversion', 'cta_count'), g(f, 'conversion', 'cta_count'), 'exact'),
        ('Conversion', 'Click to call', g(c, 'conversion', 'click_to_call'), g(f, 'conversion', 'click_to_call'), 'exact'),
        ('Conversion', 'Swipes to the price stack', g(c, 'conversion', 'swipes_to_price_stack'), g(f, 'conversion', 'swipes_to_price_stack'), 'exact'),
        ('Conversion', 'Swipes to the CTA stack', g(c, 'conversion', 'swipes_to_cta_stack'), g(f, 'conversion', 'swipes_to_cta_stack'), 'exact'),
        ('Conversion', 'Big price', g(c, 'conversion', 'big_price_is'), g(f, 'conversion', 'big_price_is'), 'text'),
        ('Conversion', 'Pop-up on VDP load', g(c, 'conversion', 'popup_on_load'), g(f, 'conversion', 'popup_on_load'), 'exact'),
        ('Conversion', 'ComplyAuto on load', g(c, 'conversion', 'complyauto_panel_on_load'), g(f, 'conversion', 'complyauto_panel_on_load'), 'exact'),
        ('Conversion', 'Promo banner top', g(c, 'conversion', 'promo_banner_top'), g(f, 'conversion', 'promo_banner_top'), 'exact'),
        ('Blog', 'Posts', g(c, 'blog', 'posts'), g(f, 'blog', 'posts'), 'exact'),
    ]
    return out


def verdict(kind, a, b, drift, lcp_drift):
    if a is None and b is None:
        return 'neither'
    if a is None:
        return 'COLLECTOR MISSING'
    if b is None:
        return 'chrome side missing'
    if kind == 'exact':
        return 'match' if a == b else 'DIFFERS'
    if kind == 'drift':
        return 'within drift' if abs(num(a) - num(b)) <= drift else 'DIFFERS'
    if kind == 'lcp':
        return 'within drift' if abs(num(a) - num(b)) <= lcp_drift else 'DIFFERS'
    if kind == 'phones':
        ca = {re.sub(r'\D', '', x)[-10:] for x in a}
        return 'match' if ca == set(b) else f'DIFFERS (collector only {sorted(ca - set(b))}, chrome only {sorted(set(b) - ca)})'
    if kind == 'hours':
        na, nb = norm_hours(a), norm_hours(b)
        if not na or not nb:
            return 'could not read one side as hours'
        common = [d for d in na if d in nb]
        return 'match' if common and all(na[d] == nb[d] for d in common) else f'DIFFERS on {[d for d in common if na[d] != nb[d]]}'
    if kind == 'text':
        sa, sb = str(a).strip().lower(), str(b).strip().lower()
        return 'match' if sa == sb else ('same words, more detail on one side' if sa[:20] in sb or sb[:20] in sa else 'DIFFERS')
    return 'info'


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    c = json.load(open(argv[0]))
    f = json.load(open(argv[1]))
    drift = float(argv[argv.index('--drift') + 1]) if '--drift' in argv else 10
    lcp_drift = 2.0
    print(f'{"Section":18} {"Check":30} {"Collector":42} {"Chrome":42} Verdict')
    print('-' * 150)
    counts = {}
    for sec, label, a, b, kind in rows(c, f):
        v = verdict(kind, a, b, drift, lcp_drift)
        counts[v.split(' ')[0]] = counts.get(v.split(' ')[0], 0) + 1
        sa, sb = json.dumps(a, ensure_ascii=False) if not isinstance(a, str) else a, json.dumps(b, ensure_ascii=False) if not isinstance(b, str) else b
        print(f'{sec:18} {label:30} {sa[:42]:42} {sb[:42]:42} {v}')
    print('-' * 150)
    print('collector run', g(c, 'collector', 'started_at'), 'to', g(c, 'collector', 'finished_at'), '| chrome capture', f.get('captured_at'))
    print('not captured by the collector:', [x['what'] for x in c.get('not_captured', [])])
    print('summary:', counts)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
