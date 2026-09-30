"""Settings for the collector: keys from .env, the viewport the Desktop PC's Chrome uses, timeouts, and the folders.
Nothing here decides anything about a deck; SPEC.md is the contract."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / '.env')
except ImportError:  # dotenv is in requirements.txt; the collector still runs on plain environment variables
    pass

VERSION = '0.1.0'
PSI_API_KEY = os.environ.get('PSI_API_KEY', '')   # free; empty means the report page supplies the numbers
# No SpyFu key and no Places API: SpyFu and Google Business Profile are Chrome steps (Jonathan, Sep 29).
HANDOFF_MODE = os.environ.get('HANDOFF_MODE', 'taildrop')        # taildrop | folder
HANDOFF_DIR = Path(os.environ.get('HANDOFF_DIR', str(Path.home() / 'audit-handoff')))
TAILDROP_TARGET = os.environ.get('TAILDROP_TARGET', 'jon-d1-pc')
JOBS = int(os.environ.get('JOBS', '3'))

# The Desktop PC's Chrome window on Sep 29, 2026: every capture meant for a deck is made at this size, scale 1.
VIEWPORT = {'width': 1707, 'height': 1019}
USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
              'Chrome/{major}.0.0.0 Safari/537.36')


def user_agent_for(browser_version):
    """The desktop Chrome user agent at the headless browser's own major version, so the user agent and the browser's
    client hints (Sec-CH-UA) name the same Chrome."""
    major = (browser_version or '').split('.')[0] or '141'
    return USER_AGENT.format(major=major)
LOCALE = 'en-US'
TIMEZONE = 'America/New_York'

# Timeouts (ms), from SPEC.md section 8
NAV_TIMEOUT = 30_000
PSI_TIMEOUT = 90_000
POPUP_POLL_MS = 20_000
STORE_BUDGET_S = 600

# The skill's zoom levels (references/04_capture.md): 1.4 on a dealer page rendered small, 1.15 on PageSpeed
DEALER_ZOOM = 1.4
PSI_ZOOM = 1.15

# Elements hidden before every capture (references/04_capture.md)
HIDE_BEFORE_CAPTURE = ['#chrome-extension-pull-out-tab-host', '#podium-bubble', 'iframe[id^="podium"]', 'iframe[src*="podium"]']

# Platform markers the pre-flight looks for in the page (host names, script paths, generator tags), checked in this
# order. They are the dealer census's verified patterns (site-scans-data/markers.json, 17,678 sites, Sep 28, 2026),
# with Sincro's from the cobalt and sincrod hosts the census saw; bare words like "cdk", "di-" and "apollo" matched
# too much. A platform in platforms.json marked chrome_only goes straight to Chrome.
PLATFORM_MARKERS = {
    'Dealer.com': ['pictures.dealer.com', 'static.dealer.com', 'images.dealer.com', 'content="ddc"', 'website by dealer.com'],
    'DealerOn': ['cdn.dlron.us', '.dealeron.com/dealeron-', '.dealeron.com/personalization.js', 'dealeron.com/do-info', '/assets/logos/dealeron/'],
    'Dealer Inspire': ['assets.dealerinspire.com', '.dealerinspire.com', 'carscommerce.inc', '/wp-content/plugins/dealer-inspire'],
    'Sincro': ['cobaltnitra.com', 'cobaltgroup.com', 'wsassets.cobalt.com', 'sincrod.com', 'sincro.com', 'assets-cdk.com'],
    'Team Velocity': ['secureoffersites.com/images/getlibraryimage', 'tvmimageservice.com', 'tvmwebsitecdn.com', 'teamvelocity'],
    'Dealer eProcess': ['cdn.dealereprocess.org', 'dealereprocess.com', 'dealereprocess.org'],
    'DealerFire': ['dealerfire.com'],
    'Fox Dealer': ['foxdealer.com'],
    'Overfuel': ['overfuel.com'],
    'Dealer Alchemist': ['dealeralchemist.com'],
    'Motive': ['ridemotive.com', 'motivehq.com'],
    'Jazel': ['jazelc.com', 'jazel.com', 'jazel.net'],
    'Remora': ['remorainc.com', 'remora.inc'],
    'PixelMotion': ['pixelmotion.com', 'pixelmotiondemo.com'],
}

# The pop-up vendors the skill names, with the selector or signal that marks each one opening
POPUP_VENDORS = [
    {'vendor': 'Gubagoo', 'selector': '.gg-chat-wrapper', 'resource': 'cdn.gubagoo.io/gb1/'},
    {'vendor': 'DealerOn coupon', 'selector': '#dealerOnCoupon'},
    {'vendor': 'Wunderkind', 'selector': '[id^="bx-campaign-"]', 'window': 'bouncex'},
    {'vendor': 'Podium', 'selector': 'iframe#podium-prompt, iframe[id^="podium-prompt"]'},
    {'vendor': 'dealerbluesky', 'selector': '#dbs-dynamic-popup-overlay'},
    {'vendor': 'Tecobi', 'selector': '[class*="tecobi"], [id*="tecobi"]'},
    {'vendor': 'ComplyAuto', 'selector': '[class*="complyauto"], [id*="complyauto"], iframe[src*="complyauto"]'},
]
