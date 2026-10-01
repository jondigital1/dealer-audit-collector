"""The sheet trigger picks the right rows: unfinished only, groups as one job, a row once, future dates left alone."""
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from collector import trigger

FIX = Path(__file__).parent / 'fixtures' / 'requests_tab.csv'
NOW = datetime(2026, 10, 1, 10, 0, tzinfo=ZoneInfo('America/New_York'))


class TriggerTest(unittest.TestCase):
    def setUp(self):
        self.rows = trigger.read_csv(FIX)

    def test_reads_every_request_row(self):
        self.assertEqual(len(self.rows), 8)
        self.assertEqual(self.rows[0]['name'], 'Natchez Nissan')
        self.assertEqual(self.rows[3]['sites'].split('\n'), ['https://www.tubbsbrothers.net', 'https://www.tubbsbrothersford.com'])

    def test_only_unfinished_rows_become_jobs(self):
        jobs = trigger.jobs_from_rows(self.rows, {'done': {}}, now=NOW)
        names = [j['name'] for j in jobs]
        self.assertEqual(names, ['Lynn Layton Chevrolet', 'Tubbs Brothers'])   # Complete, In progress, On hold and the future row stay out

    def test_group_is_one_job_with_its_site_and_stores(self):
        jobs = trigger.jobs_from_rows(self.rows, {'done': {}}, now=NOW)
        g = next(j for j in jobs if j['kind'] == 'group')
        self.assertEqual(g['spec']['group_site'], 'https://www.tubbsbrothers.com')
        self.assertEqual([s['url'] for s in g['spec']['stores']], ['https://www.tubbsbrothers.net', 'https://www.tubbsbrothersford.com'])
        self.assertIsNone(g['spec']['stores'][0]['store'])   # a bare domain is not a name; the pre-flight reads it from the site
        self.assertEqual(sorted(g['rows']), [5, 6, 7])

    def test_single_store_spec(self):
        jobs = trigger.jobs_from_rows(self.rows, {'done': {}}, now=NOW)
        s = next(j for j in jobs if j['kind'] == 'store')
        self.assertEqual(s['spec']['store'], 'Lynn Layton Chevrolet')
        self.assertEqual((s['spec']['city'], s['spec']['state'], s['spec']['url']), ('Decatur', 'AL', 'https://www.lynnlaytonchevrolet.com'))
        self.assertEqual(s['spec']['consultant'], 'Blake Norberg')

    def test_ledger_keeps_a_row_from_running_twice(self):
        jobs = trigger.jobs_from_rows(self.rows, {'done': {}}, now=NOW)
        ledger = {'done': {k: {'ok': True} for j in jobs for k in j['keys']}}
        self.assertEqual(trigger.jobs_from_rows(self.rows, ledger, now=NOW), [])
        # a re-run on the sheet moves the Timestamp, so the row runs again
        rows = [dict(r) for r in self.rows]
        rows[2]['timestamp'] = '10/01/2026 09:30:00'
        again = trigger.jobs_from_rows(rows, ledger, now=NOW)
        self.assertEqual([j['name'] for j in again], ['Lynn Layton Chevrolet'])

    def test_group_without_store_rows_yet_uses_the_sites_list(self):
        rows = [r for r in self.rows if r['name'] not in ('tubbsbrothers.net', 'tubbsbrothersford.com')]
        jobs = trigger.jobs_from_rows(rows, {'done': {}}, now=NOW)
        g = next(j for j in jobs if j['kind'] == 'group')
        self.assertEqual([s['url'] for s in g['spec']['stores']], ['https://www.tubbsbrothers.net', 'https://www.tubbsbrothersford.com'])
        self.assertEqual(g['spec']['group_site'], 'https://www.tubbsbrothers.com')


if __name__ == '__main__':
    unittest.main()
