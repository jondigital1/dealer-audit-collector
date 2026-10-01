"""The push listener: rows arrive as a table or as dicts, the secret gates every call, and a push queues the right jobs."""
import csv
import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from collector import listener, trigger

FIX = Path(__file__).parent / 'fixtures' / 'requests_tab.csv'


class ListenerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ['TRIGGER_SECRET'] = 'test-secret'
        cls.srv = ThreadingHTTPServer(('127.0.0.1', 0), listener.Handler)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.rows = list(csv.reader(open(FIX, encoding='utf-8-sig')))

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def call(self, path, body=None, secret='test-secret'):
        req = urllib.request.Request(f'http://127.0.0.1:{self.port}{path}', data=json.dumps(body).encode() if body is not None else None,
                                     headers={'Content-Type': 'application/json', **({'X-Trigger-Secret': secret} if secret else {})}, method='POST' if body is not None else 'GET')
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_health_needs_no_secret(self):
        self.assertEqual(self.call('/health', secret=None)[0], 200)

    def test_bad_secret_is_refused(self):
        self.assertEqual(self.call('/trigger', {'rows': self.rows}, secret='wrong')[0], 401)
        self.assertEqual(self.call('/status', secret=None)[0], 401)

    def test_bad_body_is_400(self):
        self.assertEqual(self.call('/trigger', {'nope': 1})[0], 400)

    def test_rows_as_dicts_match_rows_as_table(self):
        heads = self.rows[0]
        dicts = [dict(zip(heads, r)) for r in self.rows[1:]]
        self.assertEqual(listener.rows_from_body({'rows': dicts}), trigger.rows_from_table(self.rows))

    def test_push_queues_only_what_the_rules_allow(self):
        # the fixture's open rows are dated Oct 1, 2026: in the past once the clock passes them, so the push queues them.
        # run_job is stubbed so nothing collects here.
        real = trigger.run_job
        ran = []
        trigger.run_job = lambda job, ledger: ran.append(job['name'])
        try:
            code, body = self.call('/trigger', {'source': 'test', 'rows': self.rows})
            self.assertEqual(code, 202)
            names = [q['name'] for q in body['queued']]
            self.assertTrue(set(names) <= {'Lynn Layton Chevrolet', 'Tubbs Brothers'}, names)
            self.assertNotIn('Future Dated Motors', names)
            self.assertNotIn('Bay Hyundai', names)      # On hold stays out
            self.assertNotIn('Natchez Nissan', names)   # Complete stays out
        finally:
            trigger.run_job = real


if __name__ == '__main__':
    unittest.main()
