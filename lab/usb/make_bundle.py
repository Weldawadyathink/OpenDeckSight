"""Export a streamed update bundle and the immutable recovery boot menu."""
import io
import json
from pathlib import Path
import sys
import tarfile

sys.path.insert(0, '/src')
from opendecksight.lab_update import BASE_ARGS, env_bytes, sha, validate_manifest

esp = Path('/work/esp')
kernel = json.loads((esp / 'kernel.lock.json').read_text())
args = json.loads(Path('/out/inputs/boot-args.json').read_text())
manifest = {'format': 'opendecksight-lab-update-v1', 'kernel_release': kernel['release'],
            'boot_args': args, 'kernel_provenance': kernel,
            'build_manifest_sha256': sha(esp / 'build-manifest.json'),
            'files': {name: {'size': (esp / 'boot' / name).stat().st_size,
                             'sha256': sha(esp / 'boot' / name)}
                      for name in ['vmlinuz', 'initramfs.img']}}
raw = (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode()
validate_manifest(raw)
with tarfile.open('/out/opendecksight-lab-update.tar', 'w') as archive:
    entry = tarfile.TarInfo('manifest.json')
    entry.size = len(raw)
    entry.mode = 0o644
    archive.addfile(entry, io.BytesIO(raw))
    for name in manifest['files']:
        archive.add(esp / 'boot' / name, arcname=name)
Path('/out/update-manifest.json').write_bytes(raw)
