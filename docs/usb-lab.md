# Disposable USB lab

This builds a bootable x86-64 UEFI disk image for baseline DeckSight research.
It starts a RAM-root Linux environment, networking and **passwordless root SSH**,
with explicit persistent USB updates over SSH.
No client key is required. Anyone who can reach port 22 can control this lab
environment; this is the requested private-network configuration.

The image does not include a VRR kernel patch, compositor, optical pattern
generator or sensor firmware yet. It provides the isolated foundation for those
experiments. Booting it is not evidence that the ANX bridge passes VRR.
A separate [native fixed-refresh utility](vrr-fixed-refresh-control.md) has
since been built and exercised on physical hardware; it is not started at boot
or included in the original recovery image.

## Create the image without a USB drive

Requirements: Python 3.10+, a running Docker-compatible engine, internet access,
and about 25 GB of free build/test space. The builder runs Linux amd64; an ARM host
needs amd64 container emulation. Allow at least 6 GB of memory to the container
engine for the virtual-machine tests.

From the repository root:

```sh
python3 -B tools/build_lab_image.py
python3 -B tools/test_lab_image.py
```

The first command creates `artifacts/usb-lab/opendecksight-lab.img`, its SHA-256
file, `opendecksight-lab-update.tar`, the kernel/initramfs, manifests and a cache of input packages. It
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
then reconnect it and open the **ODSBOOT** volume. The image has a 4 GiB FAT32
data partition and a separate small UEFI partition. A USB drive of 8 GB or more
is sufficient. The extra space holds the recovery baseline, two research builds
and an incoming update. Selecting and overwriting a physical drive is a separate action;
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

