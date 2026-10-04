# ANX7580 VRR investigation: next experiment and decision points

This plan follows the [initial assessment](vrr-feasibility.md) and the
2026-10-03 read-only receiver-capability test. It is not authorization to change
display timing, stop a compositor, install a kernel, reboot, or write registers.

## Completed first test

The internal display exposes a native AUX device associated with its eDP
connector. The [bounded collector](../opendecksight/dpcd.py) verified the exact
public r04 EDID and that device association, then requested only the first
16 receiver-capability bytes with `pread` on an `O_RDONLY` descriptor. It
exposes no arbitrary address or write API. The raw report is ignored.

**Result:** DPCD `0x00007 = 0x00`, so
`DP_MSA_TIMING_PAR_IGNORED` (bit 6) is clear. The receiver also reports no
extended capability block. Combined with the already-known missing EDID
frequency range, this gives two reasons the inspected upstream AMD discovery
path would reject VRR. The observed running kernel reports `vrr_capable = 0`.

The block reports maximum link-rate code `0x14` and four lanes, which differ
from the `0x0a` / two-lane values in the small reconstructed EC setup table.
These are advertised maxima, not measured negotiated link settings. Their
difference reinforces why a static table is not a complete description of live
bridge initialization; the responsible override/default path remains unknown.

A subsequent physical USB-baseline boot on 2026-10-04 returned the base block
`120a8201010001000202040000000000`, unchanged on a repeat read. Its maximum
link-rate code is `0x0a` and lane count is two, matching that EC setup table.
The MSA-ignore bit and extended-capability flag remain clear. The difference
between captures means the advertised maxima must not be treated as immutable
silicon limits. The responsible initialization/reset/configuration difference
has not been isolated.

This does **not** show that the bridge has been sent a VRR stream, that it
rejected one, or that its silicon cannot pass one. It only establishes its
current capability advertisement. The assumed ANX7580 identity comes from
public board identification, not a chip-ID read in this test.

## The next blocker

ANX7580 pass-through can remain a known unknown while testing end-to-end
behavior. Manufacturer confirmation is not a gate. Prepare and validate the
[optical measurement path](vrr-optical-measurement.md) alongside the source
timing experiment; use failures to decide whether bridge-specific probing is
needed. A successful measured workflow can establish a useful capability
without explaining every bridge internal.

We need a controlled way to make the GPU actually vary frame intervals while
keeping pixel clock and active scan timing stable. The ordinary VRR path is
currently gated off. An EDID override by itself would leave the receiver-bit
obstacle. Setting a userspace VRR request would not demonstrate that the driver
programmed variable timing.

A narrowly scoped experimental kernel quirk is a candidate: bypass capability
discovery only for the exact internal r04 display and supply a tightly bounded
experimental range. This must be built against identified matching kernel
source and reviewed before use. It would test behavior despite the advertised
capabilities; it would not establish that those capabilities were incorrect.
No such patch has been built or booted. The inspected upstream v6.17 AMD
debugfs source has no `vrr`/`freesync` override entry; this is not an exhaustive
claim about downstream kernels or other interfaces.

The [physical fixed-refresh control](vrr-fixed-refresh-control.md) now verifies
native-mode presentation and page-flip event collection in the USB environment.
Its late submissions remain quantized to one or two 60 Hz periods, as expected.
This removes a presentation-tool prerequisite without testing variable timing.

The [physical atomic TEST_ONLY test](vrr-atomic-validation.md) also accepted a
VRR-on request while the connector advertised no VRR capability. An invalid
boolean was rejected, and checked live KMS state remained unchanged. This
confirms that request acceptance alone cannot be used as the experiment's
success criterion. No variable timing was applied by that test.

The [2026-10-04 offline source tests](vrr-kernel-research.md) found a second
minimum-range check in AMD's timing builder, beyond discovery. A 59–60 Hz
request remains inactive even after assumed discovery. A harness-only control
also exposed fixed-refresh fallback that does not recover under ordinary
in-range submissions after late frames. A diagnostic implementation must
address both policies and verify final timing totals before evaluating the
bridge. The tests use a pinned candidate OGC source, not a verified installed
kernel build, and perform no hardware I/O.

The implementation must also arrange display ownership and restore the prior
state. It cannot assume that an SSH process can modeset while the desktop
compositor owns the display. A driver change and a temporary diagnostic boot
may be cleaner than altering the installed system, but booting such an image
still requires approval and a concrete recovery plan.

## Smallest useful active experiment

The following is a design target, not a ready command or a claim of safe panel
limits:

