"""Explicit USB-only updates for the RAM-root lab. Never modify the installed OS."""

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

from .lab_config import is_usb_partition

USB_UUID = '0D51-AB01'
BASE_ARGS = ('rdinit=/init console=tty0 console=ttyS0,115200n8 panic=0 '
             'initcall_blacklist=nvme_init,ahci_pci_driver_init,piix_init '
             'module_blacklist=nvme,nvme_core,mmc_block,ahci,libata')
SLOTS = ('baseline', 'research-a', 'research-b')
MAX_PAYLOAD = 1024 * 1024 * 1024
ENV_HEADER = b'# GRUB Environment Block\n'


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def validate_args(args):
    protected = {'init', 'rdinit', 'root', 'resume', 'initcall_blacklist',
                 'module_blacklist', 'ods.slot', 'ods.bundle'}
    if not isinstance(args, list) or len(args) > 64:
        raise ValueError('Expected a list of at most 64 extra kernel arguments')
    for arg in args:
        if not isinstance(arg, str) or not re.fullmatch(r'[A-Za-z0-9_./:=,+@%\-]{1,256}', arg):
            raise ValueError('Invalid kernel argument; shell/GRUB expressions are not allowed')
        if arg.split('=', 1)[0] in protected:
            raise ValueError('Cannot override the lab boot/storage isolation arguments')
    return args


def validate_manifest(data):
    m = json.loads(data)
    if not isinstance(m, dict) or m.get('format') != 'opendecksight-lab-update-v1':
        raise ValueError('Unsupported update format')
    if not re.fullmatch(r'[A-Za-z0-9._+\-]{1,128}', m.get('kernel_release', '')):
        raise ValueError('Invalid kernel release')
    validate_args(m.get('boot_args', []))
    files = m.get('files', {})
    if not isinstance(files, dict) or set(files) != {'vmlinuz', 'initramfs.img'}:
        raise ValueError('Update must contain exactly a kernel and its matching initramfs')
    for info in files.values():
        if not isinstance(info, dict) or type(info.get('size')) is not int or not 0 < info['size'] <= MAX_PAYLOAD:
            raise ValueError('Invalid payload size')
        if not re.fullmatch(r'[a-f0-9]{64}', info.get('sha256', '')):
            raise ValueError('Invalid payload hash')
    if sum(info['size'] for info in files.values()) > MAX_PAYLOAD:
        raise ValueError('Update exceeds the 1 GiB payload limit')
    return m


def env_bytes(slot):
    if slot not in SLOTS:
        raise ValueError('Unknown boot slot')
    data = ENV_HEADER + ('ods_default=' + slot + '\n').encode('ascii')
    return data + b'#' * (1024 - len(data))


def default_slot(volume):
    path = volume / 'boot/ods.env'
    if path.exists():
        data = path.read_bytes()
        if data.startswith(ENV_HEADER) and len(data) == 1024:
            for line in data.decode('ascii').splitlines():
                if line.startswith('ods_default=') and line[12:] in SLOTS:
                    return line[12:]
    return 'baseline'


