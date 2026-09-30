# The collector: what it gathers, what it writes, what it never does

The collector is Tier 1 of the Dealer Audit Automation Plan (Sep 26): a Python and Playwright process on the agents VM
that gathers the evidence a dealer SEO audit needs, headless, several stores at once, and hands a folder to the Claude
session that runs the dealer-seo-audit-v2 skill. Claude does everything the skill calls judgment: which findings go
in, how each callout reads, what it noticed. The collector's job ends when a store's `results.json`, `captures/` and
`contact_sheet.png` are complete and in the hand-off folder.

The skill's own text is the spec for every check. The collector's author reads these before writing a line:
`references/02_steps.md` (what each check looks for and what counts), `references/04_capture.md` (how each capture
was made in Chrome, with the zoom levels, selectors and workarounds that came from real runs), and
`scripts/chrome_snippets.js` (the page scripts, which the collector ports as they are). This file maps those to the
collector and fixes the file formats the two sides share.

## 1. Rules that never bend

- **It collects and flags; it never decides.** Nothing the collector writes goes onto a slide by itself. A `flags`
  entry is a candidate with the skill's standard line attached; Claude confirms it against the references.
- **Read-only on dealer sites.** It navigates, hovers menus, clicks tabs and toggles, and runs read-only scripts. It
  never submits a form, types into a lead form, sends a chat message, books a scheduler, starts a checkout or clicks a
  "call" or "text" button. When a page needs a click to reveal what the skill reads (Bing's "More hours", a menu's
  hover state), that click is fine.
- **It never touches the Dealer Audit Requests sheet or the SEO Audits folder** in Phases 3 and 4. Phase 5 is where
  it reads the sheet and marks rows Captured, and that gets its own design.
- **A number it did not read is not a number.** Every value in results.json carries where it came from and when. When
  a check fails, the check's `status` says so and `not_captured` lists it with the reason; the collector never fills
  in an estimate, a default or a guess.
