# Native fixed-refresh control

The disposable USB environment completed a physical DeckSight presentation test
on 2026-10-04. This establishes a working software control for later optical
measurements. It does not test VRR pass-through or measure panel light output.

## Test boundary

The [test utility](../lab/usb/fixed_present.c) requires the exact public 256-byte
r04 EDID, `vrr_capable = 0`, a single connected internal eDP display, and an
already-active mode matching the native r04 timing. It rejects any change to
pixel clock, active dimensions, sync boundaries, totals, skew, scan multiplier
or mode flags. Its native control and 16 rejection cases passed in a local
[guard test](../tests/fixtures/fixed_present_test.c), including rejection of the
1957/1989-line totals considered for future VRR experiments.

The utility uses two CPU-filled DRM framebuffers and legacy page-flip events.
It requests no VRR property and never accesses AUX, hardware control registers
or firmware. The brief pattern is a moving gray bar with an eight-bit frame
number strip. It restores the original framebuffer and verifies the restored
framebuffer ID and mode through a GETCRTC query. Failure to obtain DRM master
causes refusal; it does not stop an existing compositor.

Each pending flip has a two-second event timeout. SIGINT/SIGTERM request
cleanup, and the physical run used an additional 30-second process timeout.
These bounds cannot guarantee recovery from a kernel hang. The recovery USB
baseline remains available independently of this utility.

## Physical result

The running kernel was the pinned `7.2.3-ogc3.1.fc44.x86_64` USB baseline.
Cached KMS state matched the public timing fixture: 143.18 MHz pixel clock,
1220 by 1956 totals, 1080 by 1920 active pixels. Its calculated refresh is
60.000335 Hz; this is a mode calculation, not an optical frequency measurement.

All 240 requested flips completed, and framebuffer restoration was verified.
No new messages appeared in the filtered GPU/driver log during the test.
The initial phase submitted frames promptly after the preceding event. The
second phase alternated short and deliberately late submissions. Excluding
startup and the phase boundary:

| Phase | GPU page-flip event intervals | Vblank sequence increments |
| --- | --- | --- |
| Regular submissions | 16.666–16.667 ms | 111 intervals of one tick |
| Alternating short/late submissions | 16.666–16.667 or 33.333–33.334 ms | 59 intervals of one tick, 60 of two ticks |

This is the expected fixed-refresh quantization. It verifies the presentation
and timestamp collection path and supplies a negative control: irregular frame
submission alone does not establish variable refresh. Kernel event timestamps
and sequence counters do not prove how the bridge or panel physically scans.
Optical acquisition will need to distinguish the same fixed-cadence behavior
from a later, separately approved variable-timing experiment.
An [anonymous result summary](../research/reports/vrr-fixed-refresh-control.json)
records the source hash, test mode and interval counts without raw device data.

## Build and use

This utility is separate from the default image; it is never launched during
boot. Build for Linux x86-64 with GCC, libdrm development headers and pkg-config:

```sh
mkdir -p .tools/fixed-present
cc -std=c11 -O2 -Wall -Wextra -Werror $(pkg-config --cflags libdrm) \
  lab/usb/fixed_present.c -o .tools/fixed-present/ods-fixed-present \
  $(pkg-config --libs libdrm)
cc -std=c11 -O2 -Wall -Wextra -Werror $(pkg-config --cflags libdrm) \
  tests/fixtures/fixed_present_test.c -o .tools/fixed-present/guard-test \
  $(pkg-config --libs libdrm)
.tools/fixed-present/guard-test
```

The executed build used GCC `16.2.1-2.fc44` and libdrm `2.4.134-1.fc44` in a
local amd64 Fedora container. The program links only libc and libdrm. Compilers
and development packages were not installed on the physical test system.

In an authorized disposable USB session, place the binary in RAM or in an
explicit update bundle. Identify the card containing the internal eDP connector
instead of assuming that it is always `card0` or `card1`. Then use:

```sh
/run/ods-fixed-present --check /dev/dri/cardN
timeout --signal=TERM --kill-after=5s 30s \
  /run/ods-fixed-present --run /dev/dri/cardN
```

`--check` performs cached metadata queries without submitting frames. `--run`
temporarily replaces displayed content while preserving the exact mode. Output
is JSON Lines, with preflight, individual flip, completion and restore records.
Save output off the device before shutdown. Complete raw captures, artifact
hashes, build package versions and the diagnostic overlay manifest are retained
under ignored `artifacts/usb-lab/`; local executables remain in `.tools/`.

The remaining software work is the scoped experimental kernel change and its
instrumentation described in [the source investigation](vrr-kernel-research.md).
The optical sensors are needed for physical timing evidence, not for developing
those components or validating the USB update mechanism.
