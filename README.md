# dealer-audit-collector (Phase 3 of dealer-seo-audit-v2)

The collector: a Python and Playwright process on the agents VM that gathers the evidence a Digital 1 dealer SEO
audit needs, headless, and hands each store's `results.json`, `captures/` and `contact_sheet.png` to the Claude
session that runs the dealer-seo-audit-v2 skill. Claude judges and writes; the collector collects and flags. No paid APIs: SpyFu and Google Business Profile stay
Chrome steps, and the only key is the free PageSpeed Insights one, optional.

Prepared Sep 29, 2026 in the Cowork session that built Phases 1 and 2. The code here has never run against a live
site (that workspace cannot reach dealer sites or PageSpeed); the VM build makes it run, check by check, against real
stores. KICKOFF_PROMPT_VM.md is what to paste into Claude Code on the VM.

| File | What it is |
| --- | --- |
| `DECISIONS.md` | Jonathan's seven decisions (Sep 29) and what each means for the build |
| `SPEC.md` | The contract: every check of the skill mapped to the collector, PageSpeed by API plus the report page, the capture names, results.json, the flags, the platform test, the hand-off, the Phase 3 gate |
| `SETUP.md` | The free PageSpeed key (optional), the hand-off folder (Taildrop or Syncthing), the VM |
| `KICKOFF_PROMPT_VM.md` | The prompt for Claude Code on the VM |
| `collector/` | The skeleton: `__main__.py` (collect, preflight, platform-test, handoff), `config.py`, `store.py` (results.json, Eastern times, incremental saves), `captures.py` (browser, captures, crops, red boxes, contact sheet), `snippets.py` (the skill's page scripts, ported), `preflight.py`, `pagespeed.py`, `popups.py`, `site.py`, `conversion.py`, `bing.py`, `flags.py`, `platforms.py`, `handoff.py` |
| `examples/` | A store request and a group request |
| `requirements.txt`, `.env.example` | Dependencies and the one key's name (free; optional) |

What was checked before the hand-off: every module compiles; the offline parts run (the phone screens cut from a
render, the flags from a results.json, the zip and manifest, results.json written incrementally). Everything that
touches the network is untested and marked for the VM build.

```
python3 -m collector platform-test                      # Decision 7 first
python3 -m collector preflight examples/store.example.json
python3 -m collector collect examples/store.example.json --out out --jobs 1
python3 -m collector handoff out
```
