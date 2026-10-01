"""The sheet trigger: start the collector on its own when a request lands on the Dealer Audit Requests sheet.

Reads the Audit Requests tab (the Google Form's tab) read-only through the Sheets API with a service account the sheet
is shared with as a Viewer. The collector never writes to the sheet (DECISIONS.md): the row's Status, links and dates
belong to the Chrome run that finishes the audit. What this does, every time cron runs it:

1. Read every row of the tab. A row is a job while its Status and its Audit Results are both blank; In progress, On hold
   and Complete rows are left alone, and a Timestamp in the future is a typo that waits for Jonathan (references/
   12_requests_sheet.md). Rows that share an Auto Group Name are one group: the row that carries the Store websites list
   is the group itself (its Dealer URL is the group site when it is not one of the stores), the others are its stores.
2. Skip what was already collected: a local ledger (state/trigger.json) keys each row by its Timestamp and Dealer URL,
   so a row runs once, and runs again only when its Timestamp changes (a re-run on the sheet moves the Date).
3. For each job write the request file under requests/auto/, run the collector on it, zip and Taildrop the result to
   the Desktop PC the way `collect --handoff` does, and record the outcome in the ledger. One job at a time, behind a
   lock file, so two cron ticks never collect the same store twice.

A row with a blank city or state (the form's store rows come that way) still runs: the pre-flight reads the store's
name from its site and the Bing step falls back to the schema.org address for the city and state.

Usage: python3 -m collector trigger [--dry-run] [--csv FILE] [--once]
  --dry-run  list the jobs and what they would run, start nothing, write nothing
  --csv      read a CSV export of the tab instead of the API (tests, and a sheet shared another way)
  --once     run the first job only (the cron line runs everything that is waiting)
"""
import csv
import fcntl
import io
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config
from .store import domain_of, now_et

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / 'state'
LEDGER = STATE / 'trigger.json'
LOCK = STATE / 'trigger.lock'
AUTO = ROOT / 'requests' / 'auto'
OUT = ROOT / 'out' / 'auto'
ET = ZoneInfo('America/New_York')
SCOPE = 'https://www.googleapis.com/auth/spreadsheets.readonly'
# the form's headers, as the tab prints them (references/12_requests_sheet.md); matched case-insensitively by prefix
COLS = {'timestamp': 'Timestamp', 'consultant': 'Consultant', 'name': 'Dealership Name', 'city': 'Dealer City', 'state': 'Dealer State',
        'url': 'Dealer URL', 'email': 'Email Address', 'is_group': 'Is this a dealer group', 'group': 'Auto Group Name',
        'sites': 'Store websites', 'status': 'Status', 'summary': 'SEO Audit Summary', 'results': 'Audit Results',
        'rollup': 'Group Wide Roll', 'checklist': '60 Day Checklist'}


def log(msg):
    print(f'{now_et()}  trigger: {msg}', flush=True)


# ---------------------------------------------------------------- reading the tab
def rows_from_table(table):
    """Header row plus value rows -> list of dicts keyed by COLS."""
    if not table:
        return []
    heads = [str(h or '').strip().lower() for h in table[0]]
    idx = {}
    for key, label in COLS.items():
        for i, h in enumerate(heads):
            if h.startswith(label.lower()):
                idx[key] = i
                break
    out = []
    for n, row in enumerate(table[1:], start=2):
        row = list(row) + [''] * (len(heads) - len(row))
        d = {key: str(row[i]).strip() if i < len(row) and row[i] is not None else '' for key, i in idx.items()}
        d['row'] = n
        if any(d.get(k) for k in ('name', 'url', 'group')):
            out.append(d)
    return out


def read_csv(path):
    with open(path, newline='', encoding='utf-8-sig') as f:
        return rows_from_table(list(csv.reader(f)))


