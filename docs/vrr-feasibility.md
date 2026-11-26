# True variable refresh on DeckSight: feasibility assessment

Initial research: 2026-10-03; optical update: 2026-11-26. Scope: LCD Steam
Deck / DeckSight r04, using this project's reconstructed firmware, public
sources, compatibility observations and approved bounded timing experiments.
**The ordinary Linux interface does not advertise VRR. A guarded diagnostic
driver now has optical evidence that visible updates follow variable GPU
timing through the complete bridge/panel path in a narrow 59–60 Hz window.**
Whole-panel variable scanout, tear-free behavior, a useful wider range and
production support remain unestablished.

The project has useful control over initialization and display metadata. The
new optical evidence argues against an absolute timing incompatibility in the
ANX/panel path, materially improving feasibility. It does not identify the
internal mechanism, establish standards compliance or support a success
percentage for a wider-range implementation.

The [physical A/B/A experiment](vrr-visual-experiment.md) kept the native pixel
clock and used a roughly 59–60 Hz window. Reported GPU periods varied only in
the VRR-requested phase and returned to fixed cadence afterward. Motion looked
equally smooth in both phases, with no reported tearing or flicker. Sampled
DPCD `0x107` reads remained zero, leaving standard control-request behavior
unresolved. The disabled baseline was restored. This is progress past the
source-generation obstacle, not an optical measurement of variable scanout.

The subsequent [optical fixed / VRR / fixed experiment](vrr-optical-ab.md)
recovered all 1,442 intended content changes in each of a fixed control and
one experimental run. During the VRR phase, optical timing followed GPU events
with 9.22 us residual standard deviation, versus 3.51 ms distance spread from
the original uninterrupted 60 Hz grid. Clock and polarity calibration used
only the first fixed phase. Same-polarity optical/source period estimates
correlated at r = 0.9967. This is strong evidence of variable visible-update
timing at the measured location, with no whole-screen visual assessment in
that session. The disabled native baseline was restored and verified.

## What counts as true VRR

