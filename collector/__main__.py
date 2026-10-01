"""The collector's command line.

  python3 -m collector collect STORE.json [--out DIR] [--jobs N]     one store, or a group file (several at once)
  python3 -m collector preflight STORE.json                          only the pre-flight, in seconds
  python3 -m collector platform-test                                 Decision 7: which platforms load headless
  python3 -m collector handoff DIR                                   zip each finished store and send it
  python3 -m collector trigger [--dry-run] [--csv FILE] [--once]      read the requests sheet and run what is waiting
  python3 -m collector listen [--port 8787]                          the push listener the sheet's Apps Script calls

A store's run, in the skill's order: pre-flight; set-up (the three pages); PageSpeed on the home page only, mobile
and desktop (the report page, the API as fallback, the treemap); pop-up timing in a fresh context; SEO META fields;
vehicle links; the menu crawl; contact info; Bing; the VDP on a phone (the collector's own render); the pages (specials, service,
trade-in, finance, About Us, lease, hours, blog, research); flags; the contact sheet. results.json is written after
every step. A failed step is recorded and the run moves on: the audit never waits on the collector."""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import bing, captures, config, conversion, flags, group, handoff, pagespeed, platforms, popups, preflight, site, spyfu, syndication
from .store import Store


def step(store, name, fn, *args):
    """One module of a store's run: a failure is recorded and the run moves on (the audit never waits)."""
    if store.over_budget():
        store.check(name, 'skipped', 'store time budget reached')
        return None
    try:
        return fn(*args)
    except Exception as e:
        store.check(name, 'failed', f'{type(e).__name__}: {str(e)[:300]}')
        return None


def collect_store(request, out_dir, plat):
    store = Store(request, out_dir)
    store.log(f'start {request.get("store")} {request["url"]}')
    try:
        with captures.Browser() as b:
            ctx = b.context(block_lead_modals=True)
            if config.CAPTURE_BLOCKED_SCRIPTS:
                store.noticed(f'blocked for the evidence captures only (not the pop-up timing pass): {", ".join(config.CAPTURE_BLOCKED_SCRIPTS)}')
            page = ctx.new_page()
            pf = step(store, 'preflight', preflight.run, store, page, plat)
            if not pf or not pf['loads']:
                store.finish()
                return store
            if pf.get('platform_headless') == 'chrome_only':
                store.not_captured('everything after the pre-flight', f'{pf["platform"]} is chrome_only in platforms.json')
                store.finish()
                return store
            step(store, 'setup', site.setup_pages, store, page)
            # PageSpeed on the home page: numbers by API, pictures and the page's own numbers from the report page, the treemap
            rp = ctx.new_page()
            step(store, 'pagespeed_home', pagespeed.home, store, rp, store.results['pages']['home'])
            step(store, 'popup', popups.timing, store, b)
            step(store, 'seo_meta', site.seo_meta, store, page)
            step(store, 'srp_links', site.srp_links, store, page)
            step(store, 'contact_info', site.contact_info, store, page)
            step(store, 'bing', bing.listing, store, page)
            spyfu.organic(store)
            step(store, 'conversion', conversion.vdp, store, page, rp, b)
            step(store, 'menu', site.menu_crawl, store, page)
            step(store, 'pages', site.pages, store, page)
            step(store, 'research_content', syndication.check, store, page)
            rp.close()
            ctx.close()
    except Exception as e:
        store.check('browser', 'failed', f'{type(e).__name__}: {str(e)[:300]}')
    # pop-ups closed before captures (inner-page pop-ups are recap material, never timed: references/03_off_script.md)
    from urllib.parse import urlparse
    own = {store.results.get('domain'), (store.results.get('preflight') or {}).get('final_host', '').replace('www.', '')}
    closed = [c for c in captures.CLOSED_OVERLAYS if urlparse(c[0]).netloc.replace('www.', '') in own or any(d and urlparse(c[0]).netloc.endswith(d) for d in own)]
    if closed:
        texts = {}
        for url, what, text in closed:
            texts.setdefault(text[:80], []).append(url)
        for text, urls in list(texts.items())[:3]:
            store.noticed(f'a pop-up was closed before captures on {len(urls)} page(s) (first on {urls[0]}): "{text}"')
    step(store, 'flags', flags.apply, store)
    step(store, 'contact_sheet', captures.contact_sheet, store)
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
    if cmd == 'listen':
        from . import listener
        return listener.main(argv[1:])
    if cmd == 'trigger':
        from . import trigger
        return trigger.main(argv[1:])
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
            for k in ('group', 'group_site'):
                if k in spec and k not in s:
                    s[k] = spec[k]
            # a store's sister sites: the group's other stores plus any the request lists (group-wide or per store)
            from .store import domain_of
            others = [domain_of(o['url']) for o in stores if o is not s]
            s['sister_sites'] = sorted(set(others) | {domain_of(x) for x in (s.get('sister_sites') or [])} | {domain_of(x) for x in (spec.get('sister_sites') or [])})
        if cmd == 'preflight':
            with captures.Browser() as b:
                for s in stores:
                    st = Store(s, out)
                    ctx = b.context(block_lead_modals=True)
                    pf = preflight.run(st, ctx.new_page(), plat)
                    ctx.close()
                    print(json.dumps({s['url']: pf}, indent=1))
            return 0
        # stores N at a time (--jobs), each in its own browser; a group's site runs as one more job beside them, and the
        # cross-site compare runs once every store has finished. The wall-clock time is written to DIR/run.json.
        import time
        from .store import now_et
        t0 = time.time()
        run_log = {'started_at': now_et(), 'jobs': jobs, 'stores': [s['url'] for s in stores], 'group_site': spec.get('group_site') if 'stores' in spec else None}
        gs_holder = {}
        with ThreadPoolExecutor(max_workers=max(1, jobs) + (1 if 'stores' in spec and spec.get('group_site') else 0)) as ex:
            futs = [ex.submit(collect_store, s, out, plat) for s in stores]
            if 'stores' in spec and spec.get('group_site'):
                gfut = ex.submit(group.run, spec, out, plat)
            for f in futs:
                f.result()
            if 'stores' in spec and spec.get('group_site'):
                gs_holder['gs'] = gfut.result()
        if gs_holder.get('gs'):
            group.compare(spec, out, gs_holder['gs'].results)
        run_log.update({'finished_at': now_et(), 'seconds': round(time.time() - t0), 'minutes': round((time.time() - t0) / 60, 1)})
        (out / 'run.json').write_text(json.dumps(run_log, indent=1))
        print(f'wall clock: {run_log["minutes"]} min for {len(stores)} store(s)' + (' and the group site' if run_log['group_site'] else ''))
        print(handoff.run(out) if '--handoff' in argv else f'finished; run: python3 -m collector handoff {out}')
        return 0
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
