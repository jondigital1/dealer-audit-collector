# Phase 3 report: the collector, built and gated on the agents VM (Sep 30, 2026)

Also a shared doc: https://claude.ai/code/artifact/3e5cfa9e-7fba-438e-a46d-14f2359c702a

The collector runs. It gathers a store's Tier 1 evidence headless, writes results.json, captures/ and a contact sheet,
and hands the zip to the Desktop PC by Taildrop. It was built check by check against Bay Hyundai (Dealer.com, the
golden fixture) and gated on Hanania Hyundai of Orange Park (Dealer Inspire) against a same-day Chrome-path
facts.json. Seventeen commits in this folder, one per check that works; `compare_runs.py` prints the two sides.

## 1. What runs, and how long

`python3 -m collector collect STORE.json --out out` runs, in the skill's order: pre-flight, set-up (home, new SRP,
first priced VDP), PageSpeed on the home page (report page first, treemap), the pop-up pass, SEO META, vehicle links,
contact info, Bing, the VDP (PageSpeed mobile, phone screens, price stack, CTAs, a phone-sized layout for swipes),
the menu crawl, the pages (specials, service, finance, About Us, blog, research), flags, the contact sheet.
Every module is wrapped: a failure records the check and the run moves on. results.json is written after every step.

| Store | Platform | Time | Captures | Flags | Not captured |
| --- | --- | --- | --- | --- | --- |
| Bay Hyundai | Dealer.com | 11 min | 48 | 16 | SpyFu, the group card's picture, a lease page the site lacks |
| Hanania Hyundai of Orange Park | Dealer Inspire | 11 min | 60 | 15 | SpyFu, pop-up timing (no pop-up opened), trade-in, lease and hours pages the menu lacks |

Budget: a 15 minute soft budget (past it, extra research and specials pages are skipped and listed) and a 25 minute
hard stop, set from these runs. The zips run 54 MB (Bay Hyundai) and 78 MB (Hanania) with full-page captures at zoom 1.4.

## 2. The platform test (Decision 7)

All four platforms, pagespeed.web.dev and bing.com/maps load headless. One finding decided the browser: Dealer.com's
Akamai edge answers Playwright's default headless shell with a 403 Access Denied page, and serves the full Chromium in
its new headless mode normally. The collector launches the full browser with a desktop Chrome user agent at the
browser's own version. `platforms.json` holds the log; the markers are the census's verified patterns.

| Platform | Store tested | Loads headless | Time to DOM |
| --- | --- | --- | --- |
| Dealer.com | bayhyundai.com | yes | 1.1 s |
| DealerOn | longotoyota.com | yes | 0.9 s |
| Dealer Inspire | bayridgehonda.com | yes | 1.9 s |
| Sincro | arenabuickgmc.com | yes | 21 s |
| pagespeed.web.dev | | yes | 0.5 s |
| bing.com/maps | | yes, panel renders | 0.6 s |

## 3. PageSpeed

- The report page first (Jonathan, Sep 30): it exposes both results as `window.__LIGHTHOUSE_MOBILE_JSON__` and
  `__LIGHTHOUSE_DESKTOP_JSON__`, so the numbers the pictures show are the numbers quoted, and the collector runs
  with no key at all. The API is called only for a side the report page did not give.
- The gauge block (category header plus METRICS, with the Captured at line), the field card cut above Other
  notable metrics, the treemap from a real View Treemap click; captures at zoom 1.15 match the fixture's framing.
- The LCP node lives where the skill reads it, `lcp-breakdown-insight.details.items`, as a `{type: "node"}` item
  after the subpart table, when Lighthouse attributed the LCP to an element. Runs without one are listed under
  not_captured so Chrome confirms the element before a load time is quoted.
- Retries follow the skill: a failed report (Something went wrong, DEADLINE_EXCEEDED, throttled) waits 20 s and runs
  once more; a failed side leaves the other side's evidence in place.
- Drift is real: Bay Hyundai's home page read 28 to 35 mobile and 5.9 to 20.4 s LCP across one hour of runs, every
  run warning that the page loaded too slowly. results.json keeps every run.

## 4. The pop-up pass (Jonathan's call, Sep 30)

Gubagoo's chat invite renders only when navigator.webdriver reads false, as it does in Lighthouse's Chrome. The pass
now runs a normal load first (webdriver true, recorded under normal_pass); only when that load came back as a real
page (status under 400, no challenge words, a menu with images) does a second browser with the automation flag off
time the pop-up the skill's way (two loads, storage cleared between, then the SRP). A blocked or challenged load skips
the second pass and marks the store chrome_only. `tests/test_popups_blocked.py` proves both branches with a local
server playing a 403 page, a challenge page and a real page. Everything else keeps the flag.

| Bay Hyundai, Gubagoo invite (300 x 364) | Collector, Sep 30 | Chrome, Sep 27 |
| --- | --- | --- |
| First load: opens / load event | 6.5 s / 4.1 s | 7.2 s / 2.4 s |
| Second load, storage cleared | 6.2 s / 1.7 s | 6.5 s / 1.7 s |
| On the SRP | 6.6 s | 7.0 s |

## 5. The gate: Hanania Hyundai of Orange Park, Sep 30

