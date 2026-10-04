# Bounded visual VRR experiment

The diagnostic AMD driver, visual stimulus and USB update bundle were built on
2026-10-04. **One approved physical A/B/A experiment completed: GPU event
intervals varied during B and returned to fixed timing afterward. No visual
anomalies were reported. Bridge/panel VRR remains unconfirmed.** The disabled
baseline was restored by reboot and verified. The ready bundle defaults to
`amdgpu.ods_vrr_59_60=0`; installing it never starts a test.

## Physical experiment result

The experiment used the exact prepared module and stimulus, matching r04 EDID
and native mode, and the explicit boot opt-in. The driver exposed
`vrr_capable = 1`. The sequence completed all 1,800 flips without timeout or
stderr, then verified restoration of the prior framebuffer, native mode and
VRR-off property.

| Phase | Completed frames | Analyzed intervals | Reported period per vblank |
| --- | --- | --- | --- |
| A, fixed | 720 | 716 | 16.666–16.667 ms |
| B, VRR requested | 720 | 716 | 16.674–16.948 ms |
| A again, fixed | 360 | 356 | 16.666–16.667 ms |

All analyzed fixed-phase periods were within 2 microseconds of native timing.
All analyzed B periods were outside that tolerance and inside the candidate
variable window with the same tolerance. B contained 713 single-vblank
intervals and three two-vblank intervals; the latter are averages of two periods.
The single-vblank intervals had 55 distinct values at the reported microsecond
resolution, with a median of 16.675 ms. Most stayed near the fastest variable
bound: this is evidence of changed source timing, not faithful tracking of
every application target. No analyzed submission was over 500 microseconds late.

The only two new kernel messages recorded calls to `set_drr` with totals
1957/1989 and then 1956/1956. These are call-path observations, not register
readback. The observer reported that B appeared just as smooth as A, with no
tearing, flicker or other visual anomaly during the sequence. This qualitative
observation cannot resolve timing differences over such a narrow range.

DPCD `0x107` read **`00` before and after the animation**, as it had immediately
after the experimental boot. The expected MSA-ignore bit was not reflected in
those sampled reads. No AUX write/acknowledgement trace or read during B was
collected, so the exact write behavior and receiver acceptance remain open.
Do not infer that the bridge accepted the control request, nor that it is
incapable of passing variable timing.

After the run, a new boot into the disabled baseline verified the payload
hashes, native mode, `vrr_capable = 0`, disabled override and control byte `00`.
The next boot also selects the disabled baseline. Internal storage remained
unbound and unmounted, with no swap.

This removes the source-generation prerequisite far enough to proceed to
optical measurement. The next decisive test is a synchronized photodiode capture
of visible frame transitions against a controlled irregular submission sequence,
with a fixed-refresh control. Instrumenting the standard AUX control path would
also clarify the zero readback. This single short run establishes neither a
safe operating range nor end-to-end VRR support.
[Anonymous experiment report](../research/reports/vrr-visual-experiment.json)

## Driver boundary

The [patch](../lab/vrr/0001-ods-vrr-59-60.patch) targets OGC source commit
`151eb3adafae8820f349a4454c1f1e8d5fc991a4`. It rebuilds the AMD module against
the prepared `7.2.3-ogc3.1.fc44.x86_64` development package, retaining the existing
kernel and other modules. All 6,670 comparable include headers matched the source
archive; GCC `16.2.1-2` matches the kernel's compiler identification. Source and
development-package hashes are in [the build input record](../research/vrr-driver-build.json).
This is not a byte-for-byte reproduction of the distribution kernel. Its config
has module symbol versioning disabled. The diagnostic module is unsigned and
lacks module BTF because the distribution's full `vmlinux` was unavailable.
The virtual and physical module-load checks therefore matter independently.

The patch:

- Requires the read-only module option `ods_vrr_59_60=1`, internal eDP and all
  256 bytes of the public r04 EDID. It does not enable passive/desktop VRR.
- Requires the exact native mode before flagging a stream for the experiment.
  Pixel clock, active dimensions, sync boundaries and scan flags stay fixed.
- Supplies consistent 59/60 Hz range fields, bypassing both discovery and the
  independent minimum-range heuristic only for the matched stream.
- Skips LFC, sticky fixed-refresh fallback and flip-interval workarounds on that
  stream. Late frames may still miss presentation deadlines; this is diagnostic
  behavior, not a proposed production FreeSync policy.
- At `dc_stream_adjust_vmin_vmax()`, accepts only native totals 1956/1956 or the
  experimental pair 1957/1989. Mid-frame totals and counter halt are rejected.
  Other pairs are rejected before this path programs hardware.
- Logs rejected/deferred changes and calls to the timing-generator programming
  function. “set_drr invoked” is not register-readback or optical proof.

Ordinary streams retain the original minimum-range policy and callbacks.

## The experimental boot includes a standard AUX control write

The capability override itself changes software discovery. However, AMD's
normal `enable_stream_features()` reads DPCD `DP_DOWNSPREAD_CTRL` at `0x107`
and sets bit 7, `IGNORE_MSA_TIMING_PARAM`, when this stream is enabled. It preserves
the other bits and writes the byte if changed. This is a standard DisplayPort
control request, not a vendor flash command, but this receiver does not advertise
the corresponding capability. Acceptance and behavior are unknown.

