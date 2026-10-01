# Setup on your side, before the VM build starts

Three things, none of them code, and nothing that bills. Step 1 gives the collector its one free key; step 2 makes
the hand-off folder; step 3 prepares the VM. The key stays on your side: put it in the VM's `.env` and never paste it
into a chat. No SpyFu key and no Places API: both stay Chrome steps (your call, Sep 29).

## 1. The PageSpeed Insights API key (Decision 2)

1. Open https://console.cloud.google.com with your digital1group.com account.
2. Create a project (the project picker at the top, New Project): name it `Digital 1 Audits`.
3. With that project selected, open APIs & Services, then Library, search "PageSpeed Insights API" and click Enable.
4. Open APIs & Services, then Credentials, click Create credentials, then API key. Copy the key.
5. Click the new key to edit it: under API restrictions choose Restrict key and tick only PageSpeed Insights API. Save.
6. On the VM, put it in `~/dealer-audit-collector/.env` as `PSI_API_KEY=...`.

The PageSpeed Insights API is free, needs no billing account, and its default daily quota is far above an audit's 3 to
6 runs per store. If you'd rather not make a key at all, leave `PSI_API_KEY` empty: the collector then reads the
numbers from the report page it opens for the pictures, which is what Chrome does today. Never enable the Places API
on this project.

## 2. The hand-off folder (Decision 4)

The collector writes each store's zip to a folder on the VM, and that folder is mirrored to a folder on the Desktop
PC. The Cowork session connects the Desktop PC folder (the way it connected Downloads on Sep 29: one permission prompt
per session) and pulls what it needs in one call per zip.

Two ways to mirror it; start with A, move to B when the collector runs on its own.

**A. Taildrop (two settings, then no setup).** Both machines are on your tailnet. From the VM:
`tailscale file cp <store>.zip jon-d1-pc-2:` sends the zip to the Desktop PC, where the Tailscale client saves it in
`C:\Users\jon\Downloads`. The `handoff` command does this when `HANDOFF_MODE=taildrop`. Downloads is the folder the
session connects. Two things found on Sep 30, 2026:

1. The Tailscale daemon only lets root, or a set operator, send files. Once on the VM:
   `sudo tailscale set --operator=$USER`. Without it `tailscale file cp` says "Access denied: file access denied"
   and the `handoff` command reports that with the fix.
2. The Desktop PC's name on the tailnet is `jon-d1-pc-2` (its MagicDNS name, as `tailscale status` lists it), not
   `jon-d1-pc`. Set `TAILDROP_TARGET=jon-d1-pc-2` in `.env`. When the configured name is not on the tailnet but a
   Windows node with that name plus a suffix is, `handoff` sends there and says so.

Windows Taildrop never overwrites: a repeat arrives as `name (1).zip`, so every send writes its own manifest,
`manifest_<YYYY-MM-DD_HHMM>ET.json`. The file the session should trust is the newest manifest.

To send a file the other way (a Chrome-path facts.json for `compare_runs.py`), on the PC right-click the file,
choose Show more options, then Send with Tailscale, and pick `agents`; or in PowerShell
`& "C:\Program Files\Tailscale\tailscale.exe" file cp "$env:USERPROFILE\Downloads\facts.json" agents:`.
On the VM, `tailscale file get ~/inbox` fetches what was sent.

