# Hardware validation

Device confirmed by owner: LCD Steam Deck originally sold with a 512 GB SSD,
now upgraded, running Bazzite. A DeckSight display is installed. SSH can be made
available. Read-only SSH inspection was performed on 2026-10-03; no device
files, services, settings, MMIO or firmware were modified by the investigation.

**Owner requirement:** anything potentially dangerous to hardware or software
must receive human confirmation first. No runtime write tests are authorized.

## Read-only findings on 2026-10-03

- Valve Jupiter, DMI `F7A0133` (no ` DS` suffix exposed through DMI).
- Bazzite 44, `bazzite-deck`, build `Stable (F44.20260907)`.
- Running kernel `7.2.3-ogc3.1.fc44.x86_64`.
- Connected internal `card1-eDP-1` exposes the exact 256-byte r04 EDID.
- Backlight is `amdgpu_bl1`, maximum 65535. Snapshot requested value 19661;
  `actual_brightness` was 11822. These are OS values, not measured panel luminance.
- `decksight-brightnessctrl.service` is loaded and running. Installed binary
  SHA-256 exactly matches the analyzed r04 binary.
- OpenDeckSight's service is not installed.

The collector was streamed to `python3 -B -` over SSH. Its raw report is saved
locally in ignored `artifacts/device-readonly-2026-10-03.json`. The command did
not create a remote file. These observations establish the current software and
EDID identity, not the contents of the device's full flash chip.

## Information needed next

The initial inventory is complete. Runtime write tests remain deferred until
explicit human approval. Deeper offline firmware reconstruction can continue
without changing the Deck. A panel/controller part number or datasheet would
help explain the remaining vendor-specific initialization commands if the owner
already has that information; opening the device is not requested.

The collector must avoid firmware writes, MMIO, serial numbers, networking
configuration, credentials and unrestricted journal dumps. No sudo is needed.

## Runtime brightness validation

The collector is now implemented. From a checkout on the Deck:

```sh
python3 -m opendecksight collect deck-report.json
```

It creates a new JSON file and refuses to overwrite an existing one. Only the
allowlisted sysfs/OS fields, internal eDP EDID, two service states and hashes of
known installed brightness binary paths are collected.

1. Capture a read-only baseline and identify any running proprietary brightness daemon.
2. Compare preview packets at minimum, middle and maximum OS settings.
3. Coordinate a brief service stop and one explicit OpenDeckSight brightness write.
4. Check that output changes, no new kernel errors appear and restoring the
   existing service returns normal behavior.
5. Test transitions between desktop and gaming sessions, suspend/resume and
   several refresh rates. Record visual behavior and service logs.

Runtime MMIO is explicit opt-in. Validation should begin with a single write,
not unattended installation. A mailbox timeout is an error, not success.
No raw display-controller register sweep or speculative command will be used.

## Firmware validation is a later stage

Before any experimental firmware boot, obtain a full device-specific SPI backup
and establish a tested external recovery method. The public release does not
contain device-specific data. Determine which EC bank executes and why the
second table has reversed values. Analyze the update-container signature/trust
mechanism independently. A generated research `.bin` must not be handed to the
vendor updater as if it were a signed `.fd`.

No additional computer software is currently required from the owner. Python,
Apple's LLVM disassembler and a locally downloaded UEFIExtract have been enough
for the offline stage. Ghidra or an 8051-aware disassembler may help deeper EC
analysis later; no global installation has been made.
