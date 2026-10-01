"""The hand-off (Decision 4): each finished store folder zipped as <domain>_<YYYY-MM-DD>.zip with a manifest, then
sent to the Desktop PC by Taildrop (into its Downloads) or copied into the folder Syncthing mirrors to
C:\\Users\\jon\\AuditCaptures. The Cowork session connects that folder and stages the zips it needs."""
import datetime as dt
import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

from . import config


def zip_store(store_dir, out_dir):
    """One zip per store folder; the group site's folder is named by its domain, group-site_<domain>_<date>.zip."""
    store_dir = Path(store_dir)
    label = store_dir.name
    if label == 'group' and (store_dir / 'results.json').exists():
        try:
            label = 'group-site_' + (json.loads((store_dir / 'results.json').read_text()).get('domain') or 'group')
        except Exception:
            pass
    name = f'{label}_{dt.date.today().isoformat()}.zip'
    out = Path(out_dir) / name
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in sorted(store_dir.rglob('*')):
            if p.is_file() and 'raw' not in p.relative_to(store_dir).parts:
                z.write(p, str(Path(store_dir.name) / p.relative_to(store_dir)))
    return out


def manifest(zips, out_dir):
    """One manifest per send, named with the send time (manifest_2026-09-30_0837ET.json): Windows Taildrop keeps a
    repeat as "name (1)" rather than overwriting, so a fixed name would leave the PC's manifest listing the first send."""
    from zoneinfo import ZoneInfo
    now = dt.datetime.now(ZoneInfo('America/New_York'))
    rows = []
    for z in zips:
        rows.append({'zip': z.name, 'store': z.name.rsplit('_', 1)[0], 'bytes': z.stat().st_size,
                     'md5': hashlib.md5(z.read_bytes()).hexdigest(), 'made': now.isoformat(timespec='seconds'), 'sent_at_et': now.strftime('%b %d, %Y, %I:%M %p ET').replace(' 0', ' ')})
    path = Path(out_dir) / f'manifest_{now.strftime("%Y-%m-%d_%H%M")}ET.json'
    path.write_text(json.dumps(rows, indent=1))
    return path


def taildrop_target():
    """The Desktop PC's node name on the tailnet. The configured name is used when it is online; when it is not listed
    but a node with that name plus a suffix is (jon-d1-pc-2 for jon-d1-pc, Sep 30, 2026), that one is used and said so."""
    want = config.TAILDROP_TARGET
    try:
        st = subprocess.run(['tailscale', 'status', '--json'], capture_output=True, text=True, timeout=15)
        peers = json.loads(st.stdout).get('Peer', {}).values() if st.returncode == 0 else []
        names = {(p.get('DNSName') or p.get('HostName') or '').split('.')[0].lower(): p for p in peers}   # the MagicDNS name is what file cp takes
    except Exception:
        return want, None
    if want in names:
        return want, None
    alt = sorted(n for n in names if n.startswith(want + '-') and names[n].get('OS', '').lower().startswith('win'))
    if alt:
        return alt[0], f'{want} is not on the tailnet; sending to {alt[0]} instead (set TAILDROP_TARGET in .env)'
    return want, f'{want} is not on the tailnet; tailscale file cp will fail'


def send(paths):
    """Taildrop each file to the Desktop PC, or copy it into the synced folder."""
    if config.HANDOFF_MODE == 'taildrop':
        target, note = taildrop_target()
        for p in paths:
            res = subprocess.run(['tailscale', 'file', 'cp', str(p), f'{target}:'], capture_output=True, text=True)
            if res.returncode != 0:
                err = (res.stderr or res.stdout).strip()
                hint = ' Run once on the VM: sudo tailscale set --operator=$USER' if 'operator' in err or 'access denied' in err.lower() else ''
                return f'Taildrop could not send {p.name} to {target}: {err[:200]}.{hint} The zips stay in {p.parent}.'
        return f'sent {len(paths)} file(s) to {target} by Taildrop (they land in its Downloads)' + (f'; note: {note}' if note else '')
    config.HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
    for p in paths:
        shutil.copy2(p, config.HANDOFF_DIR / p.name)
    return f'copied {len(paths)} file(s) into {config.HANDOFF_DIR} for Syncthing'


def run(out_dir):
    out_dir = Path(out_dir)
    stores = [d for d in out_dir.iterdir() if d.is_dir() and (d / 'results.json').exists()]
    if not stores:
        return 'no finished store folders in ' + str(out_dir)
    zips = [zip_store(d, out_dir) for d in stores]
    m = manifest(zips, out_dir)
    return send(zips + [m])