Consequently, **approval must precede the opt-in boot**, not merely the animation.
The usual FreeSync source flag is retained from stream initialization, including
the fixed-refresh A phases. Disabling the userspace VRR property restores native
timing but does not clear this stream-configuration flag. Rebooting into the
disabled baseline is part of the complete restoration procedure.
[Pinned stream-enable implementation](https://github.com/OpenGamingCollective/linux/blob/151eb3adafae8820f349a4454c1f1e8d5fc991a4/drivers/gpu/drm/amd/display/dc/link/link_dpms.c),
[DPCD definitions](https://github.com/OpenGamingCollective/linux/blob/151eb3adafae8820f349a4454c1f1e8d5fc991a4/include/drm/display/drm_dp.h)

The separate [control reader](../opendecksight/msa_control.py) opens only the
identified internal AUX device read-only and requests one byte at `0x107`.
It exposes no write or arbitrary-address interface. The original receiver-capability
collector remains limited to its original 16 bytes.

## Visual sequence and interpretation

The [visual program](../lab/vrr/visual_ab.c) rotates a moving gray bar, rate label
and frame-ID markers into the panel's portrait framebuffer. It uses three
buffers, renders ahead, and schedules submissions with monotonic absolute
deadlines. “TARGET FPS” is the requested content cadence; “VRR REQUESTED” does
not assert that the bridge or panel follows it.

| Phase | Length | Requested behavior |
| --- | --- | --- |
| A | 720 frames, about 12.10 s | Fixed native 60.000335 Hz, irregular application cadence |
| B | 720 frames, about 12.10 s | VRR request, same application sequence |
| A again | 360 frames, about 6.05 s | Fixed native timing and first half of the same sequence |

The GPU window is approximately **59.004855–59.969676 Hz** (1957–1989 lines).
The animation sweeps an interior target cadence of approximately
59.094–59.878 FPS, leaving a small margin from the endpoints. A narrow range is
not an established safe panel range. No wider sweep is implemented.

Look for blanking, corruption, tearing, brightness changes and periodic motion
hitches. A clear failure is useful evidence; smooth motion is not proof of VRR.
The event report compares kernel timing against the fixed cadence, separately
from submission deadlines. Optical measurements remain necessary to determine
whether the visible panel updates follow the source rather than fixed-rate
buffering or another behavior. No automatic “VRR works” verdict is produced.

## Execution and recovery after concrete human approval

1. Keep the verified disabled research slot and recovery baseline. Install the
   same bundle to the inactive slot with the sole experimental boot argument
   `amdgpu.ods_vrr_59_60=1`. Reboot with a human watching the Deck.
2. As soon as SSH returns, select the disabled slot as the next boot default.
   Verify the new module, opt-in, exact EDID/native mode and storage isolation.
   Record whether the one-byte bridge control readback reflects the request;
   this alone is not proof of working variable timing. Stop if identity, native
   mode or required driver state does not match the prepared experiment.
3. Run the approximately 30.25-second A/B/A sequence once. Each pending flip has
   a two-second timeout; each phase has a 16-second wall-clock bound. The SSH
   wrapper allows 45 seconds, then sends SIGTERM and allows five seconds for
   cleanup before terminating a stuck userspace process.
4. The program requests VRR off, restores the original framebuffer/native mode
   and checks the result. Save GPU events and kernel logs. Reboot into the
   disabled slot and verify that the override and bridge control bit are clear.

If the screen becomes abnormal, stop the test immediately. Software timers do
not guarantee recovery from a kernel/GPU hang. If SSH recovery fails, power off
and remove the lab USB to boot the installed OS. If a hang occurs before SSH
becomes available, the USB may still select the
experimental slot; use its recovery entry or correct its configuration before
booting it again. No firmware flash or installed-system modification is involved.

These steps require approval because the receiver/panel response to the requested
control bit and timings remains unknown. This follows the user's hardware-risk
boundary and [AGENTS.md](../AGENTS.md), which requires human confirmation for
potentially dangerous actions. Merely having a reversible USB does not establish
display-hardware tolerance.

## Build and check

First build the normal lab builder/image as described in [USB lab](usb-lab.md).
Then:

```sh
python3 -B tools/test_vrr_patch.py
python3 -B tools/build_vrr_lab.py
```

The build uses pinned downloads, verifies source anchors, compiles the module,
strips debug data, and builds/checks the renderer. It produces
`artifacts/vrr/visual-ab/opendecksight-vrr-update.tar`. `--reuse-build` only
repackages binaries when their recorded source and payload hashes still match.
It never contacts a device or writes a physical USB.

On the disabled lab, the default remote command performs preflight KMS queries
and the bounded AUX control reads, without applying a display change:

```sh
python3 -B tools/run_vrr_visual.py root@<lab-address> \
  --known-hosts artifacts/usb-lab/known_hosts \
  --output artifacts/vrr/visual-check.json
```

`--mode control` runs only the fixed-refresh A sequence. `--mode experiment`
requires the matching rebuilt module/binary, explicit boot opt-in and exposed
VRR capability before applying the bounded sequence. It is for the separately
approved and observed session above. Raw device reports remain ignored.

Local tests rejected all 256 single-byte EDID mutations, all 12 changed native
timing fields, and disallowed total pairs in a 2,601-pair grid. The extracted
patched functions retained variable totals across 200 late-frame cycles,
preserved the native off state, rejected a widened narrow override, and kept
ordinary streams on their normal path. The renderer passed address/undefined
behavior sanitizers. The QEMU candidate boot loaded the module with the override
off, verified payload hashes, refused the wrong display, and preserved the
simulated internal disk. These tests establish software properties, not physical
VRR support.

The disabled driver subsequently booted on physical hardware with its payload
hash verified. The 720-frame fixed-refresh visual control completed and restored
the original framebuffer/mode. Across 716 analyzed intervals, 710 advanced one
vblank and six advanced two; the period per vblank stayed at 16.666–16.667 ms.
No submission was over 500 microseconds late, and no new kernel message appeared.
The MSA-ignore control stayed clear. This validates the rendering/pacing and
restoration path on the rebuilt driver, without exercising its override.
[Anonymous baseline report](../research/reports/vrr-visual-baseline.json)