def read_sheet():
    """The Audit Requests tab through the Sheets API, read-only, as the service account the sheet is shared with."""
    import requests
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account
    key = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON') or str(ROOT / '.secrets' / 'service-account.json')
    if not Path(key).exists():
        raise RuntimeError(f'no service account key at {key}: SETUP.md, "The sheet trigger"')
    creds = service_account.Credentials.from_service_account_file(key, scopes=[SCOPE])
    creds.refresh(Request())
    h = {'Authorization': f'Bearer {creds.token}'}
    base = f'https://sheets.googleapis.com/v4/spreadsheets/{config.REQUESTS_SHEET_ID}'
    meta = requests.get(base, params={'fields': 'sheets.properties'}, headers=h, timeout=30)
    meta.raise_for_status()
    title = next((s['properties']['title'] for s in meta.json().get('sheets', []) if s['properties'].get('sheetId') == config.REQUESTS_TAB_GID), None)
    if not title:
        raise RuntimeError(f'tab gid {config.REQUESTS_TAB_GID} is not on the sheet')
    vals = requests.get(f"{base}/values/{requests.utils.quote(title, safe='')}", params={'valueRenderOption': 'FORMATTED_VALUE'}, headers=h, timeout=60)
    vals.raise_for_status()
    return rows_from_table(vals.json().get('values', []))


