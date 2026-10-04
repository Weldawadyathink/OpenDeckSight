# Hardware validation

Target platform: LCD Steam Deck (Valve Jupiter) with a DeckSight display.
The findings below summarize a read-only compatibility check on Bazzite.

**Safety requirement:** anything potentially dangerous to hardware or software
must receive human confirmation first. The read-only observations below are
separate from the controlled [disposable USB tests](usb-lab.md) and
[native fixed-refresh control](vrr-fixed-refresh-control.md).

## Read-only compatibility findings

- Valve Jupiter, DMI `F7A0133` (no ` DS` suffix exposed through DMI).
- The internal eDP connector exposes the exact 256-byte r04 EDID.
- Backlight is `amdgpu_bl1`, maximum 65535. This is the OS interface range,
  not a measurement of panel luminance.
- The installed proprietary brightness executable's
  SHA-256 exactly matches the analyzed r04 binary.
- A cached DRM property query reports `vrr_capable = 0` on the internal
  connector. The matching r04 EDID has no refresh-range declaration. This is
  a current software capability finding, not proof of hardware impossibility;
  see [true VRR feasibility](vrr-feasibility.md).
- A subsequent bounded native AUX capability read found DPCD `0x00007` bit 6
  clear. The internal receiver does not advertise ignoring MSA timing
  parameters. No variable-timing signal has been tested; the
  [bridge investigation plan](vrr-bridge-test-plan.md) separates discovery,
  signal generation and physical verification.

These observations establish software and EDID identity, not the contents of
the device's full flash chip. They do not validate the open brightness controller
or establish compatibility across Bazzite versions. Raw inventories remain in
ignored `artifacts/`; public reports omit ownership, access details and
transient settings.

## Information needed next

Brightness/mailbox writes remain deferred until explicit human approval. Deeper
offline firmware reconstruction can continue without changing a device.
Public panel/controller identification or programming documentation would help
explain the remaining vendor-specific initialization commands.

The collector must avoid firmware writes, MMIO, serial numbers, networking
configuration, credentials and unrestricted journal dumps. No sudo is needed.

## Runtime brightness validation

The collector is now implemented. From a checkout on the Deck:

```sh
mkdir -p artifacts
python3 -m opendecksight collect artifacts/device-report.json
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

The offline stage uses Python, Apple's LLVM disassembler and locally downloaded
UEFI tools. See [reproduce.md](reproduce.md) for tool versions and commands.
An 8051-aware disassembler may help deeper EC analysis.
