"""The collector's command line.

  python3 -m collector collect STORE.json [--out DIR] [--jobs N]     one store, or a group file (several at once)
  python3 -m collector preflight STORE.json                          only the pre-flight, in seconds
  python3 -m collector platform-test                                 Decision 7: which platforms load headless
  python3 -m collector handoff DIR                                   zip each finished store and send it

A store's run, in the skill's order: pre-flight; set-up (the three pages); PageSpeed home mobile and desktop
(numbers by API, pictures from the report page, the treemap); pop-up timing in a fresh context; SEO META fields;
vehicle links; the menu crawl; contact info; Bing; the VDP on a phone; the pages (specials, service,
trade-in, finance, About Us, lease, hours, blog, research); flags; the contact sheet. results.json is written after
every step. A failed step is recorded and the run moves on: the audit never waits on the collector."""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import bing, captures, config, conversion, flags, handoff, pagespeed, platforms, popups, preflight, site, spyfu
from .store import Store


def collect_store(request, out_dir, plat):
    store = Store(request, out_dir)
    store.log(f'start {request.get("store")} {request["url"]}')
    with captures.Browser() as b:
        ctx = b.context()
        page = ctx.new_page()
        pf = preflight.run(store, page, plat)
        if not pf['loads']:
            store.finish()
            return store
        if pf.get('platform_headless') == 'chrome_only':
            store.not_captured('everything after the pre-flight', f'{pf["platform"]} is chrome_only in platforms.json')
            store.finish()
            return store
        site.setup_pages(store, page)
        # PageSpeed on the home page: numbers by API, pictures from the report page, then the treemap
        rp = ctx.new_page()
        for ff in ('mobile', 'desktop'):
            if not config.PSI_API_KEY:
                store.results['pagespeed'][f'home_{ff}'] = {'api': None, 'report': None, 'runs': [], 'lcp_is_popup': None, 'captures': {}}
                continue   # no key: the report page below supplies the numbers as well as the pictures
            try:
                main, runs = pagespeed.api_with_rerun(store, store.results['pages']['home'], ff)
                store.results['pagespeed'][f'home_{ff}'] = {'api': main, 'report': None, 'runs': runs, 'lcp_is_popup': main['lcp_is_popup'], 'captures': {}}
                if ff == 'mobile':
                    store.results['gtm'] = {'count': main['gtm_count'], 'names': main['gtm_names'], 'scripts_total': main['scripts_total'], 'capture': None, 'source': 'api'}
                store.check(f'pagespeed_home_{ff}', 'ok')
            except Exception as e:
                store.check(f'pagespeed_home_{ff}', 'failed', f'{type(e).__name__}: {e}')
        pics = pagespeed.report_pictures(store, rp, store.results['pages']['home'], 'home')
        for ff in ('mobile', 'desktop'):
            rec = store.results['pagespeed'].get(f'home_{ff}')
            if rec:
                rec['report'] = pics.get('numbers', {}).get(ff)
                rec['report_url'] = pics.get('report_url')
                rec['captures'] = {k: v for k, v in pics.get('captures', {}).items() if k.startswith(ff)}
        if pics.get('report_url'):
            tm = pagespeed.treemap_picture(store, rp)
            if tm:
                if store.results['gtm']:
                    store.results['gtm']['capture'] = 'captures/treemap_home.png'
                    store.results['gtm']['count_report'] = tm['count']
                else:   # no API key: the treemap tab is the count's only source, as in Chrome
                    store.results['gtm'] = {'count': tm['count'], 'names': tm['names'], 'scripts_total': tm['total'], 'capture': 'captures/treemap_home.png', 'source': 'treemap'}
            for ff in ('mobile', 'desktop'):
                rec = store.results['pagespeed'].get(f'home_{ff}')
                if rec and not rec['api'] and rec['report']:
                    store.check(f'pagespeed_home_{ff}', 'ok')
                elif rec and not rec['api']:
                    store.check(f'pagespeed_home_{ff}', 'failed', 'no key and the report page exposed no numbers; PageSpeed goes to Chrome')
        store.save()
        popups.timing(store, b)
        site.seo_meta(store, page)
        site.srp_links(store, page)
        site.contact_info(store, page)
        bing.listing(store, page)
        spyfu.organic(store)
        conversion.vdp(store, page, rp)
        site.menu_crawl(store, page)
        site.pages(store, page)
        rp.close()
        ctx.close()
    flags.apply(store)
    captures.contact_sheet(store)
    store.finish()
    store.log(f'done in {store.results["collector"]["seconds"]} s: {len(store.results["flags"])} flags, {len(store.results["not_captured"])} not captured')
    return store


def main(argv):
    if len(argv) < 1:
        print(__doc__)
        return 2
    cmd = argv[0]
    if cmd == 'platform-test':
        platforms.run()
        return 0
    if cmd == 'handoff':
        print(handoff.run(argv[1] if len(argv) > 1 else 'out'))
        return 0
    if cmd in ('collect', 'preflight'):
        spec = json.loads(Path(argv[1]).read_text())
        out = Path(argv[argv.index('--out') + 1]) if '--out' in argv else Path('out')
        jobs = int(argv[argv.index('--jobs') + 1]) if '--jobs' in argv else config.JOBS
        out.mkdir(parents=True, exist_ok=True)
        plat = platforms.load()
        stores = spec['stores'] if 'stores' in spec else [spec]
        for s in stores:
            for k in ('group', 'group_site', 'sister_sites'):
                if k in spec and k not in s:
                    s[k] = spec[k]
        if cmd == 'preflight':
            with captures.Browser() as b:
                for s in stores:
                    st = Store(s, out)
                    ctx = b.context()
                    pf = preflight.run(st, ctx.new_page(), plat)
                    ctx.close()
                    print(json.dumps({s['url']: pf}, indent=1))
            return 0
        with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
            list(ex.map(lambda s: collect_store(s, out, plat), stores))
        print(handoff.run(out) if '--handoff' in argv else f'finished; run: python3 -m collector handoff {out}')
        return 0
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