def atomic_write(path, data):
    temp = path.with_name(path.name + '.new')
    with temp.open('wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)
    # Flush FAT metadata before reporting completion or allowing a reboot.
    os.sync()


def slot_path(volume, slot):
    if slot not in SLOTS[1:]:
        raise ValueError('The recovery baseline cannot be overwritten')
    return volume / 'boot/slots' / slot


def select(volume, slot):
    if slot not in SLOTS:
        raise ValueError('Unknown boot slot')
    if slot != 'baseline':
        path = slot_path(volume, slot)
        manifest = validate_manifest((path / 'manifest.json').read_bytes())
        for name, info in manifest['files'].items():
            if (path / name).stat().st_size != info['size'] or sha(path / name) != info['sha256']:
                raise ValueError('Selected slot failed payload verification')
        if not (path / 'entry.cfg').is_file():
            raise ValueError('Selected slot has no boot entry')
    atomic_write(volume / 'boot/ods.env', env_bytes(slot))


def install(volume, stream, boot_args=None, running='baseline'):
    """Validate a streamed bundle before changing the default boot selection."""
    selected = default_slot(volume)
    if running in SLOTS[1:] and selected != running:
        raise ValueError('A different boot is pending; reboot or select the running slot first')
    slot = 'research-b' if selected == 'research-a' else 'research-a'
    parent = volume / 'boot/slots'
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.incoming-', dir=parent))
    try:
        with tarfile.open(fileobj=stream, mode='r|') as archive:
            first = archive.next()
            if first is None or first.name != 'manifest.json' or not first.isfile() or first.size > 65536:
                raise ValueError('Bundle must begin with a small regular manifest.json')
            raw = archive.extractfile(first).read()
            manifest = validate_manifest(raw)
            if boot_args is not None:
                manifest['boot_args'] = validate_args(boot_args)
            needed = sum(x['size'] for x in manifest['files'].values()) + 8 * 1024 * 1024
            if shutil.disk_usage(volume).free < needed:
                raise ValueError('Insufficient USB space; existing boot slots were preserved')
            seen = set()
            for member in archive:
                if member is first:
                    continue
                if member.name not in manifest['files'] or member.name in seen or not member.isfile():
                    raise ValueError('Unexpected, duplicate or non-regular bundle member')
                info = manifest['files'][member.name]
                if member.size != info['size']:
                    raise ValueError('Payload size differs from manifest')
                target = staging / member.name
                with archive.extractfile(member) as source, target.open('wb') as dest:
                    shutil.copyfileobj(source, dest, 1024 * 1024)
                    dest.flush()
                    os.fsync(dest.fileno())
                if sha(target) != info['sha256']:
                    raise ValueError('Payload hash differs from manifest')
                seen.add(member.name)
            if seen != set(manifest['files']):
                raise ValueError('Incomplete bundle')
        raw = (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode()
        bundle_id = hashlib.sha256(raw).hexdigest()
        (staging / 'manifest.json').write_bytes(raw)
        extra = ' '.join(manifest.get('boot_args', []))
        entry = (f"menuentry 'OpenDeckSight {slot}' --id '{slot}' {{\n"
                 f"  linux /boot/slots/{slot}/vmlinuz {BASE_ARGS} ods.slot={slot} ods.bundle={bundle_id} {extra}\n"
                 f"  initrd /boot/slots/{slot}/initramfs.img\n}}\n")
        (staging / 'entry.cfg').write_text(entry)
        os.sync()
        target = slot_path(volume, slot)
        if target.exists():
            shutil.rmtree(target)  # Only the inactive research slot; never baseline/current.
        staging.rename(target)
        os.sync()
        atomic_write(volume / 'boot/ods.env', env_bytes(slot))
        return {'next_boot': slot, 'bundle_id': bundle_id, 'kernel_release': manifest['kernel_release'],
                'reboot_required': True}
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def running_slot():
    args = Path('/proc/cmdline').read_text().split()
    return next((x.split('=', 1)[1] for x in args if x.startswith('ods.slot=')), 'baseline')


@contextmanager
def mounted_usb(write=False):
    if sys.platform != 'linux' or os.geteuid() != 0:
        raise ValueError('Run ods-update as root inside the Linux USB lab')
    with open('/run/ods-update.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = subprocess.run(['blkid', '-t', 'UUID=' + USB_UUID, '-o', 'device'],
                                capture_output=True, text=True, check=False)
        devices = [p for p in result.stdout.splitlines() if is_usb_partition(p)]
        if len(devices) != 1:
            raise ValueError('Expected exactly one lab USB configuration volume')
        device = devices[0]
        if any(line.split()[0] == device for line in Path('/proc/mounts').read_text().splitlines()):
            raise ValueError('Lab USB is already mounted; unmount it before updating')
        volume = Path('/run/ods-update-usb')
        volume.mkdir(exist_ok=True)
        options = ('rw' if write else 'ro') + ',nosuid,nodev,noexec'
        subprocess.run(['mount', '-t', 'vfat', '-o', options, device, str(volume)], check=True)
        try:
            if not (volume / 'ODS-UPDATE-V1').is_file():
                raise ValueError('This USB was not created with update support')
            yield volume
        finally:
            if write:
                os.sync()
            subprocess.run(['umount', str(volume)], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    commands.add_parser('status')
    upload = commands.add_parser('install', help='stage and select a kernel/initramfs bundle; does not reboot')
    upload.add_argument('bundle', help='tar file or - to stream from stdin')
    upload.add_argument('--boot-arg', action='append', default=None)
    choose = commands.add_parser('select', help='select an existing verified slot; does not reboot')
    choose.add_argument('slot', choices=SLOTS)
    args = parser.parse_args()
    try:
        with mounted_usb(write=args.action != 'status') as volume:
            if args.action == 'install':
                if args.bundle == '-':
                    result = install(volume, sys.stdin.buffer, args.boot_arg, running_slot())
                else:
                    with open(args.bundle, 'rb') as stream:
                        result = install(volume, stream, args.boot_arg, running_slot())
            elif args.action == 'select':
                select(volume, args.slot)
                result = {'next_boot': args.slot, 'reboot_required': True}
            else:
                result = {'running': running_slot(), 'next_boot': default_slot(volume),
                          'available': ['baseline'] + [s for s in SLOTS[1:]
                                                      if (slot_path(volume, s) / 'entry.cfg').exists()]}
        print(json.dumps(result))
    except (OSError, ValueError, TypeError, KeyError, tarfile.TarError, subprocess.SubprocessError) as error:
        parser.exit(1, 'ods-update: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
