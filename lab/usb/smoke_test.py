"""Boot the real USB layout in an isolated QEMU VM and test unauthenticated SSH."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

out = Path('/out')
work = Path('/work')
work.mkdir(exist_ok=True)
configured = os.environ.get('ODS_TEST_WIFI') == '1'
case = 'wifi' if configured else 'baseline'
prefix = 'uefi-smoke-' + case


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


disk = out / 'opendecksight-lab.img'
if configured:
    # Use synthetic credentials on a disposable copy, never modify the output image.
    shutil.copyfile(disk, work / 'wifi-test.img')
    disk = work / 'wifi-test.img'
    config = work / 'wifi.json'
    config.write_text(json.dumps({'wifi': {'ssid': 'ODS synthetic "network"',
                                          'password': 'example-not-a-real-secret'}}))
    subprocess.run(['mcopy', '-o', '-i', str(disk) + '@@1048576', str(config), '::/wifi.json'], check=True)
firmware = Path('/usr/share/edk2/ovmf')
code = firmware / 'OVMF_CODE.fd'
variables = firmware / 'OVMF_VARS.fd'
if not code.exists() or not variables.exists():
    raise SystemExit('Expected Fedora OVMF firmware files are missing')
shutil.copyfile(variables, work / 'vars.fd')
canary = work / 'internal-nvme.img'
with canary.open('wb') as stream:
    stream.write(b'OpenDeckSight internal-storage canary\n')
    stream.truncate(32 * 1024 * 1024)
before = hashlib.sha256(canary.read_bytes()).hexdigest()
args = ['qemu-system-x86_64', '-machine', 'q35', '-accel', 'tcg', '-cpu', 'max',
        '-smp', '2', '-m', '3072', '-display', 'none', '-monitor', 'none', '-no-reboot',
        '-serial', 'file:/out/' + prefix + '-serial.log',
        '-drive', 'if=pflash,format=raw,readonly=on,file=' + str(code),
        '-drive', 'if=pflash,format=raw,file=/work/vars.fd',
        '-device', 'qemu-xhci',
        '-drive', 'if=none,id=labusb,format=raw,readonly=on,file=' + str(disk),
        '-device', 'usb-storage,drive=labusb,bootindex=1',
        '-drive', 'if=none,id=internal,format=raw,file=' + str(canary),
        '-device', 'nvme,drive=internal,serial=ODS-CANARY',
        '-device', 'virtio-rng-pci',
        '-nic', 'user,model=e1000,hostfwd=tcp:127.0.0.1:2222-:22']
ssh = ['ssh', '-p', '2222', '-o', 'BatchMode=yes', '-o', 'PreferredAuthentications=none',
       '-o', 'StrictHostKeyChecking=accept-new', '-o', 'UserKnownHostsFile=/work/known_hosts',
       '-o', 'ConnectTimeout=2', 'root@127.0.0.1']
log = (out / (prefix + '-qemu.log')).open('w')
vm = subprocess.Popen(args, stdout=log, stderr=log)
try:
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        if vm.poll() is not None:
            raise RuntimeError('QEMU exited before SSH was available; inspect smoke logs')
        try:
            result = subprocess.run(ssh + ['true'], capture_output=True, text=True, timeout=6)
        except subprocess.TimeoutExpired:
            continue
        if result.returncode == 0:
            break
        time.sleep(3)
    else:
        raise RuntimeError('USB boot did not reach SSH within 600 seconds; inspect smoke logs')
    program = 'configured = ' + repr(configured) + '\n' + r'''
import glob,json,os,pathlib,subprocess
mounts=pathlib.Path('/proc/mounts').read_text()
assert os.getuid() == 0
assert not glob.glob('/dev/nvme*')
nvme = [p for p in pathlib.Path('/sys/bus/pci/devices').iterdir()
        if (p / 'class').read_text().strip() == '0x010802']
ahci = [p for p in pathlib.Path('/sys/bus/pci/devices').iterdir()
        if (p / 'class').read_text().strip() == '0x010601']
assert len(nvme) == 1, 'NVMe canary controller missing from VM'
assert ahci, 'AHCI controller missing from VM'
assert all(not (p / 'driver').exists() for p in nvme + ahci)
assert not any(line.split()[0].startswith('/dev/') and line.split()[1] not in ['/dev','/dev/pts'] for line in mounts.splitlines())
assert pathlib.Path('/run/ods/boot.log').exists()
assert 'No display experiment will start automatically' in pathlib.Path('/run/ods/boot.log').read_text()
profile = pathlib.Path('/run/NetworkManager/system-connections/ods-wifi.nmconnection')
assert profile.exists() == configured
if not configured:
    assert 'Wi-Fi is not configured; Ethernet remains available.' in pathlib.Path('/run/ods/boot.log').read_text()
if configured:
    assert profile.stat().st_mode & 0o777 == 0o600
    ssid = subprocess.check_output(['nmcli','--escape','no','-g','802-11-wireless.ssid','connection','show','ods-wifi'],text=True).rstrip('\n')
    assert ssid == 'ODS synthetic "network"', repr(ssid)
    secret = subprocess.check_output(['nmcli','--show-secrets','--escape','no','-g','802-11-wireless-security.psk','connection','show','ods-wifi'],text=True).rstrip('\n')
    assert secret == 'example-not-a-real-secret'
    assert secret not in pathlib.Path('/run/ods/boot.log').read_text()
assert pathlib.Path('/usr/local/sbin/ods-poweroff').exists()
assert pathlib.Path('/usr/bin/systemctl').exists()
subprocess.run(['busctl','--system','call','org.freedesktop.DBus','/org/freedesktop/DBus',
                'org.freedesktop.DBus','StartServiceByName','su','fi.w1.wpa_supplicant1','0'],
               check=True,stdout=subprocess.DEVNULL)
assert not pathlib.Path('/etc/fstab').read_text().strip()
print(json.dumps({'uid':os.getuid(),'kernel':os.uname().release,'mounts':mounts.splitlines(),
                  'nvme_devices':glob.glob('/dev/nvme*'),'wifi_profile_imported':configured,
                  'nvme_ahci_controllers_present_but_unbound':True,
                  'wifi_supplicant_dbus_activation_verified':True,
                  'ssh_authentication':'none; no client key or password supplied',
                  'boot_log':pathlib.Path('/run/ods/boot.log').read_text().splitlines()},indent=2))
'''
    result = subprocess.run(ssh + ['python3 -B -'], input=program, capture_output=True,
                            text=True, timeout=60)
    if result.returncode:
        (out / (prefix + '-check.log')).write_text(result.stdout + result.stderr)
        raise RuntimeError('Guest checks failed; inspect ' + prefix + '-check.log')
    report = json.loads(result.stdout)
    report['test_scope'] = 'QEMU UEFI USB boot and Ethernet/SSH; no physical Deck, Wi-Fi radio or display timing test'
    report['image_sha256'] = sha(disk)
    subprocess.run(ssh + ['ods-poweroff'], capture_output=True, timeout=15)
    vm.wait(timeout=60)
    assert vm.returncode == 0, 'Guest did not power off cleanly'
    report['guest_poweroff_verified'] = True
finally:
    vm.terminate()
    try:
        vm.wait(timeout=10)
    except subprocess.TimeoutExpired:
        vm.kill()
        vm.wait()
    log.close()
after = hashlib.sha256(canary.read_bytes()).hexdigest()
assert before == after, 'Simulated internal NVMe contents changed'
report['internal_nvme_canary_unchanged'] = True
(out / (prefix + '-report.json')).write_text(json.dumps(report, indent=2) + '\n')
print(case + ': UEFI USB boot, passwordless root SSH, RAM root, shutdown and unchanged NVMe canary verified.', flush=True)
