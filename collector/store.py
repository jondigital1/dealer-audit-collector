"""The store request, the results.json skeleton and the small helpers every module shares: Eastern time strings the
skill's notes can quote as they are, the store folder layout, and incremental saves (results.json is written after
every check, never only at the end)."""
import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from . import config

ET = ZoneInfo('America/New_York')
DASH = re.compile('[' + chr(0x2013) + chr(0x2014) + ']')


def now_et():
    """"Sep 27, 2026, 12:41 AM ET", the form the skill's speaker notes use."""
    d = datetime.now(ET)
    return f'{d.strftime("%b")} {d.day}, {d.year}, {d.strftime("%I:%M %p").lstrip("0")} ET'


def time_et():
    d = datetime.now(ET)
    return f'{d.strftime("%I:%M %p").lstrip("0")} ET'


def domain_of(url):
    host = urlparse(url if '://' in url else 'https://' + url).netloc.lower()
    return host[4:] if host.startswith('www.') else host


def no_dash(s):
    """The standing rule: no em or en dashes in anything the collector writes."""
    return DASH.sub('-', s) if isinstance(s, str) else s


class Store:
    """One store's run: its request, its folder, its results, and the log."""

    def __init__(self, request, out_dir, folder=None):
        self.req = request
        self.domain = domain_of(request['url'])
        self.dir = Path(out_dir) / (folder or self.domain)
        self.captures = self.dir / 'captures'
        self.raw = self.captures / 'raw'
        for d in (self.dir, self.captures, self.raw):
            d.mkdir(parents=True, exist_ok=True)
        self.t0 = time.time()
        self.results = {
            'collector': {'version': config.VERSION, 'host': 'agents', 'started_at': now_et(), 'started_epoch': self.t0, 'finished_at': None,
                          'seconds': None, 'platform_headless': None, 'notes': []},
            'request': request,
            'preflight': None,
            'store': request.get('store'), 'city': request.get('city'), 'state': request.get('state'),
            'domain': self.domain, 'platform': None, 'captured_at': now_et(),
            'pages': {'home': request['url'], 'srp': None, 'vdp': None, 'vdp_vehicle': None, 'vehicle_swapped': False, 'srp_new_count': None, 'srp_new_count_text': None},
            'bing': None, 'address_hours': None, 'phones': [],
            'pagespeed': {'home_mobile': None, 'home_desktop': None},   # the home page only (Jonathan, Sep 30, 2026)
            'vdp_render': None,
            'gtm': None, 'popup': None, 'seo_meta': {}, 'links': None, 'menu': None, 'spyfu': None,
            'conversion': None, 'cx': [], 'content': [], 'about_us_first_para': None, 'slider': [],
            'empty_blocks': [], 'special_hours': None, 'blog': None, 'group_card': None,
            'noticed': [], 'flags': [], 'not_captured': [], 'checks': {}, 'captures': {},
        }

    # ---- bookkeeping ----
    def log(self, msg):
        line = f'{time_et()}  {no_dash(msg)}'
        print(f'[{self.domain}] {line}', flush=True)
        with open(self.dir / 'collector.log', 'a', encoding='utf-8') as f:
            f.write(line + '\n')

    def save(self):
        # seconds since the run started, from the epoch kept in results.json; frozen once the run has finished, so a
        # results file loaded and saved by a later process (a module rerun, the flags) keeps the run's own time
        if not self.results['collector'].get('finished_at'):
            t0 = self.results.get('collector', {}).get('started_epoch') or self.t0
            self.results['collector']['seconds'] = round(time.time() - t0)
        txt = json.dumps(self.results, indent=1, ensure_ascii=False)
        (self.dir / 'results.json').write_text(no_dash(txt), encoding='utf-8')

    def check(self, name, status, reason=None):
        self.results['checks'][name] = status
        if status != 'ok' and reason:
            self.not_captured(name, reason)
        self.save()

    def not_captured(self, what, why):
        self.results['not_captured'].append({'what': what, 'why': no_dash(str(why))})
        self.log(f'not captured: {what}: {why}')

    def noticed(self, what, capture=None):
        self.results['noticed'].append({'what': no_dash(what), 'capture': capture})

    def flag(self, check, section, value, threshold, line, evidence):
        self.results['flags'].append({'check': check, 'section': section, 'value': value, 'threshold': threshold,
                                      'line': no_dash(line), 'evidence': evidence})

    def record_capture(self, name, page_url, size):
        self.results['captures'][name] = {'page': page_url, 'w': size[0], 'h': size[1], 'at': time_et()}

    def elapsed(self):
        return time.time() - (self.results.get('collector', {}).get('started_epoch') or self.t0)

    def over_budget(self):
        """Past the hard stop: nothing more is opened."""
        return self.elapsed() > config.STORE_HARD_STOP_S

    def over_soft_budget(self):
        """Past the soft budget: the extras (more research and specials pages) are skipped and listed."""
        return self.elapsed() > config.STORE_BUDGET_S

    def finish(self, close=True):
        """The run's end. A later save by another process (flags, a module rerun) keeps the first finished_at."""
        if close and not self.results['collector'].get('finished_at'):
            self.results['collector']['finished_at'] = now_et()
            self.results['collector']['seconds'] = round(time.time() - (self.results['collector'].get('started_epoch') or self.t0))
            self.save()
            return
        seconds = self.results['collector'].get('seconds')
        self.save()
        if seconds is not None:
            self.results['collector']['seconds'] = seconds
            (self.dir / 'results.json').write_text(no_dash(json.dumps(self.results, indent=1, ensure_ascii=False)), encoding='utf-8')
