# Kickoff prompt for Claude Code on the agents VM (Phase 3, the collector)

Before pasting: SETUP.md steps 1 to 3 done (the PageSpeed key in `.env`, or left empty; the hand-off folder chosen;
the venv and Playwright installed), this package unzipped at `~/dealer-audit-collector`, and the v2 skill folder
(`dealer-seo-audit-v2`) and the golden fixture (`dealer-seo-audit-v2-golden-bay-hyundai`) unzipped beside it at
`~/dealer-seo-audit-v2` and `~/dealer-seo-audit-v2-golden-bay-hyundai`.

Paste this:

---

You're building Phase 3 of my Digital 1 dealer SEO audit rebuild: the collector, a Python and Playwright process on
this VM that gathers the evidence an audit needs, headless, and hands a folder to the Claude session that runs my
dealer-seo-audit-v2 skill. A skeleton is in this folder; it has never run against a live site. Your job is to make it
run, check by check, against real stores, until one dealer audited by the collector and by the Chrome path give the
same numbers.

Read these first, in order: DECISIONS.md, SPEC.md (the contract; section 2 maps every check of the skill to the
collector, section 5 fixes results.json), SETUP.md, then in ~/dealer-seo-audit-v2: SKILL.md, references/02_steps.md,
references/04_capture.md (how every capture was made in Chrome, with the selectors and workarounds from real runs;
port them, don't reinvent them), references/10_rules.md, and scripts/chrome_snippets.js. Then read every file in
collector/. The golden fixture at ~/dealer-seo-audit-v2-golden-bay-hyundai shows what a finished store's evidence
looks like: bay-hyundai/facts.json is the shape results.json keeps, and bay-hyundai/captures/ are the pictures the
deck used, so you can compare what the collector produces against real ones.

Ground rules:
- The collector collects and flags; it never decides what goes in a deck. Every number carries its source and time.
  A value it did not read is null and listed under not_captured with the reason, never estimated.
- Read-only on dealer sites: never submit a form, type into a lead form, send a chat message, book a scheduler, start
  a checkout or click a call or text button. Hovering menus, clicking tabs and toggles and running read-only scripts is
  fine. Decline cookie banners. Don't route around a firewall page or a proxy 403; log it and move on.
- Never touch the Dealer Audit Requests sheet or the SEO Audits folder in Drive. Never use my Chrome; this VM has no
  browser but the headless one.
- No paid APIs, ever: the free PageSpeed Insights API is the only key. SpyFu and Google Business Profile are Chrome
  steps that Claude does; the collector never opens spyfu.com or Google Maps.
- No em or en dashes anywhere you write, code comments included; ranges as "X to Y".
- Every capture meant for a deck is PNG at device scale 1 in the 1707 x 1019 viewport the skill names, hidden
  elements hidden first, the mouse parked off the page, a scroll pass before full-page captures, document zoom 1.4 on
  dealer pages and 1.15 on PageSpeed.
- Keys stay in .env. Never print them, never commit them.
- Commit to git in this folder as you go (git init if needed), one commit per check that works.

The work, in order:
1. Decision 7 first: fill platforms.test.json with one live store per platform (Dealer.com, DealerOn, Dealer Inspire,
   Sincro; find them by the markers in config.PLATFORM_MARKERS on stores from my dealer census or the archive tab of
   the audit sheet, never a store that is In progress on the sheet) and run `python3 -m collector platform-test`. Fix
   the test's own logic where it misjudges (a rendered page with no nav match, say), then tell me which platforms load
   headless and which don't, and whether pagespeed.web.dev and bing.com/maps render. That decides what stays in Chrome.
2. PageSpeed: confirm the report page's selectors in pagespeed.py (the gauge block with METRICS, the field card, View
   Treemap, the Desktop tab) against a live report, and whether the page exposes its LHR to a script; make the
   gauge and field captures match the fixture's psi_home_mobile_gauges.png and psi_home_mobile_field.png in framing.
   Confirm the API numbers against the report's, and the treemap count against the API's script-treemap-data.
3. Then each module against one store on a platform that loads headless, in this order: preflight, site.setup_pages,
   site.seo_meta, site.srp_links, popups.timing, site.contact_info, bing.listing, conversion.vdp, site.menu_crawl,
   site.pages. For each: run it, open the captures it made and results.json, compare against what the skill's
   references say the check must produce, fix, rerun. The fixture's captures are the standard for what a capture
   should show.
4. When PSI_API_KEY is empty, make the report page the source of the numbers (pagespeed.report_pictures already
   reads the page's LHR when the page exposes it; find the accessor or read the rendered values) so the collector runs
   with no key at all.
5. The flags (flags.py) against SPEC.md section 6, then the contact sheet, then `python3 -m collector handoff out`
   with HANDOFF_MODE from .env, and confirm the zip lands on the Desktop PC.
6. The Phase 3 gate: pick one single-store dealer, run the collector on it, and write compare_runs.py, which prints
   the collector's results.json beside a facts.json from a Chrome-path capture of the same store (I'll run that side
   the same day in Cowork with the v2 skill and give you its facts.json). Every Tier 1 number must match: counts
   exactly, PageSpeed scores within normal run-to-run drift. Report what matched, what didn't and why.

Report after each numbered step, short: what works, what you changed, what's left to Chrome and why. Don't start
step 3 before I've seen step 1's platform log.

---
