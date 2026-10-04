# Disposable USB lab

This builds a bootable x86-64 UEFI disk image for baseline DeckSight research.
It starts a RAM-root Linux environment, networking and **passwordless root SSH**.
No client key is required. Anyone who can reach port 22 can control this lab
environment; this is the requested private-network configuration.

The image does not include a VRR kernel patch, compositor, optical pattern
generator or sensor firmware yet. It provides the isolated foundation for those
experiments. Booting it is not evidence that the ANX bridge passes VRR.

## Create the image without a USB drive

Requirements: Python 3.10+, a running Docker-compatible engine, internet access,
and about 15 GB of free build space. The builder runs Linux amd64; an ARM host
needs amd64 container emulation. Allow at least 6 GB of memory to the container
engine for the virtual-machine tests.

From the repository root:

```sh
python3 -B tools/build_lab_image.py
python3 -B tools/test_lab_image.py
```

The first command creates `artifacts/usb-lab/opendecksight-lab.img`, its SHA-256
file, the kernel/initramfs, a build manifest and a cache of input packages. It
never opens or writes a physical drive. The second command boots the USB layout
under QEMU UEFI and checks remote access and storage isolation; its SSH forwarding
is confined to the test container, with no host port published.

The default kernel is the pinned OGC `7.2.3-ogc3.1.fc44.x86_64` binary package.
Its release string matches the research baseline. That does not establish an
identical build/configuration to another installation. Kernel RPMs are extracted
as data, without running their installation scripts.

The initial build uses the checked-in runtime package lock; rebuilding reuses
the saved lock/cache and checks hashes and Fedora signatures. Retain that cache:
mirrors may eventually stop serving an old RPM. `--refresh-runtime` explicitly
resolves a new Fedora package set,
preserving the previous cache. `--skip-builder-build` reuses the local builder
container image. Build inputs and package versions are recorded; the resulting
disk image is **not claimed to reproduce byte-for-byte** across builds.

All downloads, complete payloads, images and raw test reports stay in ignored
`artifacts/`. No Wi-Fi credentials are needed during the build.

## Configure the USB later

When a drive is available, write the complete `.img` with a disk-image writer,
then reconnect it and open the **ODSBOOT** volume. The image has a 1 GiB FAT32
data partition and a separate small UEFI partition. A USB drive of 2 GB or more
is sufficient. Selecting and overwriting a physical drive is a separate action;
the generator does not do it.

Either edit `wifi.json` using `wifi.example.json` as a guide, or run the helper
against the mounted ODSBOOT directory:

```sh
# macOS example; use the actual mounted directory on your system.
python3 -B tools/configure_lab_wifi.py /Volumes/ODSBOOT
```

The helper prompts for the network name and hides the password while typing.
Manual JSON example:

```json
{
  "wifi": {
    "ssid": "Your network",
    "password": "Your Wi-Fi password",
    "security": "wpa-psk",
    "hidden": false
  }
}
```

Use `wpa-psk` for WPA2 or WPA2/WPA3 transition mode, `sae` for WPA3-only, and
`open` with an empty password for an open network. The helper accepts
`--security sae` and `--hidden`. Enterprise Wi-Fi and captive-portal setup are
outside this initial implementation. `{"wifi": null}` leaves Wi-Fi unconfigured;
Ethernet DHCP remains available with a supported USB adapter.

Credentials are plain text on the FAT partition; FAT does not enforce Unix file
permissions. `wifi.json` is Git-ignored. The runtime treats it as data, mounts the
USB read-only while importing it, creates a NetworkManager profile in RAM, then
unmounts the USB. Malformed configuration is rejected without logging its values.

## Connect and collect

Booting the physical Deck has not been performed by this implementation work.
The image uses an unsigned UEFI fallback loader and does not change Secure Boot
settings or enroll keys. Device boot/configuration changes and later active
display experiments remain separate, concrete actions requiring human approval
under the project's working constraints.

Once booted, the console prints its IP addresses. The router's DHCP lease list
is another way to find it. Connect with:

```sh
ssh root@<IP-address>
```

Each boot generates a fresh SSH host key. A separate lab known-hosts file avoids
mixing these disposable identities with normal machines:

```sh
ssh -o UserKnownHostsFile=./artifacts/usb-lab/known_hosts root@<IP-address>
```

If SSH reports a changed host key after a reboot, remove only that lab entry
from that file before connecting again. Passwordless login still uses encrypted
SSH transport. The configuration follows OpenSSH's
[PermitEmptyPasswords and PermitRootLogin settings](https://man.openbsd.org/sshd_config).

Logs are under `/run/ods/`; changes, profiles and logs disappear at shutdown.
Copy useful observations off before using `ods-poweroff` or `ods-reboot`.
These commands act immediately in this disposable environment. No installed
desktop services or settings are involved.

## Isolation and remaining validation

The Linux root is an initramfs. There is no installed-root mount, swap, resume,
automounter or installer. NVMe, MMC and ATA modules are omitted. This pinned kernel
also has built-in NVMe/AHCI/PIIX drivers: GRUB disables their registration with
`initcall_blacklist=nvme_init,ahci_pci_driver_init,piix_init`. The build verifies
the corresponding kernel configuration and symbols. This uses the documented
[kernel initcall blacklist](https://docs.kernel.org/admin-guide/kernel-parameters.html);
keep these boot arguments intact. It requires USB
ancestry as well as the expected filesystem UUID before reading configuration.
The original kernel is otherwise unpatched. Normal driver initialization still
occurs; this is not a proof of hardware safety for future experiments.

The virtual tests cannot establish physical Deck Wi-Fi, display, touchscreen,
USB-adapter compatibility or variable scan timing. Those remain hardware checks.
The next display work is a separately reviewed, explicit experiment launcher
with a bounded kernel change and paired fixed-refresh control. See the
[kernel research](vrr-kernel-research.md) and
[optical measurement plan](vrr-optical-measurement.md).

## Validation checkpoint — 2026-10-04

The image was built and tested with QEMU/OVMF UEFI, an emulated USB boot disk,
3 GiB of guest RAM, Ethernet and a writable simulated internal NVMe disk.
Both the unconfigured image and a disposable copy with synthetic Wi-Fi
credentials passed:

- Boot through the real GPT/UEFI/GRUB USB layout into the RAM root.
- Root SSH using authentication `none`, without a client key or password.
- Read configuration from USB, then leave all disk filesystems unmounted.
- Import the configured SSID/password into NetworkManager, with mode 0600 on
  the RAM profile; activate the Wi-Fi supplicant through D-Bus.
- Find NVMe/AHCI controllers present but without bound drivers, and no NVMe
  block devices; preserve the simulated SSD's contents through shutdown.
- Power off through `ods-poweroff` with a successful QEMU exit.

Interactive SSH terminal allocation was also verified during the configured
boot. All 58 repository unit tests passed, including a regression for incomplete
network-address records during startup. Shell syntax and recorded build-source
hashes were checked. No physical Deck or Wi-Fi radio was used for these tests.

The tested default image's SHA-256 was
`734ad4cc60e845580b448a676310e0d8a3b59a946ae289b0b1107ea806ea1db1`.
Raw serial logs, VM reports and the image remain in ignored `artifacts/usb-lab/`.
Later rebuilds have their own image hashes.

Kernel packages come from the
[OGC packaging project](https://github.com/OpenGamingCollective/kernel-packages).
The OCI manifest and RPM hashes are pinned in
[`kernel.lock.json`](../lab/usb/kernel.lock.json). Fedora runtime packages,
firmware, GRUB and OVMF retain their upstream licenses; this image is assembled
locally rather than committed to the repository.
