"""Record build inputs and payload hashes without local paths or credentials."""
from pathlib import Path
import hashlib
import json
import subprocess

root = Path('/src')
esp = Path('/work/esp')
def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
sources = (list((root / 'lab/usb').glob('*')) + list((root / 'opendecksight').glob('*.py'))
           + list((root / 'tools').glob('*lab*.py')))
manifest = {
    'schema': 1,
    'purpose': 'RAM-only fixed-refresh diagnostic baseline; no VRR patch',
    'kernel': json.loads((root / 'lab/usb/kernel.lock.json').read_text()),
    'runtime_lock_sha256': sha(esp / 'runtime.lock.json'),
    'source_sha256': {str(p.relative_to(root)): sha(p) for p in sources if p.is_file()},
    'payload_sha256': {str(p.relative_to(esp)): sha(p) for p in sorted(esp.rglob('*'))
                       if p.is_file() and p.name != 'wifi.json'},
    'builder_packages': subprocess.run(['rpm', '-qa', '--qf', '%{NEVRA}\n'],
                                        check=True, capture_output=True, text=True).stdout.splitlines(),
    'storage': 'NVMe/AHCI/PIIX registration initcalls blacklisted; NVMe/MMC/ATA modules omitted; no installed root, swap or automount service',
    'ssh': 'root with empty password; ephemeral host key generated at boot',
}
(esp / 'build-manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
