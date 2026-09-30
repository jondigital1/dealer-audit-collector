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
    store_dir = Path(store_dir)
    name = f'{store_dir.name}_{dt.date.today().isoformat()}.zip'
    out = Path(out_dir) / name
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in sorted(store_dir.rglob('*')):
            if p.is_file() and 'raw' not in p.relative_to(store_dir).parts:
                z.write(p, str(Path(store_dir.name) / p.relative_to(store_dir)))
    return out


def manifest(zips, out_dir):
    rows = []
    for z in zips:
        rows.append({'zip': z.name, 'store': z.name.rsplit('_', 1)[0], 'bytes': z.stat().st_size,
                     'md5': hashlib.md5(z.read_bytes()).hexdigest(), 'made': dt.datetime.now().isoformat(timespec='seconds')})
    path = Path(out_dir) / 'manifest.json'
    old = json.loads(path.read_text()) if path.exists() else []
    path.write_text(json.dumps(old + rows, indent=1))
    return path


def send(paths):
    """Taildrop each file to the Desktop PC, or copy it into the synced folder."""
    if config.HANDOFF_MODE == 'taildrop':
        for p in paths:
            subprocess.run(['tailscale', 'file', 'cp', str(p), f'{config.TAILDROP_TARGET}:'], check=True)
        return f'sent {len(paths)} file(s) to {config.TAILDROP_TARGET} by Taildrop (they land in its Downloads)'
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
