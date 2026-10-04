#!/bin/bash
set -euo pipefail
export LC_ALL=C PYTHONDONTWRITEBYTECODE=1
mkdir -p /work/root /work/esp/EFI/BOOT /work/esp/boot/grub
ROOT=/work/root
python3 /src/lab/usb/package_cache.py
dnf -y --installroot="$ROOT" --releasever=44 --setopt=reposdir=/work/no-repositories \
    --setopt=install_weak_deps=False --setopt=tsflags=nodocs install /out/inputs/runtime/*.rpm

# Extract the pinned kernel as data; never execute its installation scriptlets.
for rpm in /out/inputs/kernel-core-*.rpm /out/inputs/kernel-modules-*.rpm; do
    rpm2cpio "$rpm" > /work/kernel.cpio
    (cd "$ROOT" && cpio -idm --quiet < /work/kernel.cpio)
done
rm /work/kernel.cpio
KVER=$(python3 -c 'import json; print(json.load(open("/src/lab/usb/kernel.lock.json"))["release"])')
test -s "$ROOT/usr/lib/modules/$KVER/vmlinuz"
cp "$ROOT/usr/lib/modules/$KVER/vmlinuz" /work/esp/boot/vmlinuz

# The pinned kernel has built-in NVMe/AHCI/PIIX. Disable their registration
# initcalls in GRUB below, verify the exact symbols, and omit storage modules.
python3 - "$ROOT/usr/lib/modules/$KVER/config" <<'PY'
import sys
from pathlib import Path
path = Path(sys.argv[1])
config = path.read_text().splitlines()
for expected in ['CONFIG_KALLSYMS=y', 'CONFIG_BLK_DEV_NVME=y', 'CONFIG_SATA_AHCI=y',
                 'CONFIG_ATA_PIIX=y', 'CONFIG_MMC_BLOCK=m']:
    if expected not in config:
        raise SystemExit('Storage isolation needs review for this kernel: ' + expected)
symbols = {line.split()[-1] for line in path.with_name('System.map').read_text().splitlines()}
for symbol in ['nvme_init', 'ahci_pci_driver_init', 'piix_init']:
    if symbol not in symbols:
        raise SystemExit('Missing storage initcall: ' + symbol)
PY
rm -rf "$ROOT/usr/lib/modules/$KVER/kernel/drivers/nvme" \
    "$ROOT/usr/lib/modules/$KVER/kernel/drivers/mmc" \
    "$ROOT/usr/lib/modules/$KVER/kernel/drivers/ata"
depmod -b "$ROOT" "$KVER"
mkdir -p "$ROOT/etc/modprobe.d" "$ROOT/usr/local/lib/opendecksight" \
    "$ROOT/etc/NetworkManager/conf.d" "$ROOT/etc/ssh" "$ROOT/root" \
    "$ROOT/proc" "$ROOT/sys" "$ROOT/dev" "$ROOT/run" "$ROOT/tmp"
cat > "$ROOT/etc/modprobe.d/ods-storage.conf" <<'EOF'
blacklist nvme
blacklist nvme_core
blacklist mmc_block
blacklist ahci
blacklist libata
EOF
cat > "$ROOT/etc/NetworkManager/NetworkManager.conf" <<'EOF'
[main]
plugins=keyfile
hostname-mode=none
[logging]
level=WARN
[connectivity]
enabled=false
EOF
cat > "$ROOT/etc/hostname" <<'EOF'
opendecksight-lab
EOF
cat > "$ROOT/etc/hosts" <<'EOF'
127.0.0.1 localhost opendecksight-lab
::1 localhost
EOF
cat > "$ROOT/etc/motd" <<'EOF'
OpenDeckSight USB lab — RAM-only baseline, passwordless root SSH.
No VRR experiment starts automatically. No installed OS is mounted.
Logs: /run/ods/  |  Shutdown: ods-poweroff  |  Reboot: ods-reboot
Logs, SSH host keys and all runtime changes disappear at shutdown.
EOF
cp /src/lab/usb/sshd_config "$ROOT/etc/ssh/sshd_config"
cp /src/lab/usb/init "$ROOT/init"
chmod 755 "$ROOT/init"
cp /src/lab/usb/ods_init.py "$ROOT/usr/local/lib/ods_init.py"
mkdir -p "$ROOT/usr/local/sbin"
printf '#!/bin/sh\nexec /usr/bin/systemctl --force --force poweroff\n' > "$ROOT/usr/local/sbin/ods-poweroff"
printf '#!/bin/sh\nexec /usr/bin/systemctl --force --force reboot\n' > "$ROOT/usr/local/sbin/ods-reboot"
chmod 755 "$ROOT/usr/local/sbin/ods-poweroff" "$ROOT/usr/local/sbin/ods-reboot"
cp /src/opendecksight/{__init__,lab_config,collect,edid,vrr,dpcd}.py "$ROOT/usr/local/lib/opendecksight/"
# Runtime user/password and machine identities are intentionally disposable.
python3 - "$ROOT" <<'PY'
from pathlib import Path
import sys
root = Path(sys.argv[1])
for name, replacement in [('passwd', 'root:x:0:0:Lab root:/root:/bin/bash'),
                          ('shadow', 'root::19000:0:99999:7:::')]:
    path = root / 'etc' / name
    lines = [line for line in path.read_text().splitlines() if not line.startswith('root:')]
    path.write_text(replacement + '\n' + '\n'.join(lines) + '\n')
(root / 'etc/shadow').chmod(0o600)
for path in list((root / 'etc/ssh').glob('ssh_host_*')) + [root / 'etc/machine-id', root / 'var/lib/dbus/machine-id']:
    path.unlink(missing_ok=True)
PY
# No automatic mounts, swaps, resume, machine-ID persistence or installer.
: > "$ROOT/etc/fstab"
rm -rf "$ROOT/var/cache/dnf" "$ROOT/var/cache/libdnf5" "$ROOT/var/log"/*
rm -f "$ROOT/dev/console" "$ROOT/dev/null"
mknod -m 600 "$ROOT/dev/console" c 5 1
mknod -m 666 "$ROOT/dev/null" c 1 3
cp /out/inputs/runtime.lock.json /work/esp/runtime.lock.json
cp /src/lab/usb/kernel.lock.json /work/esp/kernel.lock.json
cp /src/lab/usb/wifi.example.json /work/esp/wifi.example.json
printf '{"wifi": null}\n' > /work/esp/wifi.json
cat > /work/esp/ODS-LAB.txt <<'EOF'
OpenDeckSight USB lab baseline

Edit wifi.json on this FAT volume before booting. Copy the structure from
wifi.example.json, or run tools/configure_lab_wifi.py on the mounted directory.
WPA2/WPA2-WPA3 transition: security "wpa-psk". WPA3-only: "sae".
Wi-Fi credentials stay on this USB in plain text and are imported into RAM.

SSH: root, no password or client key required. Use the IP shown on the screen
or in your router's DHCP lease list. Host keys change each boot.
The USB is mounted read-only only to import configuration, then unmounted.
Runtime logs: /run/ods. Copy them off before shutdown; they are not persistent.
No experimental kernel patch or display test is enabled in this baseline.
The bootloader is unsigned; no Secure Boot settings or keys are changed.
EOF

# initramfs root: no squashfs, overlay or internal disk dependency is needed.
# Keep package ownership (notably the setuid D-Bus activation helper's group).
(cd "$ROOT" && find . -print0 | sort -z | cpio --null -o --format=newc --quiet) \
    | gzip -n -1 > /work/esp/boot/initramfs.img
cat > /work/esp/boot/grub/grub.cfg <<'EOF'
set timeout=3
set default=0
menuentry 'OpenDeckSight lab — fixed-refresh baseline' {
    linux /boot/vmlinuz rdinit=/init console=tty0 console=ttyS0,115200n8 panic=0 initcall_blacklist=nvme_init,ahci_pci_driver_init,piix_init module_blacklist=nvme,nvme_core,mmc_block,ahci,libata
    initrd /boot/initramfs.img
}
EOF
cat > /work/grub-embedded.cfg <<'EOF'
search --no-floppy --fs-uuid --set=root 0D51-AB01
configfile /boot/grub/grub.cfg
EOF
grub2-mkstandalone -O x86_64-efi \
    --modules='part_gpt fat normal linux search search_fs_uuid configfile all_video' \
    -o /work/esp/EFI/BOOT/BOOTX64.EFI 'boot/grub/grub.cfg=/work/grub-embedded.cfg'
python3 /src/lab/usb/manifest.py
truncate -s 1024M /work/esp.fat
mkfs.vfat -F 32 -n ODSBOOT -i 0D51AB01 /work/esp.fat
mcopy -s -i /work/esp.fat /work/esp/* ::/
# A normal data partition is easy to mount on Windows/macOS. A separate small
# ESP holds the UEFI fallback loader; GRUB finds the payload by its FAT UUID.
truncate -s 32M /work/efi.fat
mkfs.vfat -F 16 -n ODSEFI -i 0D51EF01 /work/efi.fat
mcopy -s -i /work/efi.fat /work/esp/EFI ::/
truncate -s 1058M /work/opendecksight-lab.img
sgdisk --clear --new=1:2048:+1024M --typecode=1:0700 --change-name=1:ODSBOOT \
    --new=2:0:+32M --typecode=2:ef00 --change-name=2:ODSEFI /work/opendecksight-lab.img
dd if=/work/esp.fat of=/work/opendecksight-lab.img bs=1M seek=1 conv=notrunc status=none
dd if=/work/efi.fat of=/work/opendecksight-lab.img bs=1M seek=1025 conv=notrunc status=none
sgdisk --verify /work/opendecksight-lab.img
cp /work/esp/boot/{vmlinuz,initramfs.img} /out/
cp /work/esp/build-manifest.json /out/build-manifest.json
cp /work/opendecksight-lab.img /out/opendecksight-lab.img
(cd /out && sha256sum opendecksight-lab.img > opendecksight-lab.img.sha256)
echo 'USB image created; no physical drive was opened or written.'