**B. Syncthing (continuous).** Install Syncthing on the Desktop PC (syncthing.net, the Windows installer runs it as a
service with a web page at localhost:8384) and on the VM (`docker run -d --name syncthing --restart unless-stopped
-p 8384:8384 -p 22000:22000 -v ~/audit-handoff:/var/syncthing/handoff syncthing/syncthing`). Pair the two devices
(Add Remote Device on each side with the other's device id, reachable over Tailscale), then share the VM's `handoff`
folder to the Desktop PC as `C:\Users\jon\AuditCaptures`, send-only from the VM. The `handoff` command copies zips
into `~/audit-handoff` when `HANDOFF_MODE=folder`, and Syncthing does the rest. `C:\Users\jon\AuditCaptures` is then
the folder the session connects.

Either way the Desktop PC's folder holds a manifest per send and one zip per store, `<domain>_<YYYY-MM-DD>.zip`.

## 3. The VM

On `agents` (ssh jonneale83@agents):

```
sudo apt update && sudo apt install -y python3-venv python3-pip unzip
mkdir -p ~/dealer-audit-collector && cd ~/dealer-audit-collector
# unzip dealer-audit-collector.zip here (this package)
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium --with-deps
cp .env.example .env    # then put PSI_API_KEY in it, or leave it empty for the report page
python3 -m collector platform-test     # Decision 7, the first job
```

Claude Code on the VM (Decision 5): install it there per Anthropic's docs if it isn't already, open
`~/dealer-audit-collector`, and paste KICKOFF_PROMPT_VM.md. The v2 skill folder (`dealer-seo-audit-v2`, unzipped) and
the golden fixture go beside it, since the kickoff has the VM session read the skill's references.

Node is only needed for the Lighthouse report generator if the VM build chooses to render reports locally instead of
opening pagespeed.web.dev; the default design opens the report page, so Node is optional.

## The sheet trigger (the collector starts itself)

`python3 -m collector trigger` reads the Audit Requests tab of the Dealer Audit Requests sheet (read-only), runs the
collector on every row whose Status and Audit Results are blank, and Taildrops each zip to the Desktop PC, where the
scheduled Chrome run picks it up. It never writes to the sheet. A cron line on the VM runs it every 15 minutes; a lock
file keeps two ticks from colliding, and state/trigger.json remembers which rows ran (a row runs again only when its
Timestamp changes, which is what a re-run on the sheet does).

One-time setup, in the same Google Cloud project as the PageSpeed key (free, no billing):

1. APIs & Services > Library: enable the Google Sheets API.
2. IAM & Admin > Service Accounts > Create: name it `audit-collector`, no roles needed. Open it, Keys > Add key >
   JSON, and download the file.
3. Copy the key to the VM as `~/dealer-audit-collector/.secrets/service-account.json` (the folder is git-ignored):
   from PowerShell, `scp C:\Users\jon\Downloads\<key>.json jonneale83@agents:~/dealer-audit-collector/.secrets/service-account.json`
   after `ssh jonneale83@agents mkdir -p ~/dealer-audit-collector/.secrets`.
4. Share the Dealer Audit Requests sheet with the service account's email (it ends in `.iam.gserviceaccount.com`,
   shown on the service account's page) as a Viewer. Viewer is all the trigger ever uses.
5. On the VM: `python3 -m collector trigger --dry-run` lists what is waiting without starting anything. The cron line
   (installed with `crontab -l` to check) is:

   `*/15 * * * * cd /home/jonneale83/dealer-audit-collector && .venv/bin/python3 -m collector trigger >> state/trigger.log 2>&1`

The log is `state/trigger.log`; each run's request file lands in `requests/auto/` and its output under `out/auto/`.
Until the key is in place the trigger logs "no service account key" every 15 minutes and does nothing else.

## The push trigger (the sheet tells the collector to go)

Jonathan's call, Oct 1, 2026: the sheet pushes a new request to the collector the moment it lands, instead of the VM
polling the sheet every 15 minutes. The sheet's Apps Script sends the request rows themselves, so the VM needs no
Google credential at all (the service account route above stays documented in case it is ever wanted).

How it runs: `python3 -m collector listen` is a small HTTP server on the VM (127.0.0.1:8787) that cron starts at boot
and a watchdog pokes every five minutes (`bin_listener.sh`). Tailscale Funnel fronts it at
https://agents.taild0ebeb.ts.net so Google's servers can reach it over HTTPS. The Apps Script
(`apps-script/Trigger.gs`) POSTs the Audit Requests tab's unfinished rows to /trigger with a shared secret in the
X-Trigger-Secret header: on every form submit, on every change to the sheet, and once an hour as a sweep. The listener
applies the same rules as the polling trigger (unfinished rows only, groups by Auto Group Name, one run per row, one
run at a time) and Taildrops each zip to the Desktop PC. Nothing on the VM reads or writes the sheet.

One-time setup:

1. Funnel. On the VM `tailscale funnel --bg 8787` prints a link the first time; open it as the tailnet admin and
   enable Funnel for the node (it adds the `funnel` node attribute to the tailnet policy). `tailscale funnel status`
   then shows https://agents.taild0ebeb.ts.net proxied to 127.0.0.1:8787.
2. The secret. `.env` on the VM carries TRIGGER_SECRET (generated when the listener was set up; `grep TRIGGER_SECRET
   .env` shows it) and LISTENER_PORT=8787.
3. The script. In the sheet, Extensions > Apps Script: add a file Trigger.gs with the contents of
   `apps-script/Trigger.gs`. Project Settings > Script Properties: COLLECTOR_URL =
   https://agents.taild0ebeb.ts.net/trigger and TRIGGER_SECRET = the value from .env. Triggers: onRequestSubmitted
   (from spreadsheet, on form submit), onSheetChanged (from spreadsheet, on change), sweepUnfinished (time-driven,
   hourly). Run sweepUnfinished once from the editor to authorize it; its log should end with "collector answered 202".
4. Check from the VM: `tail state/listener.log` shows each push with the jobs it queued; `curl -s localhost:8787/health`
   answers ok.
