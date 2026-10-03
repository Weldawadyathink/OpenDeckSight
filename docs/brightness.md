# Brightness protocol findings

Input: `decksight-brightnessctrl` from r04, SHA-256
`c7e62509bb327a93630071c535051f5e8506d7020c4fb1b18cba429f102994d9`.
ELF64 x86-64 PIE, stripped. It has been disassembled, not executed.
The binary uses GLIBC symbols through 2.38; OpenDeckSight avoids this binary dependency.

## Recovered behavior

| ELF virtual address | Operation |
| --- | --- |
| `0x1190..0x1218` | Open `/dev/mem` read/write, synchronous; map 4096 bytes at physical `0xfe700000`; mailbox base is mapped offset `0xb00` |
| `0x1218..0x132f` | Glob `/sys/class/drm/card*-eDP-1/amdgpu_bl*/brightness`, choose first, read sibling `max_brightness` (fallback 65535) |
| `0x13c9..0x140f` | Scale brightness to `[0x0280,0x0900]`, round to nearest using integer arithmetic |
| `0x140f..0x1457` | Write payload to bridge register `0x70`, then header to `0x6c` |
| `0x16d0..0x177d` | Submit mailbox writes and poll bit 7 of the command byte; timeout about 200 ms |
| `0x1468..0x14bf` | Sleep 200 ms; use CLOCK_MONOTONIC to detect a loop gap exceeding 400 ms and force a resend |

For requested brightness `v` and maximum `m`:

```text
b = 0x280 + floor((min(v,m) * 0x680 + floor(m/2)) / m)
payload = [0x51, b >> 8, b & 0xff, 0x00]
header  = [0x39, 0x03, 0x00, 0x00]
```

`0x51` is DCS set-display-brightness. `0x39` is the DCS long-write data type;
the header's word count is 3. Minimum is 640; maximum is 2304. This is a register
range, not measured nits and not a linear perceived-brightness claim. A zero OS
setting still sends minimum brightness, not display-off.

Each bridge write uses the following physical addresses, in this order:

```text
0xfe700ba5 <- 0xc0                 target/slave field (exact EC semantics unresolved)
0xfe700ba6 <- 0x70 or 0x6c         bridge register
0xfe700ba7 <- four payload bytes  little-endian 32-bit store in original binary
0xfe700ba4 <- 0x84                 trigger (busy bit 0x80)
poll 0xfe700ba4 until bit 7 clears, up to 200 × 1 ms
```

The register naming is consistent with DeckHD's public ANX bridge header.
Clearing busy establishes that the EC accepted/completed its command sequence;
the original binary does not check a panel acknowledgement or error status.

## Differences worth preserving or improving

The original remembers the requested brightness even when a mailbox write fails,
which can suppress retries until a new value or long loop gap. The replacement
should only remember a successful write. The original also proceeds after some
backlight discovery failures; the replacement should reject ambiguous/missing
sources before touching MMIO.

CLOCK_MONOTONIC normally excludes suspend time. A >400 ms loop-gap check alone
is not a reliable resume detector. A replacement can use CLOCK_BOOTTIME on Linux
to include suspend time, then reapply the setting on wake. This still requires
device validation, especially because the kernel/firmware may use the same EC
mailbox. A userspace lock coordinates OpenDeckSight processes only.

## Evidence boundary

No `/dev/mem` access has occurred during this investigation. Protocol encoding
is recovered; EC arbitration, panel acknowledgement, wake timing and Bazzite
kernel access restrictions remain unvalidated. The daemon is experimental until
the hardware validation plan has been completed.