# ---------------------------------------------------------------- picking the jobs
def parse_ts(t):
    for fmt in ('%m/%d/%Y %H:%M:%S', '%m/%d/%Y %I:%M:%S %p', '%m/%d/%Y %H:%M', '%m/%d/%Y', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(t.strip(), fmt).replace(tzinfo=ET)
        except ValueError:
            continue
    return None


def https(u):
    u = (u or '').strip()
    if not u:
        return ''
    if not re.match(r'https?://', u, re.I):
        u = 'https://' + u
    return u.rstrip('/')


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', (s or '').lower()).strip('-')[:60] or 'request'


def row_key(r):
    return f"{r.get('timestamp', '')}|{domain_of(https(r.get('url'))) or r.get('name', '')}"


def unfinished(r, now=None):
    """Blank Status and blank Audit Results, with a Timestamp that is not in the future."""
    if r.get('status') or r.get('results'):
        return False
    ts = parse_ts(r.get('timestamp', ''))
    if ts and ts > (now or datetime.now(ET)) + timedelta(minutes=5):
        return False
    return bool(https(r.get('url')) or r.get('sites'))


def store_spec(r):
    name = r.get('name') or domain_of(https(r.get('url')))
    if re.fullmatch(r'[a-z0-9.-]+\.[a-z]{2,}', (name or '').lower()):
        name = None   # the form's script puts the bare domain in for a group's store row; the pre-flight reads the real name
    return {'store': name, 'city': r.get('city') or None, 'state': (r.get('state') or '').upper()[:2] or None, 'url': https(r.get('url')),
            'brand': None, 'towns': [], 'consultant': r.get('consultant') or None, 'email': r.get('email') or None, 'sheet_row': r.get('row')}


def jobs_from_rows(rows, ledger, now=None):
    """Every request waiting on the tab that the ledger has not seen, as collector request specs."""
    waiting = [r for r in rows if unfinished(r, now)]
    done = set(ledger.get('done', {}).keys())
    jobs, used = [], set()
    # groups first: rows that share an Auto Group Name
    by_group = {}
    for r in waiting:
        g = r.get('group', '').strip()
        if g and (r.get('is_group', '').lower().startswith('y') or r.get('sites')):
            by_group.setdefault(g.lower(), []).append(r)
    for g, members in by_group.items():
        keys = [row_key(r) for r in members]
        if all(k in done for k in keys):
            used.update(id(r) for r in members)
            continue
        head = next((r for r in members if r.get('sites')), None)
        store_rows = [r for r in members if r is not head]
        site_urls = {domain_of(https(x)) for x in (head.get('sites', '').split('\n') if head else []) if x.strip()}
        if head and not store_rows:   # the script has not added the store rows yet: build them from the Store websites list
            store_rows = [{'name': '', 'url': u.strip(), 'city': '', 'state': '', 'consultant': head.get('consultant'), 'email': head.get('email'), 'row': head.get('row'), 'timestamp': head.get('timestamp')} for u in head.get('sites', '').split('\n') if u.strip()]
        stores = [store_spec(r) for r in store_rows]
        store_domains = {domain_of(s['url']) for s in stores}
        group_site = https(head.get('url')) if head and domain_of(https(head.get('url'))) not in store_domains else None
        if not stores and head:
            stores = [store_spec(head)]
            group_site = None
        name = members[0].get('group')
        jobs.append({'kind': 'group', 'name': name, 'keys': keys, 'rows': [r.get('row') for r in members],
                     'spec': {'group': name, 'group_site': group_site, 'consultant': members[0].get('consultant') or None, 'email': members[0].get('email') or None, 'stores': stores}})
        used.update(id(r) for r in members)
    for r in waiting:
        if id(r) in used or not https(r.get('url')):
            continue
        k = row_key(r)
        if k in done:
            continue
        s = store_spec(r)
        s.update({'group': None, 'group_site': None, 'sister_sites': [], 'old_domain': None, 'competitor_candidates': []})
        jobs.append({'kind': 'store', 'name': s['store'] or domain_of(s['url']), 'keys': [k], 'rows': [r.get('row')], 'spec': s})
    # oldest request first, so a queue drains in the order the consultants asked
    jobs.sort(key=lambda j: min((parse_ts(k.split('|')[0]) or datetime.max.replace(tzinfo=ET)) for k in j['keys']))
    return jobs


# ---------------------------------------------------------------- running
def load_ledger():
    if LEDGER.exists():
        return json.loads(LEDGER.read_text())
    return {'done': {}, 'runs': []}


def save_ledger(ledger):
    STATE.mkdir(exist_ok=True)
    LEDGER.write_text(json.dumps(ledger, indent=1))


def run_job(job, ledger, jobs_flag='3'):
    AUTO.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(ET).strftime('%Y-%m-%d_%H%M')
    req = AUTO / f'{stamp}_{slug(job["name"])}.json'
    req.write_text(json.dumps(job['spec'], indent=1))
    out = OUT / f'{stamp}_{slug(job["name"])}'
    log(f'start {job["kind"]} {job["name"]} (sheet rows {job["rows"]}) -> {out}')
    t0 = time.time()
    cmd = [sys.executable, '-m', 'collector', 'collect', str(req), '--out', str(out), '--jobs', jobs_flag, '--handoff']
    res = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    tail = (res.stdout or '')[-600:]
    ok = res.returncode == 0 and 'sent ' in (res.stdout or '')
    record = {'kind': job['kind'], 'name': job['name'], 'rows': job['rows'], 'request': str(req.relative_to(ROOT)), 'out': str(out.relative_to(ROOT)),
              'started': now_et(), 'seconds': round(time.time() - t0), 'returncode': res.returncode, 'handoff': ok, 'tail': tail}
    ledger.setdefault('runs', []).append(record)
    for k in job['keys']:
        ledger.setdefault('done', {})[k] = {'at': now_et(), 'out': record['out'], 'ok': ok}
    save_ledger(ledger)
    log(f'{"done" if ok else "FAILED"} {job["name"]} in {record["seconds"]} s' + ('' if ok else f': {(res.stderr or res.stdout)[-300:]}'))
    return ok


def main(argv):
    dry = '--dry-run' in argv
    once = '--once' in argv
    csv_path = argv[argv.index('--csv') + 1] if '--csv' in argv else None
    STATE.mkdir(exist_ok=True)
    try:
        rows = read_csv(csv_path) if csv_path else read_sheet()
    except Exception as e:
        log(f'could not read the sheet: {type(e).__name__}: {str(e)[:200]}')
        return 2
    ledger = load_ledger()
    jobs = jobs_from_rows(rows, ledger)
    waiting = sum(1 for r in rows if unfinished(r))
    log(f'{len(rows)} rows, {waiting} unfinished, {len(jobs)} job(s) to run')
    for j in jobs:
        log(f'  {j["kind"]}: {j["name"]} (sheet rows {j["rows"]}): ' + ', '.join(s['url'] for s in (j['spec'].get('stores') or [j['spec']])) + (f" + group site {j['spec']['group_site']}" if j['spec'].get('group_site') else ''))
    if dry or not jobs:
        return 0
    with open(LOCK, 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            log('another trigger run holds the lock; leaving the queue to it')
            return 0
        for j in jobs:
            run_job(j, ledger)
            if once:
                break
    return 0