Collector at 9:33 AM ET (SEO META and set-up refreshed at 4:54 PM), Chrome path 4:01 to 4:24 PM ET.

Matches exactly: the SRP and VDP, 469 new on the SRP, home title 59 and meta 148, home headers [1,17,1,4,2,0], SRP
title 60 and meta 133, SRP headers [1,43,4,7,4,0], 0 http:// vehicle links, the site address, sales and service
hours, field data (Failed on phones, INP 256 ms; Passed on desktop), ComplyAuto on load, Start Buying Process as the
CTA leaving the site, the Payment Calculator 404, one blog post, no special hours.

Within drift: home mobile 30 against 38, desktop LCP 4.2 against 4.1 s. Both sides' home mobile LCP was the ComplyAuto
banner text (the pop-up case the rerun rule covers); the collector names the same node.

Differences and their causes:
- Blank photo spaces: the collector found the Finance page's 319 px blank band above the Finance Center banner
  (boxed in empty_finance.png); the Chrome run did not open the Finance page. The band carries invisible heading
  text, so the skill's DOM rule misses it; the collector now also scans each full-page capture's pixels for flat
  bands of at least 150 by 300 CSS px, beside the DOM candidates.
- Holiday hours: none on the site today on either side; the Sep 29 finding has been fixed by the dealer. The
  Dealership Info sidebar's text is recorded on every run so a return shows.
- Phones: the collector's fresh visit read the site's (904) numbers; the Chrome session with cookies was served the
  call-tracking swap numbers (866 and 877). Both are what the site showed. Worth a line in the skill.
- Images 52 / 27 / 52 against 55 / 28 / 55: lazy loading; the SEO META pass now scrolls at 400 px per 300 ms, which
  is what this site's model carousel needs. The remaining three are tracking pixels and map tiles counted separately.
- GTM 11 against 10: the collector's run also loaded a placeholder container, G-9999999999. Both lists are kept.
- Desktop 43 against 55, VDP 12 / 14.0 s against 24 / 9.8 s: drift, and a different first vehicle at 9:33 AM.
- Menu off-site 4 against 2 and empty pages 2 against 1: the Chrome run's own summary counts 4 other-host links
  (two blocked by Chrome's site permissions); the collector's second empty page is Parts Special Offers reading
  "We are currently updating".

Verdict: every count the collector reads matches the Chrome path; PageSpeed differs by run-to-run drift; on the two
flags asked about, the collector found the blank spaces the Chrome run missed and both agree the holiday hours are gone.

## 6. What the live sites taught (all in the code, with dates)

- Dealer.com's SRP links VDPs as /new/Make/...; the skill's a[href*="/inventory/"] finds nothing there, so the
  collector falls back to the platform's pattern and records which selector counted.
- A page's images: the page's own count, with map-widget tiles and carousel clones counted beside it; a carousel's
  state at read time moves the ALT count (Bay Hyundai 26 against Chrome's 46 on Sep 27).
- Dealer Inspire: the SRP count reads "469 New HYUNDAI in Jacksonville, FL"; Service & Parts and About Us sit under
  a More overflow entry, so the menu shot hovers the overflow first and is taken with the mouse still on the menu;
  hidden menu anchors have no innerText, so labels fall back to textContent.
- Bing Maps is a fixed-height app whose sidebar scrolls on its own; the panel is captured at the skill's zoom 1.35
  in a temporarily taller frame, entity card through the review-source blocks.
- Cookie panels are declined (never accepted) before captures, so ComplyAuto's panel no longer sits in full-page shots.
- The group site keeps Bay Hyundai's card in a hidden map info window; its text is recorded, the picture is not.
- Lighthouse 13.5's API response carries no LCP node for the home page; the report page's does when attributed.

## 7. Hand-off

`python3 -m collector handoff out` zips each store folder and sends the zips and a manifest named by the send time
(manifest_2026-09-30_1656ET.json, since Windows Taildrop keeps a repeat as "name (1)") to the Desktop PC. Needed
once on the VM: `sudo tailscale set --operator=$USER`. The Desktop PC's tailnet name is jon-d1-pc-2 (.env updated).
Both stores' zips are in its Downloads as of 4:56 PM ET, Sep 30.

## 8. What stays with Chrome

SpyFu and Google Business Profile (the cost rule). The LCP element when a report carries no node. The pop-up timing
on a store whose home page is blocked or challenged. Anything listed under not_captured, with its reason. The
collector never touched the Dealer Audit Requests sheet or the SEO Audits folder.

## 9. Open for Phase 4

- Group runs in parallel (stores at once), the group site's cards everywhere they appear, the syndication check.
- The phones note in the skill: the collector sees a site's default numbers, not the tracking swaps.
- Zip size: 50 to 80 MB per store; if the session's folder connector has a ceiling, full-page captures could be
  re-encoded or the raw frames left out.
- A blank block beside copy (not full width) is only in the capture, not in the band scan; Claude reads the shot.
- SRP vehicle-link counts differ by method (the collector's unique count against the Chrome read's), only the http://
  count is the finding.
- The one-off VM settings (the Tailscale operator, the .env target) belong in SETUP.md.
