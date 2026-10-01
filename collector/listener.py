"""The push listener: the sheet's Apps Script tells the collector a request landed, and the collector goes to work.

A small HTTP server on the VM, reached from Google's servers through Tailscale Funnel (SETUP.md, "The push trigger").
The Apps Script (apps-script/Trigger.gs) POSTs the request rows as JSON, in the Audit Requests tab's own columns,
with the shared secret in the X-Trigger-Secret header; the listener answers at once and runs the jobs in the
background, one at a time, through the same rules as the polling trigger (collector/trigger.py: unfinished rows only,
groups by Auto Group Name, the ledger so a row runs once, the lock so runs never overlap). Nothing here reads or writes
the sheet, so no Google credential is needed on the VM.

Endpoints (all answers are JSON):
  POST /trigger   body {"rows": [[header...], [row...], ...]} or {"rows": [{column: value, ...}, ...]}
                  -> 202 {"queued": [...], "skipped": n}; 401 on a bad secret; 400 on a bad body
  GET  /status    -> the ledger's last runs and whether a job is running (secret required)
  GET  /health    -> 200 ok (no secret; what Funnel and the watchdog poke)

Usage: python3 -m collector listen [--port 8787]   (the cron @reboot line and the watchdog keep it running)
"""
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import trigger
from .store import now_et

RUNNING = {'job': None, 'since': None}
QUEUE_LOCK = threading.Lock()


def secret():
    return os.environ.get('TRIGGER_SECRET') or ''


def rows_from_body(body):
    """Rows as the script sends them: a table (header first) or a list of dicts keyed by the tab's headers."""
    rows = body.get('rows')
    if not isinstance(rows, list) or not rows:
        raise ValueError('rows missing')
    if isinstance(rows[0], list):
        return trigger.rows_from_table(rows)
    heads = []
    for r in rows:
        for k in r:
            if k not in heads:
                heads.append(k)
    return trigger.rows_from_table([heads] + [[r.get(h, '') for h in heads] for r in rows])


def run_queue(jobs):
    """Run the queued jobs one after another; a second request while one runs waits for the lock."""
    with QUEUE_LOCK:
        ledger = trigger.load_ledger()
        for j in jobs:
            # a job queued twice (the form submit and the sweep) runs once: the ledger settles it
            if all(k in ledger.get('done', {}) for k in j['keys']):
                continue
            RUNNING['job'], RUNNING['since'] = j['name'], now_et()
            try:
                trigger.run_job(j, ledger)
            except Exception as e:
                trigger.log(f'{j["name"]} failed: {type(e).__name__}: {str(e)[:200]}')
            RUNNING['job'], RUNNING['since'] = None, None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):   # one line per request in the listener's log, with the time
        trigger.log(f'{self.address_string()} {fmt % args}')

    def send(self, code, payload):
        data = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def authorized(self):
        return secret() and self.headers.get('X-Trigger-Secret', '') == secret()

    def do_GET(self):
        if self.path.startswith('/health'):
            return self.send(200, {'ok': True, 'at': now_et()})
        if not self.authorized():
            return self.send(401, {'error': 'bad secret'})
        if self.path.startswith('/status'):
            ledger = trigger.load_ledger()
            return self.send(200, {'running': RUNNING, 'done': len(ledger.get('done', {})), 'last_runs': ledger.get('runs', [])[-5:]})
        self.send(404, {'error': 'no such path'})

    def do_POST(self):
        if not self.path.startswith('/trigger'):
            return self.send(404, {'error': 'no such path'})
        if not self.authorized():
            return self.send(401, {'error': 'bad secret'})
        try:
            n = int(self.headers.get('Content-Length') or 0)
            body = json.loads(self.rfile.read(n) or b'{}')
            rows = rows_from_body(body)
        except (ValueError, json.JSONDecodeError) as e:
            return self.send(400, {'error': f'bad body: {e}'})
        ledger = trigger.load_ledger()
        jobs = trigger.jobs_from_rows(rows, ledger)
        queued = [{'kind': j['kind'], 'name': j['name'], 'rows': j['rows'], 'stores': [s['url'] for s in (j['spec'].get('stores') or [j['spec']])]} for j in jobs]
        trigger.log(f'push from {body.get("source", "the sheet")}: {len(rows)} row(s), {len(jobs)} job(s) queued: {", ".join(q["name"] for q in queued) or "none"}')
        if jobs:
            threading.Thread(target=run_queue, args=(jobs,), daemon=True).start()
        self.send(202, {'queued': queued, 'skipped': len(rows) - sum(len(j['rows']) for j in jobs), 'running': RUNNING['job']})


def main(argv):
    port = int(argv[argv.index('--port') + 1]) if '--port' in argv else int(os.environ.get('LISTENER_PORT') or 8787)
    if not secret():
        trigger.log('TRIGGER_SECRET is not set in .env; refusing to listen')
        return 2
    trigger.STATE.mkdir(exist_ok=True)
    srv = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    trigger.log(f'listening on 127.0.0.1:{port} (Funnel fronts it)')
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0