1. Identify the matching kernel source/configuration and implement a strictly
   opt-in quirk, tied to internal connector and full EDID identity. Preserve
   the normal path unless the experiment is explicitly selected.
2. Build and inspect a temporary diagnostic environment locally. It must not
   mount internal storage writable, install services, flash firmware, or
   change persistent boot configuration. Verify those properties before
   proposing a boot procedure.
3. Start from the released native approximately 60 Hz timing, preserving its
   pixel clock and active scanout. Investigate a very narrow downward range
   first, rather than assuming 40–80 Hz works. For illustration, 59–60 Hz is
   roughly 16.67–16.95 ms per frame. A narrow range would also need an explicit
   exception to both the driver's greater-than-10-Hz discovery heuristic and
   the timing builder's independent at-least-10-Hz check. Validate integer-line
   rounding and late-frame fallback as described in the offline source tests.
   Panel tolerance for even this range remains unverified.
4. Use a short deterministic sequence of irregular frame intervals and encoded
   visible frame numbers. Record GPU flip/vblank timing to verify that the
   source varies. Include a fixed-refresh control run. Specify timeouts and
   a restore procedure that does not depend only on the tested display.
5. With a human observing, measure visible updates and check blanking, repeats,
   tearing, flicker and brightness shifts. End immediately on abnormalities.
   A software timeout cannot guarantee recovery from a driver/display hang;
   the human recovery procedure must be agreed beforehand.

No refresh-rate sweep, capability spoof, experimental kernel patch or hardware
control-register write has been performed. The disposable USB has been updated
and rebooted, and its native fixed-refresh control has run. A temporary software
change can still drive real hardware outside documented behavior; lack of
persistence does not make an unverified timing experiment risk-free.

## What evidence would distinguish the outcomes

| Observation | What it would establish | What remains open |
| --- | --- | --- |
| Driver exposes `vrr_capable = 1` after a quirk | Discovery bypass worked | Whether timing changed at either physical interface |
| GPU timestamps vary as intended | Source timing appears to vary | Whether bridge/panel follow it; software timestamps need corroboration |
| Optical measurements follow irregular frame delivery without fixed-cadence quantization | Strong evidence of working end-to-end variable refresh in that tested range | Limits, robustness, brightness behavior and production suitability |
| Screen stays fixed or blanks while the source varies | That configuration fails end-to-end | Bridge versus panel, configuration error, and other possible modes |
| DSI analyzer shows fixed output while DP input varies | Bridge/configuration is the immediate bottleneck | Whether another documented mode or firmware change can fix it |
| DSI output varies but the panel rejects it | Panel/configuration is the immediate bottleneck | Whether another supported panel mode can fix it |

One failed experiment would not establish impossibility. A strong negative
result would need documented hardware limits or a sufficiently understood
bridge/panel design showing that the required timing cannot be generated or
accepted in the available modes. Conversely, success across a narrow range
would justify widening the investigation in small steps.

## What would help from a human

- Panel assembly and controller part numbers, and any vendor programming or
  timing documentation already available. The synthetic EDID name is not the
  panel controller's identity. Existing photos are useful; do not disassemble
  the Deck just to obtain them at this stage.
- An ANX7580 programming manual or a manufacturer answer about per-frame
  variable vertical blanking from DP/eDP to DSI video mode, required bridge
  firmware, and panel requirements. Ask about that exact behavior; support
  for switching fixed rates or DSC would not answer the question.
- For an eventual active experiment, a time when someone can watch the screen
  and perform the agreed recovery procedure. An already-available spare USB
  drive and external monitor would help with a temporary diagnostic boot.
- For measurement, knowing whether a slow-motion camera or photodiode/scope is
  available. A camera helps find obvious failures, but its sampling can alias
  with display scanout; a narrow 59–60 Hz experiment calls for more precise
  timing measurement. Isolating the bridge electrically may require a DSI
  analyzer and suitable probing, not a generic USB logic analyzer.

The preferred measurement setup is an RP2040 board with an amplified
photodiode for timing, supplemented by a high-speed phone camera for visual
context; a suitable ESP32-family board is an alternative. A 240-fps camera alone
is a weak instrument for the proposed narrow 59–60 Hz test. The
[optical plan](vrr-optical-measurement.md) specifies candidate
sample rates, calibration, transport and false-positive checks. Final circuit
and acquisition firmware depend on the exact board and sensor components.

No purchase is necessary for the next offline development step. No outreach
has been sent. Documentation would reduce uncertainty, but its absence does
not prevent preparing a carefully bounded diagnostic implementation.