- **Every capture meant for a deck is full scale**: PNG, device scale 1 (the skill: "every capture meant for a deck
  runs at scale 1"), the viewport 1707 x 1019 the Desktop PC's Chrome uses, so what lands on a slide matches what the
  Chrome path produces.
- **No em or en dashes anywhere** it writes, code comments included; ranges as "X to Y".
- **One browser profile per store, fresh each run**, with a normal desktop Chrome user agent, en-US, America/New_York.
  No evasion beyond a normal browser: a platform that blocks headless Chromium is logged and left to Chrome.

## 2. What it gathers, step by step

The skill's Steps 1 to 17 (`references/02_steps.md`), with the collector's part and what stays with Claude.

| Skill step | Collector, Tier 1 | Stays with Claude (Chrome) |
| --- | --- | --- |
| 1 Set up | Loads the home page, finds the new inventory SRP (the main menu's New item, or /new-inventory/, /new-vehicles/) and the first in-stock new VDP with a real price; records the three URLs and the SRP's "N new vehicles" text | Confirming the dealer, city, state and brand |
| 2 Google Business Profile | Nothing, in any phase (no Places API: Jonathan's cost rule) | The panel, departments, body shop and Service searches, cover photos: all of Step 2, in Chrome as today |
| 3 Bing listing | bing.com/maps?q=[dealer name and street address]: the panel screenshot at about 700 px wide, every button's text, host and path (the skill's script), the website link's real URL from the bing.com/alink/link?url= wrapper with its query keys, the hours behind the "More hours" toggle, the rating and its source, the description present or not | Reading the lead photo, judging each button's landing page |
| 4 Address, hours, phones | The site's address, sales, service and parts hours and every phone number from the header, footer, hours page, Dealership Info sidebar, tel: links and schema.org JSON-LD; the Bing address and hours; a screenshot of the site's hours block. In a group, the group site's store card for this store | Google's address and hours (Step 2); the comparison and the slide |
| 5 Site speed | PageSpeed mobile and desktop on the home page, and on the home page only (Jonathan, Sep 30, 2026: "we do not need to determine page speed on any page outside of the homepage. it's all dealerships are graded on when it comes to page speed that is measured."): the report page's numbers first (score, FCP, LCP, TBT, CLS, Speed Index, the LCP element's node label) with the API as the fallback, and the gauge block screenshot (section 3 says how). In a group, the group site's home page gets the same run | Quoting the load time; the rerun call when the LCP is a pop-up's image (the collector reruns once on its own and keeps both runs) |
| 6 Tag load | The count of scripts from googletagmanager.com in the same result's script-treemap-data, the list of their names, and the treemap screenshot | Nothing |
| 7 Core Web Vitals | The field data (Chrome UX Report) for the URL: Passed, Failed or No Data, with LCP, INP and CLS and each one's category, mobile and desktop, and the field card screenshot | Naming the failing metric per side in the skill's words |
| 8 Homepage pop-ups | A fresh context, the home page, polling every 100 ms for the vendor overlays the skill names (Gubagoo .gg-chat-wrapper, or the start time of its cdn.gubagoo.io/gb1/ avatar in resource timing; DealerOn #dealerOnCoupon; Wunderkind window.bouncex.campaigns with activation_delay; Podium's #podium-prompt iframe; dealerbluesky #dbs-dynamic-popup-overlay; Tecobi's LIVE SUPPORT bubble) and for any fixed element that appears after load and covers a third of the viewport; seconds from navigation start and from the load event; screenshots before and after; a second vendor recorded the same way; cookies and storage cleared and the page reloaded to catch a cookie-capped pop-up | Whether it counts (a survey modal on the second page view stays out) |
| 9 SEO META | The skill's SEO META script on the home page, SRP and VDP: title and meta lengths, the title text, H1 to H6 counts, and on the home page only the image counts; the visible H1 texts | Judging a generic title, hidden H1s, what to put on the slide |
| 10 Links, inventory, menu | The skill's vehicle-links script on the SRP (count, http:// count, one example); the "N new vehicles" count; every main-menu link (top item, label, href host and path), each one opened with a real navigation: HTTP status, final host and path, redirect to the home page, 404 page, off-site host, group or sister site host, third-party listing site; the menu hovered open with the item boxed in red and the landed page captured; the group site's new count when there is one | Which ones are findings and their wording; GM's parts and accessories links go in the notes |
| 11 AI agent readiness | Nothing. Out since Sep 27; the collector skips PageSpeed's Agentic Browsing checks | Nothing |
| 12 Organic search | Nothing (no SpyFu API: Jonathan's cost rule) | All of Step 12 in Chrome as today: the signed-in tab's same-origin data call for the monthly totals, the overview and Top Organic Competitors cards, the keyword and Kombat tables, the competitor choice, every verdict and line |
| 13 Conversion, SRP and VDP | No PageSpeed on the VDP (Jonathan, Sep 30, 2026: the home page only). The collector's own phone render of the VDP (a fresh context at 412 x 823, device scale 1, a current mobile Chrome user agent, mobile and touch on; the load event plus the pop-up window), its full-page capture cut into four 412 x 823 phone screens with the 4 px #FF2D55 outline; the render's time in Eastern and the vehicle's title, stock and VIN under vdp_render; a VDP that fails to load twice in the phone context is swapped for the next vehicle on the SRP (vehicle_swapped); the VDP's price stack text in order with the biggest price marked; every CTA in the stack with its text, host and whether it leaves the site (the skill's VDP links script); click to call present; the swipe counts to the full price stack and the full CTA stack; whether the pop-up shows on load and on the SRP; the ComplyAuto panel showing on load; a promotion banner across the first screen; the vehicle photo's overlay text | Every judgment on the slide; the iframe check when the phone render is blank |
| 14 Customer experience | Full-page screenshots, zoom 1.4, of the service specials, new vehicle specials, schedule service, trade-in and finance application pages, and of every page the Specials and Research menus open; the text of each specials page (NO RESULTS, No vehicles found, We are currently updating); each specials card's title, price text and image present; vendor banners' text; the research pages' model years against the SRP's model years | What looks careless, unfinished or wrong |
| 15 Content quality | Full-page screenshots of the About Us, finance and lease pages; the first 300 characters of the About Us copy (to compare across sister sites); the home slider's slide alt texts from the source; text baked into images can only be seen, so the screenshots carry it | Stock photos, stale copy, template copy, the sister-site comparison |
| 16 Empty spaces, special hours | The skill's blank-block script on every page it opens and on the blog (elements at least 150 px tall and 300 px wide with no text, no img, picture, video or iframe, computed background-image none), each candidate with its page, position and size and a full-page screenshot; the blog's post count or its "no posts" text; the Special Hours block text from the hours page and any Dealership Info sidebar, each holiday named | Whether a blank block is a missing photo or a spacer or a slider that hadn't loaded; whether a holiday is the next one |
| 17 Extras | Anything odd goes in `noticed` with its capture: a menu label like "New Navigation Node", a schema address that names another store, an empty staff tab | Everything |
| Pre-flight (new) | Before anything else: the site loads over https (two tries, 30 s each); the final host after redirects (a different domain means a rename or a sale); the dealer name in the site's JSON-LD and title against the request's name; the old domain's fate when the request names one; the group site's card for the store when there is a group site; the platform (Dealer.com, DealerOn, Dealer Inspire, Sincro, other) from the page's markers | Whether to leave a store out; Google's listing check comes with Places in Phase 4 |

Phase 4 adds: Tier 2 flags for every threshold in section 6, the group site's store cards everywhere they appear, the
syndication check for research copy, and stores in parallel across a group. No paid API in any phase: Google Business
Profile and SpyFu stay Chrome steps (Jonathan, Sep 29).
Phase 3 may already emit the flags whose numbers it has; they are candidates either way.

## 3. PageSpeed: numbers by API, pictures from the report

The deck shows PageSpeed's own rendering: the gauge block with its METRICS, the field data card, the treemap. The API
returns numbers, not pictures, so the two come from two places and the collector keeps them consistent:

1. **The numbers come from the PageSpeed Insights API**, which is free and needs no billing account (`runPagespeed`,
   strategy mobile then desktop, category performance, the project's key from Decision 2; when no key is wanted, the
   report page's own numbers stand in, see 3): performance score, FCP, LCP, TBT, CLS and Speed Index with their
   display values, the LCP element (the `largest-contentful-paint-element` audit's node label and snippet), the
   `script-treemap-data` nodes, the `full-page-screenshot` data (a webp data URL, 412 px wide on mobile), and the
   `loadingExperience` block for the field data (overall category and each metric's percentile and category; no
   `metrics` means No Data). The keyless quota the skill warns about does not apply to a keyed call.
2. **The pictures come from the report page**, pagespeed.web.dev/analysis?url=[page]&form_factor=mobile, opened
   headless at 1707 x 1019 with the page zoomed to 1.15, the gauge block captured with METRICS at about y 385 and the
   mouse parked off the report, then the field card, then form_factor=desktop for both again, exactly as
   `references/04_capture.md` describes. The treemap comes from the report's View Treemap button (a real click; it
   opens the Lighthouse treemap app in a new page, which the collector screenshots) and the GTM count is checked
   against the API's treemap nodes.
3. **The report page runs its own analysis**, so its numbers can differ from the API run by a little. results.json
   keeps both, labeled `api` and `report`, and the report's numbers are the ones the screenshots show. When the two
   disagree on a score by more than 5 points or on the LCP by more than 1 s, the collector reruns the report once and
   keeps every run in `runs`.
4. **When the report page cannot be used headless** (it does not render, or the platform test in section 7 shows it
   challenges automation), the API numbers stand and the pictures are listed under `not_captured` for Chrome. The
   audit does not wait on the collector.
5. **The LCP rule**: when the LCP element's label is a pop-up's image rather than the page's own content, rerun once,
   keep both runs, and mark which run has the page's main content as its LCP. Claude quotes that one and the notes
   say what the other measured.
6. **No PageSpeed on the VDP** (Jonathan, Sep 30, 2026): the VDP's phone screens come from the collector's own phone
   render (section 2, step 13). A VDP that fails to load twice in that phone context is swapped for the next vehicle
   on the SRP, and results.json says so (vehicle_swapped).

## 4. The captures

All PNG, device scale 1, in `captures/`, named the way the Chief run's capture brief named them, so Claude and the
builders find them without a map. The full frame of every crop stays in `captures/raw/`.

| Name | What it is |
| --- | --- |
| `bing_panel.png` | The Bing Maps panel, about 700 px wide |
| `hours_site.png`, `address_site.png`, `address_bing.png` | The site's hours block; the site's and Bing's address lines |
| `psi_home_mobile_gauges.png`, `psi_home_desktop_gauges.png` | The gauge blocks, page zoom 1.15 |
| `psi_home_mobile_field.png`, `psi_home_desktop_field.png` | The field data cards, or the No Data line |
| `treemap_home.png` | The treemap |
| `popup_before.png`, `popup_after.png`, `popup2_after.png` | The home page before the pop-up, with it open, and a second vendor's |
| `menu_<item>.png`, `dest_<item>.png` | The menu hovered open with the item boxed in red; the page it opens (only for items whose result is not ok) |
| `srp_header.png` | The SRP's "N new vehicles" header |
| `vdp_phone_1.png` to `vdp_phone_4.png` | The four phone screens from the collector's own phone render, 412 x 823 with the 4 px #FF2D55 outline, saved at 1.25 scale (about 505 x 997 px, the size the decks so far carry); the full render stays in `captures/raw/` |
| `vdp_photo.png` | The first vehicle photo, for overlay text |
| `specials_service.png`, `specials_new.png`, `specials_<slug>.png` | Full-page, zoom 1.4 |
| `schedule_service.png`, `trade_in.png`, `finance_app.png` | Full-page, zoom 1.4 |
| `research_<model>.png` | Every page the Research menu opens |
| `about_us.png`, `finance.png`, `lease.png`, `blog.png`, `hours_page.png` | Full-page, zoom 1.4 |
| `slider_<n>.png` | Each home slider slide the collector could show (by alt text order) |
| `empty_<page>_<n>.png` | A page with a blank-block candidate boxed in red |
| `group_card.png` | The group site's card for this store |
| `contact_sheet.png` | Every capture, four to a row with file names and pixel sizes |

Before every capture: hide `#chrome-extension-pull-out-tab-host`, `#podium-bubble` and the Podium iframes, move the
mouse to the far right edge, scroll the page to the bottom once and back so lazy images load. Full-page captures use
Playwright's full_page after a scroll pass, at document zoom 1.4 on dealer pages (the skill's number for a page
rendered small) and 1.15 on PageSpeed.

## 5. results.json

One file per store. Its shape is the Chief run's `facts.json` (the capture brief's schema, which the build agents and
the roll-up's `rollup_data.js` already read), so a group roll-up can be computed from collector output the way it was
from capture agents' output, plus a `collector` block, a per-check `status`, a `captures` index and `flags`.
The reference for every field is `04_agent_briefs/CAPTURE_BRIEF.md` in the v2 handoff, "What to record"; the fields
below are the additions and the ones whose meaning the collector fixes.

```
{
  "collector": { "version": "0.1.0", "host": "agents", "started_at": "2026-10-01 09:02:11 AM ET", "finished_at": ...,
                 "seconds": 412, "platform_headless": "ok | blocked | partial", "notes": [] },
  "request": { "store": "Bay Hyundai", "city": "Panama City", "state": "FL", "url": "https://www.bayhyundai.com",
               "group": "Chief Auto Group", "group_site": "https://www.chiefautogroup.com", "old_domain": null,
               "competitor_candidates": [ { "name": "Hyundai of Dothan", "domain": "hyundaiofdothan.com" } ] },
  "preflight": { "loads": true, "final_host": "www.bayhyundai.com", "redirected_to_other_domain": false,
                 "site_name": "Bay Hyundai", "name_matches": true, "old_domain_result": null,
                 "platform": "Dealer.com", "notes": [] },
  "store", "city", "state", "domain", "platform", "captured_at",
  "pages": { "home", "srp", "vdp", "vdp_vehicle", "vdp_vehicle_detail", "vehicle_swapped", "srp_new_count", "srp_new_count_text" },
  "bing": { ...capture brief fields..., "status": "ok", "buttons": [ { "text", "host", "path", "final_host", "final_path" } ] },
  "address_hours": { ...capture brief fields (google_* left null in Phase 3)..., "phones_raw": [ { "where", "text" } ] },
  "phones": [ { "where", "dept", "number" } ],
  "pagespeed": { "home_mobile": { "api": { "score", "fcp_s", "lcp_s", "tbt_ms", "cls", "si_s", "lcp_element", "field": {...} },
                                  "report": { ...the same fields read from the report page..., "url": "https://pagespeed.web.dev/analysis/.../id" },
                                  "runs": [ ... every run, api and report, with its time and LCP element ... ],
                                  "lcp_is_popup": false, "captures": { "gauges", "field" } },
                 "home_desktop": { ... } },   (the home page only; no vdp_mobile block since Sep 30, 2026)
  "vdp_render": { "status": "ok", "rendered_at": "Sep 30, 2026, 5:12 PM ET", "url": ..., "vehicle": { "title", "stock", "vin" },
                  "screens": [ "vdp_phone_1.png", ... ], "render_height_px": 8224, "attempts": 1, "vehicle_swapped": false },
  "gtm": { "count", "names": [ ... ], "capture": "captures/treemap_home.png" },
  "popup": { "vendor", "selector", "open_s", "load_s", "loads": [ { "open_s", "load_s", "at" } ], "second_vendor": {...},
             "on_srp": bool, "on_vdp_load": bool, "captures": [] },
  "seo_meta": { "home": { "title", "title_len", "meta_len", "h": [6 counts], "h1_visible": [], "images", "no_alt", "no_title" },
                "srp": { ... }, "vdp": { "title", "title_len", "meta_len", "h": [...] } },
  "links": { "srp_vehicle_links", "srp_http_links", "example_http_link" },
  "menu": { "items_total", "opened", "items": [ { "top", "label", "href_host", "path", "status", "result", "landed_host", "landed_path",
            "capture_menu", "capture_dest" } ] },
  "spyfu": null,   (a Chrome step; Claude fills the facts the way the capture brief's schema shows, from the signed-in tab)
  "conversion": { ...capture brief fields..., "price_stack": [ { "label", "text", "value", "biggest": bool } ],
                  "ctas": [ { "text", "host", "leaves_site", "screen": 1 } ], "captures": [] },
  "cx": [ { "page", "url", "capture", "text_flags": [ "NO RESULTS" ], "cards": [ { "title", "price_text", "has_image" } ], "vendor_banners": [] } ],
  "content": [ { "page", "url", "capture", "first_300": "..." } ],
  "about_us_first_para": "...",
  "slider": [ { "n", "alt", "capture" } ],
  "empty_blocks": [ { "page", "url", "x", "y", "w", "h", "capture" } ],
  "special_hours": { "where": "Dealership Info sidebar", "text": "...", "holidays": [ "Christmas Eve", ... ] },
  "blog": { "url", "posts", "no_posts_text", "capture" },
  "group_card": { "address", "hours", "phone", "links": [ { "text", "host" } ], "new_count", "capture" },
  "noticed": [ { "what", "capture" } ],
  "flags": [ { "check": "site_speed_desktop", "section": "Site Speed", "value": 32, "threshold": 50,
               "line": "Desktop site speed is below 50", "evidence": [ "captures/psi_home_desktop_gauges.png" ] } ],
  "not_captured": [ { "what", "why" } ],
  "checks": { "preflight": "ok", "bing": "ok", "pagespeed_home_mobile": "ok", "pagespeed_home_desktop": "ok", "vdp_render": "ok", ... },
  "captures": { "bing_panel.png": { "page": "https://www.bing.com/maps?q=...", "w": 700, "h": 1043, "at": "09:14:02 AM ET" }, ... }
}
```

Numbers are kept exactly as displayed (the display string beside the parsed number where PageSpeed or SpyFu shows
"1.03k"). Every time is Eastern, written the way the skill's notes want it ("Sep 27, 2026, 12:41 AM ET"), so it can be
quoted into a slide's notes as it is. Nulls mean "not read", never zero.

## 6. Flags (Tier 2), the skill's thresholds as numbers

Each flag carries the check, the value, the threshold and the skill's standard line. They are candidates; Claude
confirms each one against `references/02_steps.md`. Phase 3 emits the ones its numbers cover; Phase 4 completes them.

| Check | Flag when | Standard line |
| --- | --- | --- |
| Site speed mobile | score under 20 | "Mobile site speed is below 20" |
| Site speed desktop | score under 50 | "Desktop site speed is below 50" |
| Mobile LCP | lab LCP over 2.5 s | "On a phone, the main content takes N s to load" |
| Desktop LCP or TBT | LCP over 2.5 s, else TBT reported | "On desktop, scripts block the page for a combined N ms" |
| Tag load | 8 or more GTM scripts | "N GTMs loading on the home page" |
| Core Web Vitals | field data Failed on a side | "[Store] fails Core Web Vitals on phones" (the failing metric named per side) |
| Homepage pop-up | any overlay opens on its own | "Delay homepage pop-ups 15 seconds to improve website load time" |
| Images | any home page image without ALT or TITLE | "N of M images are missing ALT text" |
| Titles and metas | home or SRP title over 60, meta over 160 | the counts in a grid |
| Headers | home with no H1, SRP with no H2 or more than one H1 | "Optimize the SRP template down to one H1" |
| Vehicle links | any http:// vehicle link on an https:// SRP | "All N vehicle links use http:// on an https:// site" |
| Menu | a 404, a home-page redirect, an off-site host, a group or sister site, a third-party listing site | the skill's Broken Link and Off-Site Link lines |
| Organic, competitor | not flagged by the collector (SpyFu is a Chrome step); the skill's thresholds still apply when Claude reads SpyFu | Claude's, from references/02_steps.md |
| Hours, address | any schedule or address format that differs between Bing and the site (Google's come from Claude's Chrome read) | "Use one address format on Google, Bing and the site" |
| Price stack | the biggest price is a fee, or no selling price | "The VDP's big price is the $N processing fee" |
| CTA | a CTA host that is not the site | "The [name] CTA sends shoppers off the site" |
| Specials | a specials page with NO RESULTS, No vehicles found or the updating text | "The [X] Specials page is empty" |
| Research pages | a research page's model year behind the SRP's | Model Research Pages |
| Slider | a slide alt naming last year's model | Content Quality |
| Blog | no posts | "The blog has no posts" |
| Special hours | a holiday that is not the next one coming up | "The site still shows Christmas and New Year's hours" |
| Empty blocks | any candidate | never a flag on its own: candidates go to Claude with their shots |

## 7. The platform test (Decision 7)

Before the collector is relied on, one live store per platform (Dealer.com, DealerOn, Dealer Inspire, Sincro, plus
pagespeed.web.dev and bing.com/maps) is opened headless the way the collector will open every page. The log records,
per site: the HTTP status, the page title, whether the home page's main content rendered (the menu and a vehicle card
found), whether a firewall or challenge page came back (Cloudflare, Incapsula, "Access denied", a captcha), and the
time to load. A platform that blocks headless Chromium is written into `platforms.json` as `chrome_only`, and every
store the pre-flight identifies on that platform goes straight to Chrome with a note in `not_captured`. The test is
rerun whenever a store on an ok platform starts failing.

## 8. Running it, and the hand-off

- `collect STORE.json [--out DIR] [--jobs N]`: one store, or a group file with one entry per store, N stores at once
  (default 3 on the 4-core VM). Each store gets `DIR/<domain>/` with `results.json`, `captures/`, `captures/raw/`,
  `contact_sheet.png` and `collector.log`. A group also gets `DIR/group/` for the group site.
- `preflight STORE.json`: only the pre-flight, in seconds, so a sold, renamed or dead store surfaces before an hour of
  capture (the Chief run's Coast Chevrolet lesson).
- `platform-test`: section 7.
- `handoff DIR`: zips each store folder as `<domain>_<YYYY-MM-DD>.zip` and copies the zips into the sync folder
  (Decision 4: a folder the Desktop PC mirrors, SETUP.md), with a `manifest.json` naming each zip, its store, its size
  and its md5. The Cowork session connects that folder and stages the zips it needs.
- Timeouts: 30 s per navigation, 90 s per PageSpeed report, 20 s per pop-up poll, 10 minutes per store before the run
  moves on and lists what it did not finish. Every step writes results.json as it goes, never only at the end.

## 9. What Claude does with it (the skill side)

The v2 skill's SKILL.md carries this as "Reading a capture folder". In short: when a store's zip under a week old is in
the connected folder, Claude unzips it into the store folder, reads results.json, looks at the contact sheet, confirms
every number and flag against the references, captures in Chrome whatever is in `not_captured` and whatever the skill
leaves to judgment (Google Business Profile and SpyFu in full, anything it wants to see for itself), and writes
findings.json from there. The recap says what the collector flagged, what Claude found in Chrome, and what the
collector could not capture.

## 10. The Phase 3 gate

One dealer audited both ways on the same day: once by the collector, once in Chrome with the current skill. Every
Tier 1 number in results.json matches the Chrome capture (scores within PageSpeed's normal run-to-run drift, counts
exactly), and the two decks match slide for slide on the Tier 1 sections. The Chrome run's facts.json is the reference;
`compare_runs.py` (to be written on the VM) prints the two side by side.