Frame delivery must determine when the next scan begins, within a supported
range, without a modeset for every rate change. Linux describes this as
extending the vertical front porch until a page flip or timeout. The connector
property `vrr_capable` reports driver support; the CRTC's `VRR_ENABLED` property
is a request to use it. Merely setting the latter is not proof that the display
supports variable refresh.
[Linux KMS documentation](https://docs.kernel.org/6.17/gpu/drm-kms.html#variable-refresh-properties)

The existing [DeckSight Gamescope profile](../third_party/gamescope/DeckSight.lua)
provides 41 selectable fixed rates, 40–80 Hz. Its generator keeps the totals
at 1240 × 1998 and recalculates the pixel clock. Those are separate fixed modes;
the profile contains no implementation of per-frame variable blanking. Its
comment also excludes rates with less stable initialization. A range of fixed
modes does not establish a VRR range.

## Observed and verified evidence

| Evidence | Result | Meaning and limit |
| --- | --- | --- |
| Anonymous compatibility query on Bazzite, kernel `7.2.3-ogc3.1.fc44.x86_64` | Internal eDP connector has `vrr_capable = 0` | The running driver does not advertise VRR for this path. Does not prove a silicon limitation. |
| Follow-up native AUX capability read | DPCD `0x00007` is `0x00`; bit 6 is clear | The receiver does not advertise ignoring MSA timing parameters. This is another discovery obstacle, not a silicon impossibility result. |
| Internal connector EDID | Exact match to the public r04 256-byte EDID; SHA-256 `53c47cbd31b785b332a890d5074b46ac4efe88d96cc210b041ee07773a4dfe48` | Connects the observation to the analyzed release metadata; not a dump of installed firmware. |
| r04 EDID base block | One 1080 × 1920 DTD, about 60 Hz; no monitor-range descriptor (`0xfd`) | No advertised min/max vertical-frequency range. |
| r04 EDID extensions | One CTA extension containing only HDR static metadata | No DisplayID timing-range block or AMD FreeSync vendor block. HDR metadata is independent of VRR. |
| Existing EC reconstruction | EDID relocation, bridge configuration and panel commands are understood at the transport level | Provides places to investigate changes; several command effects remain opaque. |
| Public panel identification | A retained ICNA3512 datasheet matches several initialization commands; exact controller identity remains unverified | The generated `DSO:5001` identity is not a controller part number. See the [controller-family evidence](vrr-icna3512.md). |
| Guarded 59–60 Hz optical comparison | All intended visible changes followed variable GPU timing at one screen location; fixed controls remained native-periodic | Evidence that the complete path can carry variable visible-update timing; one run does not establish whole-panel scanout, wider-range tolerance or production VRR. |

The new [collector](../opendecksight/vrr.py) opens the DRM card read-only and
calls only `drmModeObjectGetProperties` and `drmModeGetProperty`, plus their
memory-free functions. It does not acquire DRM master, enable client
capabilities, reprobe connectors, modeset, access MMIO/AUX/debugfs, or read
framebuffers. Missing properties and failed queries are distinct from a zero
value. Raw reports remain in ignored `artifacts/` and are not published.

## Where support could be blocked

The expected platform path is:

```mermaid
flowchart LR
    A[Game and compositor] --> B[AMDGPU display engine]
    B -->|eDP| C[Analogix ANX7580 bridge]
    C -->|MIPI DSI| D[DeckSight panel controller]
    D --> E[OLED scanout]
```

The bridge identification comes from the
[public LCD Steam Deck board teardown](https://www.ifixit.com/Teardown/Steam+Deck+Chip+ID/147811),
not an invasive inspection of the tested unit. Analogix describes the ANX7580
as an eDP/DP-to-MIPI device with DSC support. Its available product page does
not specify Adaptive-Sync pass-through or variable vertical-blanking behavior.
Absence from a product page is not proof of lack of support. The linked product
brief returned HTTP 404 during this research; no full programming manual was
obtained.
[Analogix ANX7580](https://www.analogix.com/en/products/dp-mipi-converters/anx7580)

### 1. Kernel capability discovery: a known obstacle

In the inspected upstream Linux **v6.17** reference implementation,
`amdgpu_dm_update_freesync_caps()` handles both DP and eDP. It requires a link
that permits ignoring MSA timing parameters and an advertised vertical refresh
range spanning more than 10 Hz. It can obtain the range from EDID/DisplayID.
The released r04 metadata lacks that range. This reference is not asserted to
be the exact source of the tested downstream kernel.
[AMDGPU source, lines 12599–12710](https://github.com/torvalds/linux/blob/v6.17/drivers/gpu/drm/amd/display/amdgpu_dm/amdgpu_dm.c#L12599)

The [2026-10-04 candidate OGC source investigation](vrr-kernel-research.md)
confirmed those discovery gates and found an additional minimum-range check
inside the timing builder. Local tests also reproduced a late-frame fallback
that can hold a narrow-range experiment at fixed refresh. These are software
experiment-design constraints, not evidence against bridge or panel support.

The relevant receiver capability is DPCD `0x00007`, bit 6
(`DP_MSA_TIMING_PAR_IGNORED`). A follow-up native AUX read found **byte 7 =
`0x00`, so this capability is not advertised**. The base block also reports no
extended receiver-capability block. The missing EDID range and clear receiver
bit are two distinct discovery obstacles. Neither determines whether different
bridge configuration could support the behavior.
[Linux DP definitions](https://github.com/torvalds/linux/blob/v6.17/include/drm/display/drm_dp.h#L143)

The short EC link-configuration table at `0x6965..0x697f` contains no entry for
bridge address `0x1007`. That is a bounded static observation, not a statement
about the bridge's reset defaults, other initialization paths or live DPCD.
The complete table and input hashes are in the
[static analysis record](../research/reports/vrr-static-analysis.json).

Adding an EDID range, advertising a capability bit, or forcing a kernel quirk
would only change what the driver believes. None would create missing bridge
or panel behavior. The guarded driver experiment now has supporting optical
evidence, but there is still insufficient evidence for a general enablement
patch or fabricated production capability range.

### 2. Bridge timing: the main transport uncertainty

The bridge must turn a variable-interval DP stream into correspondingly timed
DSI frames, without treating each interval change as a lost signal, requiring
reinitialization, or continuing to scan at its own fixed cadence.

The [existing BIOS analysis](bios.md) shows fixed porch/frame-rate parameters
and a transfer-mode change consistent with non-burst sync events. The public
DeckHD register header names panel frame rate, vertical porches, video-stability
events and DSI timing registers. These are useful investigation targets, but
register names alone do not establish how the bridge responds to a varying
vertical interval. Non-burst video mode alone neither proves nor rules out VRR.
[DeckHD register definitions](https://github.com/DeckHD/BiosMaker/blob/master/chicago_registers.h)

The decisive question is whether the bridge can follow each incoming frame
boundary automatically. A firmware routine that reprograms a fixed mode after
detecting a rate change would not by itself provide true VRR. Bridge firmware
and/or documented configuration may be needed; an inflexible timing generator
would make support on the existing hardware much less likely.

The optical result now constrains this uncertainty: visible updates track
variable source timing through the existing path in the narrow experiment.
An unchanged uninterrupted native-60-Hz output does not explain that trace.
This does not directly measure DSI signaling or exclude every buffering model;
the bridge's internal implementation and behavior over larger timing changes
remain unknown.

### 3. Panel timing: a separate hardware uncertainty

The subsequently retained [ICNA3512 datasheet](vrr-icna3512.md) provides a
conditional interpretation of the existing `48 03` initialization: video mode
with GRAM bypass. This makes independent full-frame rescan a less compelling
assumption if the definitions apply, but proves neither controller identity nor
variable blanking support. Its dynamic-frame-rate feature listing and typical
video timings do not establish an allowed DeckSight VRR range.

Even a transparent bridge would not be sufficient. The panel controller must
accept variable frame intervals in its configured mode and preserve correct
OLED scanout. Its acceptable blanking limits and any required vendor commands
are unknown. The initialization's tear-control commands and DSC toggle do not
demonstrate Adaptive-Sync support; the opaque commands remain labeled as such
in [panel-init.md](panel-init.md).

The narrow optical result is evidence that the configured panel produces
variable visible-update timing at one location. It does not establish uniform
whole-panel scans, correct brightness everywhere, tolerated porch limits or
the absence of tearing. A short timing success is not a reliability result.

Shade Technik lists 144 Hz as a panel capability not supported on the Deck,
and discusses DSC as a route to higher rates. Those claims concern throughput
and fixed refresh ceilings, not demonstrated VRR. The manufacturer also
describes the bridge and panel's DSC path, but that is not a VRR implementation.
[DeckSight technical information](https://www.shadetechnik.com/decksight_info)

Consequently, enabling DSC or pursuing 120/144 Hz is not a prerequisite for
answering the VRR question. A bounded range below an already supported maximum
is the more focused research target. Panel brightness variation and flicker
would still require validation even if timing works.

## Why the existing 40–80 Hz range cannot be assumed

An illustrative calculation using the Lua profile's timings:

| Timing model | Pixel clock | Horizontal total | Vertical total | Vertical front porch |
| --- | --- | --- | --- | --- |
| Existing fixed 80 Hz mode, ideal arithmetic | 198.2016 MHz | 1240 | 1998 | 3 lines |
| Existing fixed 40 Hz mode, ideal arithmetic | 99.1008 MHz | 1240 | 1998 | 3 lines |
| Hypothetical 40 Hz frame in 40–80 Hz VRR | 198.2016 MHz | 1240 | 3996 | 2001 lines |

This uses `refresh = pixel_clock / (htotal × vtotal)`, holding active pixels,
horizontal timing, vertical sync and back porch constant in the VRR example.
Actual mode clocks are quantized. The third row is **not an approved mode or
known panel capability**. It shows why accepting 40 Hz at half the pixel clock
does not imply acceptance of a long pause at the 80 Hz scan speed.

Likewise, the absence of spare bandwidth at the maximum rate does not by itself
rule out VRR below it. The uncertainty is handling the extra frame interval,
not necessarily transporting more active pixels. No minimum VRR rate or
low-frame-rate compensation behavior has been established.

## Feasibility judgment and next evidence

| Route | Assessment |
| --- | --- |
| Enable a desktop option or edit Gamescope Lua | Insufficient on the observed driver interface; cannot establish hardware support. |
| Add EDID metadata alone | A plausible experiment only after hardware timing support is established; currently unjustified as a solution. |
| Guarded driver changes with the existing bridge/panel configuration | Now supported by narrow-range optical evidence. Repeatability, source pacing and whole-panel behavior need validation before generalization. |
| Further bridge/panel configuration or firmware changes | Not shown necessary for the measured narrow case; may be needed for a useful wider range. Firmware functionality and signing remain separate constraints. |
| Hardware replacement | No evidence currently requires this; the optical result argues against an absolute incompatibility in the narrow case. |

The highest-value next steps are repeating the narrow optical comparison,
improving source pacing so more requested intervals are actually exercised,
and comparing timing at multiple screen locations while checking for tearing,
blanking and flicker. A second sensor would help compare scan behavior
simultaneously; the existing sensor remains useful for repeatability and
sequential location checks. No further hardware purchase is required to
continue software analysis and narrow-range test development.

An ANX7580 programming manual remains useful but is not a prerequisite for
testing the complete path. A manual or documented DP-to-DSI example, and
identification of the panel controller from public artifacts, could explain
the mechanism and guide larger timing changes. The zero control-byte readback
also warrants tracing the standard driver write path before attributing it to
receiver behavior. Supported modes, blanking limits, initialization and
brightness behavior remain open. No manufacturer correspondence is part of
this research record. The [staged bridge test plan](vrr-bridge-test-plan.md)
provides the earlier capability and experiment framework; the optical result
supersedes its initial lack of physical timing evidence.

Further timing experiments need concrete human approval under the project's
hardware-risk boundary. A credible success test compares deliberately irregular
frame delivery against actual panel updates and checks for tearing, repeats,
blanking and flicker. A changed property or an application FPS counter alone is
insufficient. Firmware experiments additionally need the recovery,
bank-selection and signing issues in [hardware-validation.md](hardware-validation.md)
and [signing.md](signing.md) resolved or explicitly accounted for.

The initial read-only assessment changed no display settings, services,
installed files, firmware or power state. Its follow-up used one 16-byte native
AUX capability read through an existing kernel device node, without arbitrary
bridge-register or MMIO access. The separately approved disposable-USB timing
experiments and restoration are documented in the visual and optical reports.
None used a vendor installer or flasher.

## Reproduction and provenance

For a preauthorized target, the capability collector is streamed into Python
with bytecode writes disabled. It creates only the specified local report:

```sh
python3 tools/collect_ssh.py USER@HOST --kind vrr --output artifacts/vrr-report.json
```

It needs an existing authenticated SSH connection, Linux Python and installed
`libdrm.so.2`; it installs nothing and needs no sudo. The baseline collector
remains available without `--kind vrr`.

The separate bounded AUX collector verifies the exact r04 EDID, discovers the
internal connector's own AUX child, verifies its device number, and opens it
read-only. It accepts no arbitrary address or write operation. If existing
permissions require it, its wrapper supports noninteractive sudo only for this
collector, without changing permissions or prompting for credentials:

```sh
python3 tools/collect_ssh.py USER@HOST --kind dpcd --sudo-read-only --output artifacts/dpcd-report.json
```

This command sends native AUX reads; it is distinct from the cached `vrr`
query. The upstream [AUX device read implementation](https://github.com/torvalds/linux/blob/v6.17/drivers/gpu/drm/display/drm_dp_aux_dev.c#L147)
dispatches to `drm_dp_dpcd_read`. The userspace request covers offsets
`0x00000..0x0000f`; kernel-level retries may occur. Raw reports remain ignored.

Regenerate the static analysis from an already-extracted public r04 input:

```sh
python3 tools/analyze_vrr.py artifacts/extracted/r04/chunks/BIOSIMG.bin
python3 -m unittest discover -s tests -v
```

- Firmware inputs and Gamescope provenance: [artifact manifest](../research/artifacts.json)
  and [upstream profile record](../third_party/gamescope/README.md).
- Static measurements and ideal timing calculation:
  [vrr-static-analysis.json](../research/reports/vrr-static-analysis.json).
- Downloaded public-source URLs and SHA-256 values:
  [vrr-sources.json](../research/vrr-sources.json). Full source downloads remain
  in ignored `artifacts/vrr/sources/`.
- Unit tests distinguish an unsupported capability from an absent property or
  failed read, and check cleanup on metadata-query failure. The collector was
  also exercised on the target; this validates querying, not VRR scanout.
