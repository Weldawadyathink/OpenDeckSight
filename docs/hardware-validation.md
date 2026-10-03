# Hardware validation

Device confirmed by owner: LCD Steam Deck originally sold with a 512 GB SSD,
now upgraded, running Bazzite. A DeckSight display is installed. SSH can be made
available. No connection or device modification has occurred.

## Information needed next

Read-only SSH access, or the output of the collector, is sufficient for the next
step. Record Bazzite version, running kernel, DMI BIOS version, the EDID actually
exposed by eDP, available backlight path/max value and existing brightness
services. The BIOS version may only say `F7A0133 DS`, which cannot distinguish
r03 from r04 by itself. A 256-byte hardware EDID helps identify r04 behavior.

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
