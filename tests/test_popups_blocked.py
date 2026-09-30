"""A blocked or challenged home page load on the normal pass must skip the flag-off timing pass and mark the store
chrome_only. A local server plays the firewall: a 403 Access Denied page, then a 200 page with a challenge, then a
real page (a menu with images) to show the pass runs when it should.

  python3 -m unittest tests.test_popups_blocked
"""
import http.server
import json
import tempfile
import threading
import unittest
from pathlib import Path

from collector import captures, config, popups
from collector.store import Store

PAGES = {
    '/blocked': (403, '<html><head><title>Access Denied</title></head><body><h1>Access Denied</h1><p>You don\'t have permission to access this page. Reference #18.abc</p></body></html>'),
    '/challenge': (200, '<html><head><title>Attention Required</title></head><body><p>Checking your browser before accessing the site. Verify you are human.</p></body></html>'),
    '/real': (200, '<html><head><title>Test Motors</title></head><body><nav>' + ''.join(f'<a href="/p{i}">Item {i}</a>' for i in range(12)) + '</nav>'
              '<img src="data:image/gif;base64,R0lGODlhAQABAIAAAAUEBA==" width="300" height="200"><p>Welcome to Test Motors, your dealer.</p></body></html>'),
}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        status, body = PAGES.get(self.path, (404, '<html><body>not found</body></html>'))
        self.send_response(status)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *a):
        pass


class BlockedLoadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.tmp = tempfile.mkdtemp()
        config.POPUP_POLL_MS = 1500   # the poll can be short: nothing opens on these pages

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def run_timing(self, path):
        store = Store({'store': 'Test Motors', 'url': f'http://127.0.0.1:{self.port}{path}'}, self.tmp)
        store.results['preflight'] = {'platform_headless': 'ok', 'notes': []}
        with captures.Browser() as b:
            popups.timing(store, b)
        return store.results

    def test_403_skips_the_flag_off_pass(self):
        r = self.run_timing('/blocked')
        self.assertEqual(r['checks']['popup'], 'skipped')
        self.assertFalse(r['popup']['normal_pass']['real_page'])
        self.assertEqual(r['popup']['loads'], [])
        self.assertEqual(r['collector']['platform_headless'], 'chrome_only')
        self.assertEqual(r['preflight']['platform_headless'], 'chrome_only')
        self.assertTrue(any('pop-up timing' in x['what'] or x['what'] == 'popup' for x in r['not_captured']))

    def test_challenge_page_skips_the_flag_off_pass(self):
        r = self.run_timing('/challenge')
        self.assertEqual(r['checks']['popup'], 'skipped')
        self.assertIn('challenge', r['popup']['normal_pass']['real_page_note'])
        self.assertEqual(r['popup']['loads'], [])
        self.assertEqual(r['collector']['platform_headless'], 'chrome_only')

    def test_real_page_runs_the_flag_off_pass(self):
        r = self.run_timing('/real')
        self.assertEqual(r['checks']['popup'], 'ok')
        self.assertTrue(r['popup']['normal_pass']['real_page'])
        self.assertEqual(len(r['popup']['loads']), 2)
        self.assertTrue(all(l['webdriver'] is False for l in r['popup']['loads']))
        self.assertNotEqual(r['collector']['platform_headless'], 'chrome_only')


if __name__ == '__main__':
    unittest.main()