Newly generated profiles explicitly use the adapter's permanent Wi-Fi MAC and
a MAC-based IPv4 DHCP client identifier. Fedora's packaged `stable-ssid` default
otherwise derives an address from identity that this RAM-only environment
regenerates each boot. Stable adapter identity helps the router reuse a lease;
it does not guarantee an unchanged IP address. This profile fix requires a new
image or update bundle; the original `1b0a44a` recovery image predates it.
See NetworkManager's [host identity](https://www.networkmanager.dev/docs/api/latest/settings-connection.html)
and [DHCP client identifier](https://www.networkmanager.dev/docs/api/latest/settings-ipv4.html)
documentation. The explicit profile fields also passed an `nmcli --offline`
generation check using the physical lab's packaged NetworkManager.

## Connect and collect

Physical boot, Wi-Fi and SSH have now been exercised; see the validation
checkpoint below. The image uses an unsigned UEFI fallback loader and does not change Secure Boot
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

Selecting the USB once in the firmware boot menu may apply to only that boot.
The first physical remote-reboot test returned to the installed OS even though
the USB update had been staged and verified successfully. Repeated unattended
USB boots require an explicitly selected USB-first firmware boot preference,
with the installed OS retained as fallback. This is separate from selecting a
research slot inside the USB's GRUB menu. Save the existing order before changing
it and verify the result across reboots; do not assume boot-entry numbers are
the same on different machines. The image never changes firmware boot preference
automatically. [UEFI boot-order tool documentation](https://github.com/rhboot/efibootmgr/blob/main/README.md)

Logs are under `/run/ods/`; changes, profiles and logs disappear at shutdown.
Copy useful observations off before using `ods-poweroff` or `ods-reboot`.
These commands act immediately in this disposable environment. No installed
desktop services or settings are involved.

## Change the kernel or userspace over SSH, then reboot

Ordinary edits to the running root filesystem still disappear at reboot.
Persistent changes are installed explicitly as a **kernel plus matching initramfs
bundle on the USB**. The initramfs contains the drivers, tools and startup code,
so this updates both the kernel and userspace. The installed OS remains separate.

After changing the image sources, rebuild only the bundle on the development host:

```sh
python3 -B tools/build_lab_image.py --bundle-only
```

Transfer it directly into an inactive USB research slot, without storing the
whole upload in the Deck's RAM:

```sh
ssh root@<IP-address> 'ods-update install -' < artifacts/usb-lab/opendecksight-lab-update.tar
ssh root@<IP-address> 'ods-update status'
ssh root@<IP-address> 'ods-reboot'
```

The update command verifies both payload sizes and SHA-256 hashes before
selecting the new slot. It mounts only the identified USB volume for writing,
flushes it, and unmounts it before reporting success. It preserves `wifi.json`,
the running research slot and the original recovery files. Installing an update
does not itself reboot or start an experiment. These are commands for an
explicitly authorized device session; the automated tests use only virtual hardware.

Extra kernel arguments can be baked into the bundle with repeated `--boot-arg`
options to the builder, or supplied to `ods-update install`. The installer option
replaces the bundle's extra argument list. It rejects overrides of the lab's
root/init and storage-isolation arguments. Persistent startup/tool changes belong
in the image sources and are delivered in the next initramfs bundle.

For a locally compiled OGC-compatible kernel, provide its core/modules RPM pair
and exact release string:

```sh
python3 -B tools/build_lab_image.py --bundle-only \
  --kernel-rpms artifacts/custom/kernel-core.rpm artifacts/custom/kernel-modules.rpm \
  --kernel-release '<exact uname release>'
```

The builder checks the RPM package names/releases and hashes, extracts them
without executing their scripts, and builds the matching initramfs. The kernel
must retain the storage configuration/initcall names checked in `build.sh`.
This accepts a previously built kernel; it does not compile one or implement
the VRR patch. Custom kernels require `--bundle-only`, so they cannot accidentally
replace the stock kernel in a newly generated recovery image.

## Roll back without reimaging

Each normal update alternates between `research-a` and `research-b`. The
**OpenDeckSight recovery baseline** entry remains in the eight-second boot menu.
To return to it through a working SSH connection:

```sh
ssh root@<IP-address> 'ods-update select baseline'
ssh root@<IP-address> 'ods-reboot'
```

If a new build cannot boot or provide networking, reboot and choose the recovery
entry locally. There is no automatic boot-failure detection or automatic reboot
from a hang. From recovery, the updater can select a verified existing research
slot or install another build. Reimaging should normally be needed only for
damage to the USB filesystem, bootloader or recovery files, not each experiment.

An incomplete/corrupt bundle is rejected before changing the default boot.
Selection is written last, after flushing the staged payload. FAT still cannot
guarantee recovery from every power loss or media failure during a write.
The updater limits each bundle's kernel/initramfs payload to 1 GiB and checks
free space before writing it. Hash checks validate transfer integrity, not
kernel compatibility or the safety of experimental display timings.

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
USB-adapter compatibility or variable scan timing. The physical checkpoint below
covers boot, Wi-Fi and native fixed-refresh presentation; touchscreen, other
USB adapters and variable scan timing remain unverified.
The next display work is a separately reviewed, explicit experiment launcher
with a bounded kernel change and paired fixed-refresh control. See the
[kernel research](vrr-kernel-research.md) and
[optical measurement plan](vrr-optical-measurement.md).

## Remote update validation — 2026-10-04

### Physical checkpoint

The original USB image booted on physical hardware, imported Wi-Fi credentials
from USB into RAM, and provided working root SSH. The AMD display driver and
wireless driver initialized. The internal NVMe controller remained unbound,
no NVMe block device was exposed, and no disk filesystem or swap was mounted.
This checks the intended isolation state; it is not an SSD byte-for-byte audit.

The [native presentation control](vrr-fixed-refresh-control.md) completed 240
page flips and restored the original framebuffer and timing. The receiver still
advertised no MSA-ignore capability and the connector reported `vrr_capable = 0`.
No variable timing or firmware operation was performed.

A streamed update containing the unchanged kernel, a marker and the manually
invoked display utility was verified and selected as a research slot. It booted
successfully after manual USB selection, with the expected marker, utility hash
and kernel argument; Wi-Fi configuration and storage isolation were retained.
The installed-system fallback on the first reboot exposed the separate firmware
boot-order requirement described above. The original recovery files were retained.

A subsequent research-slot update added the permanent-MAC/DHCP identity fix.
After reboot, the selected updated slot, expected utility hash, preserved Wi-Fi
configuration and storage isolation were verified. The connected Wi-Fi MAC
matched the adapter's permanent address, and the explicit MAC-based DHCP policy
was present. Separately, a manually selected USB-first firmware boot preference
survived that reboot, which returned to the USB. A second consecutive lease
reuse and a physical USB-absent fallback boot have not been tested.

The [atomic VRR validation](vrr-atomic-validation.md) subsequently exercised
TEST_ONLY requests without applying a display change. Off and on requests were
accepted, an invalid boolean was rejected, and checked live KMS state remained
unchanged. The connector still advertised no VRR capability.

### Virtual-machine checkpoint

The final 4 GiB data-partition image passed a complete virtual SSH update cycle:

1. Boot the factory baseline with a synthetic Wi-Fi configuration.
2. Stream a kernel/initramfs bundle over SSH into `research-a`. The test adds a
   file to the initramfs using the kernel's documented
   [concatenated archive format](https://docs.kernel.org/driver-api/early-userspace/buffer-format.html)
   and supplies the harmless extra argument `ods.test=ssh-update`.
3. Reboot and verify the new file, new kernel argument, selected research slot
   and retained Wi-Fi profile.
4. Select the recovery baseline over SSH and reboot again. Verify the recovery
   slot is running and the test file is absent, then power off.

The simulated internal NVMe contents remained unchanged across the cycle.
The final source image SHA-256 was
`ba9d539071719d850ee26156edb6f8e62d44904b7ce34ea219f4251411590cac`.
Its raw report is `artifacts/usb-lab/uefi-smoke-wifi-report.json` (ignored).

All 64 unit tests passed, including inactive-slot rotation, recovery selection,
corrupt/truncated upload rejection, and protection of the running slot and boot
arguments. The local-RPM `--bundle-only` path also built successfully using the
known OGC package pair and produced no disk image. This validates that packaging
path, not a new kernel patch or physical VRR operation. Physical Deck boot,
wireless association and display timing remain untested by this checkpoint.

## Initial baseline checkpoint — 2026-10-04 (`0ed2631`)

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

The original baseline image's SHA-256 was
`734ad4cc60e845580b448a676310e0d8a3b59a946ae289b0b1107ea806ea1db1`.
Raw serial logs, VM reports and the image remain in ignored `artifacts/usb-lab/`.
Later rebuilds have their own image hashes.

Kernel packages come from the
[OGC packaging project](https://github.com/OpenGamingCollective/kernel-packages).
The OCI manifest and RPM hashes are pinned in
[`kernel.lock.json`](../lab/usb/kernel.lock.json). Fedora runtime packages,
firmware, GRUB and OVMF retain their upstream licenses; this image is assembled
locally rather than committed to the repository.
