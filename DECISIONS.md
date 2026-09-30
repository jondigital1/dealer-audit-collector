# Decisions for the collector (Jonathan, Sep 29, 2026)

The seven decisions README section 7 of the v2 handoff asked for, answered in the Cowork session that built Phases 1
and 2. They settle where the collector runs and how it talks to the audit; none of them changes the audit itself.

| # | Decision | Answer | What it means for the build |
| --- | --- | --- | --- |
| 1 | SpyFu API access | No (revised the same night: the SpyFu API is being dropped) | SpyFu stays a Chrome step exactly as in v1: the numbers from the same-origin call the skill makes in the signed-in tab, the overview and Top Organic Competitors card screenshots as today. The collector never touches SpyFu |
| 2 | Google APIs | PageSpeed Insights API only (free, no billing account); the Places API never | A Google Cloud project with the PageSpeed Insights API enabled and its own key (SETUP.md); the report page is the fallback if Jonathan prefers no key at all. Google Business Profile stays a Chrome step for good |
| 3 | Collector host | The agents VM on the SER8 (Ubuntu Server 24.04, 4 cores, 8 GB, Docker, Tailscale SSH as jonneale83@agents) | Not the Yoga (16 GB, no upgrade path, network on a USB-C adapter) and not the Desktop PC (it is every audit's Chrome since Sep 29). Never the Legion |
| 4 | Hand-off road | The VM syncs captures to a folder on the Desktop PC | The Cowork session connects that folder and pulls each store's zip in one call. Tested the same night: the Drive connector could not carry an 8 MB file into a session, so Drive alone is not a road. SETUP.md has the two ways to sync |
| 5 | Where v2's collector is built | Claude Code on the agents VM | This cloud workspace cannot reach dealer sites or PageSpeed, so the collector is written and tested on the VM against live stores. KICKOFF_PROMPT_VM.md is what to paste |
| 6 | The v2 skill's name and trigger | dealer-seo-audit-v2, triggering by name only, through the pilot | At Phase 5, v2 takes over the current skill's trigger description word for word and the current skill retires |
| 7 | Platforms that block headless browsers | The VM build tests them first | The collector's first job is a pre-flight against one live store per platform (Dealer.com, DealerOn, Dealer Inspire, Sincro), logging which load headless and which serve a firewall page. That log decides what stays in Chrome |

Cost rule (Jonathan, Sep 29, 9:10 PM): no paid APIs, ever. The collector runs on the free PageSpeed Insights API (or the
report page) and nothing else; SpyFu and Google Business Profile are Chrome steps.

Home page rule (Jonathan, Sep 30, 4:18 PM ET), on top of the cost rule: PageSpeed runs on the home page only. His words:
"we do not need to determine page speed on any page outside of the homepage. it's all dealerships are graded on when it
comes to page speed that is measured." So no PageSpeed on the VDP: the VDP's four phone screens come from the
collector's own phone render (412 x 823, a mobile Chrome user agent), and a VDP that fails to load twice there is
swapped for the next vehicle on the SRP. Home mobile and desktop stay as they are (the report page, the API as the
fallback, the treemap, the pop-up LCP rerun rule); in a group, the group site's home page gets the same run.

Standing rules that apply to everything the collector produces (Jonathan, Sep 29): no em or en dashes anywhere,
code comments included, ranges as "X to Y"; the collector never decides what goes in a deck, it collects and flags;
it never writes to the Dealer Audit Requests sheet or the SEO Audits folder in Phases 3 and 4; and it never submits a
form, sends a chat message, books a scheduler or clicks a lead button on a dealer site.
