# Controlled timing repeat before expanding the VRR range

Prepared 2026-11-26. **Built and tested locally; not deployed or run on the
display.** The [first optical result](vrr-optical-ab.md) supports continuing,
but a repeat with better source timing control should precede range expansion.
No device was contacted while preparing this checkpoint.

## What the original sweep actually exercised

The [source scheduling review](../research/reports/vrr-source-pacing-review.json)
retains the original source-report hash and reproducible measurements. Of 719
within-B source intervals, 374 stayed at 16.674–16.676 ms, near the fastest
guarded bound. Three content changes spanned two vblanks. The animation kept
its original absolute schedule after those holds; long fast-bound stretches
followed while that schedule caught up with the completed flips. This is
evidence for changing the scheduler, not a complete diagnosis of kernel or
hardware timing behavior.

The optically measured timing remains convincing: these were actual visible
updates, with all intended changes recovered. However, a larger requested
range would be difficult to evaluate if the source still failed to exercise
the requested cadence reliably.

## Prepared source change

[`optical_feedback.c`](../lab/vrr/optical_feedback.c) selects a separate
compile-time scheduling policy in the shared A/B program. It uses the same
driver, native mode, exact EDID checks, 160-pixel marker, frame counts,
timeouts, cleanup and 59–60 Hz guard. It has no range-setting option.
The original triangle policy remains available as `optical-ab-v1`.

The new `optical-feedback-v1` policy uses an immediate first flip to seed B,
then schedules each submission from the previous completed GPU event. It
alternates 60-frame blocks at totals 1964 and 1980: approximately 59.76 and
59.27 Hz, with target periods separated by 136.33 us. There are six blocks of
each target, 720 B flips total. The fixed A phases and the entire disabled-boot
control submit immediately after each event, giving native fixed timing.
The fixed control therefore checks the sensor and baseline cadence; it does
not replay B's delayed submission schedule with VRR disabled.

Submissions precede the desired event by a fixed 350 us. In the original
variable portions with one vblank per change, submission-to-event delay had
a 352.93 us median and 296.98–449.12 us range. This empirical starting point
is neither isolated driver latency nor a guarantee that targets will be met.
It is not adjusted from optical data or fitted during the run. If userspace
arrives more than 150 us late, the program stops and restores the display
instead of submitting catch-up frames. The driver still bounds refreshes even
when a frame is late. Timeouts cannot guarantee recovery from a kernel hang.

The log records callback receipt times in addition to GPU event and submission
times. The analyzer verifies every deadline against the preceding event,
the target pattern, lateness, delivery count and the unchanged source range.
It reports all twelve block distributions. All optical edges remain included;
the first fixed A alone calibrates the clock and polarity bias. A/B transition
holds remain explicit, as in the previous analysis.

## Concrete session awaiting approval

1. Copy the reviewed feedback binary into the disposable lab's `/run` RAM
   filesystem. Verify the existing disabled driver, native mode and storage
   isolation. Run one approximately 30-second fixed control with a 50-second
   continuous Pico capture. Stop if capture, timing or restoration checks fail.
2. Verify and select the existing experimental USB slot, then reboot into its
   unchanged 59–60 Hz override. This boot can make the previously documented
   standard MSA-ignore AUX request. Select the disabled slot as the next boot
   default immediately after return, and verify the payload and native mode.
3. Copy the same binary back into RAM. Run one approximately 30-second A/B/A
   sequence with a 50-second capture and analyze it. If the checks below pass,
   run one repeat with identical settings and another 50-second capture.
4. Verify per-run framebuffer/native-mode/VRR-off restoration, then reboot to
   the disabled slot and verify the baseline and next-boot selection. On any
   failed check, skip remaining patterns and restore the disabled baseline.

This is at most three short patterns and two USB-lab reboots, with no driver
rebuild, range expansion or firmware flash. No sensor movement is required.
An observer can report whole-screen anomalies that this single sensor cannot
detect. Without an observer, no claim about tearing or flicker will follow.
If software recovery fails, manual power-off or recovery-boot intervention
may be necessary.

Progression criteria are chosen before the physical run: complete loss-free
capture, all 1,442 transitions recovered, source intervals inside existing
bounds, verified restoration, and no new unexpected kernel errors. For B,
require optical-minus-source standard deviation below 25 us and maximum
absolute residual below 200 us. Require at least five of six paired block
medians to differ by 80 us or more in the requested direction, and the pooled
slow-minus-fast median to differ by at least 80 us. Report every block and
hold even on failure. These are engineering progression criteria, not panel
safety certification or a statistical significance test. Passing them twice
would justify preparing the next small range experiment; it does not authorize
that experiment.

Approval is required by [AGENTS.md](../AGENTS.md): “Do not stop/start services,
install/copy files on the Deck, change settings, access MMIO, run a flasher,
or reboot without explicit human approval for the concrete action.” The prior
approval covered the completed optical session; this is a new display program
and new session.

## Candidate first expansion: nominal 58–60 Hz

Keep the maximum rate and 143.18 MHz pixel clock unchanged and investigate a
small downward extension only after the controlled repeat. Hash-pinned AMD
arithmetic was compiled and checked locally for both candidate bounds:

| Lower bound | Maximum total | Extra lines over native | Front porch if stretched | Maximum period |
| --- | --- | --- | --- | --- |
| Existing nominal 59 Hz | 1989 | 33 | 41 lines | 16.94776 ms |
| Candidate nominal 58 Hz | 2023 | 67 | 75 lines | 17.23746 ms |

The candidate adds 34 lines, or 289.71 us, beyond the current maximum interval.
Its quantized lower rate is about 58.013 Hz. These are source timing
calculations, not verified bridge/DSI timing limits. The retained
[controller-family datasheet](vrr-icna3512.md) does not specify DeckSight's
allowed blanking extension. A working fixed 40–80 Hz profile supplies no such
limit either. A later 58–60 Hz test needs a separately built, reviewed guard
and concrete human approval. No wider-range binary was created or installed
at this checkpoint.

## Validation and reproduction

The [preparation record](../research/reports/optical-feedback-preparation.json)
pins source/binary/build hashes. GCC 16.2.1 and libdrm 2.4.134 compiled the
program with warnings as errors. The feedback scheduling fixture and original
render/sequence fixture passed ASan and UBSan; experiment mode refused
`/dev/null`. Ten Python tests cover scheduling, stale deadlines, lateness,
capture/delivery integrity and the existing optical hypotheses. Reanalysis of
both original physical recordings retained all 1,442 edges and identical
middle-phase residual statistics. No optical thresholds or clock fitting
rules were changed.

```sh
python3 -B -m unittest tests.test_optical_ab
python3 -B tools/analyze_vrr_pacing.py artifacts/vrr/optical-ab/experiment-01.source.json \
  --output artifacts/vrr/optical-feedback/source-pacing.json
cc -std=c11 -O2 -Wall -Wextra -Werror $(pkg-config --cflags libdrm) \
  lab/vrr/optical_feedback.c -o ods-optical-feedback $(pkg-config --libs libdrm)
```

After explicit approval and boot/deployment preparation, the existing capture
wrapper accepts the new local binary using
`--binary .tools/optical-feedback/ods-optical-feedback`. Its remote RAM filename
remains `/run/ods-optical-ab`; the wrapper verifies that file's hash. Use unique
output prefixes, retain raw reports in `artifacts/`, and analyze with
`tools/analyze_optical_ab.py`. The original physical binary is retained locally;
commit `f1f02c3` preserves its exact build sources.
