import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from opendecksight.lab_update import default_slot, env_bytes, install, select, validate_args


def bundle(marker=b'new initramfs', damage=False, extra=None):
    payload = {'vmlinuz': b'test kernel', 'initramfs.img': marker}
    manifest = {'format': 'opendecksight-lab-update-v1', 'kernel_release': 'test.x86_64',
                'boot_args': ['ods.test=1'],
                'files': {name: {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                          for name, data in payload.items()}}
    if damage:
        payload['initramfs.img'] = b'x' * len(marker)
    entries = {'manifest.json': json.dumps(manifest).encode(), **payload}
    if extra:
        entries[extra] = b'bad'
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as archive:
        for name, data in entries.items():
            header = tarfile.TarInfo(name)
            header.size = len(data)
            archive.addfile(header, io.BytesIO(data))
    stream.seek(0)
    return stream


class LabUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.volume = Path(self.temp.name)
        (self.volume / 'boot').mkdir()
        (self.volume / 'boot/vmlinuz').write_bytes(b'recovery kernel')
        (self.volume / 'boot/initramfs.img').write_bytes(b'recovery root')
        (self.volume / 'boot/ods.env').write_bytes(env_bytes('baseline'))
        self.sync = patch('opendecksight.lab_update.os.sync')
        self.sync.start()
        self.addCleanup(self.sync.stop)

    def test_updates_rotate_and_preserve_baseline_and_running_slot(self):
        a = install(self.volume, bundle(b'A'))
        self.assertEqual(a['next_boot'], 'research-a')
        b = install(self.volume, bundle(b'B'), running='research-a')
        self.assertEqual(b['next_boot'], 'research-b')
        install(self.volume, bundle(b'C'), running='research-b')
        slots = self.volume / 'boot/slots'
        self.assertEqual((slots / 'research-a/initramfs.img').read_bytes(), b'C')
        self.assertEqual((slots / 'research-b/initramfs.img').read_bytes(), b'B')
        self.assertEqual((self.volume / 'boot/initramfs.img').read_bytes(), b'recovery root')
        self.assertEqual((self.volume / 'boot/vmlinuz').read_bytes(), b'recovery kernel')

    def test_bad_or_incomplete_upload_never_selects_new_boot(self):
        install(self.volume, bundle())
        for stream in [bundle(damage=True), bundle(extra='../escape'),
                       io.BytesIO(bundle().getvalue()[:2500])]:
            with self.subTest(), self.assertRaises((ValueError, tarfile.TarError)):
                install(self.volume, stream, running='research-a')
            self.assertEqual(default_slot(self.volume), 'research-a')
            self.assertFalse((self.volume / 'boot/slots/research-b').exists())
            self.assertFalse(list((self.volume / 'boot/slots').glob('.incoming-*')))

    def test_pending_boot_must_not_overwrite_running_slot(self):
        install(self.volume, bundle())
        install(self.volume, bundle(b'B'), running='research-a')
        with self.assertRaises(ValueError):
            install(self.volume, bundle(b'C'), running='research-a')

    def test_select_verifies_payload_and_can_recover_to_baseline(self):
        install(self.volume, bundle())
        path = self.volume / 'boot/slots/research-a/vmlinuz'
        path.write_bytes(b'broken')
        with self.assertRaises(ValueError):
            select(self.volume, 'research-a')
        select(self.volume, 'baseline')
        self.assertEqual(default_slot(self.volume), 'baseline')

    def test_kernel_arguments_cannot_inject_grub_or_remove_storage_guards(self):
        validate_args(['amdgpu.dcdebugmask=0x10', 'drm.debug=0x1ff'])
        for arg in ['root=/dev/nvme0n1', 'initcall_blacklist=', 'ods.slot=baseline',
                    'a; reboot', '$(reboot)', "x'", 'x\ny']:
            with self.subTest(arg=arg), self.assertRaises(ValueError):
                validate_args([arg])

    def test_grub_environment_is_fixed_size_and_recovers_from_invalid_data(self):
        self.assertEqual(len(env_bytes('research-a')), 1024)
        (self.volume / 'boot/ods.env').write_bytes(b'incomplete')
        self.assertEqual(default_slot(self.volume), 'baseline')
