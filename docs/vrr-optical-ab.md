# Optical fixed / VRR / fixed experiment

Completed 2026-11-26 after approval of the concrete procedure below. **The
first optical comparison found visible content changes that closely followed
variable GPU timing through the complete bridge/panel path in the guarded
59–60 Hz window.** This is strong evidence at one screen location, not proof
of whole-panel variable scanout, tear-free behavior or a safe wider range.
The disabled native baseline was restored by reboot and verified.

## Physical result

One disabled-boot control and one experimental A/B/A sequence each completed
all 1,800 flips. Each 50-second continuous capture contained 5,000,000 samples,
passed packet/checksum/count and hardware-status checks, and recovered all
1,442 intended optical transitions. Neither run timed out or emitted stderr.
Both restored the previous framebuffer, native mode and VRR-off property.

| Middle-phase measurement | Fixed control | VRR requested |
| --- | --- | --- |
| Source period per vblank | 16.666–16.667 ms | 16.674–16.948 ms |
| Matched optical transitions | 720 / 720 | 720 / 720 |
| Optical minus GPU prediction, standard deviation | 8.38 us | 9.22 us |
| Distance from original native 60 Hz grid, standard deviation | 8.77 us | 3,507 us |

The VRR phase's optical residual against GPU timing had 9.23 us RMS and a
range of -12.13 to +86.67 us. Its distance from the original uninterrupted
60 Hz grid had 3.66 ms RMS and spread across almost the full +/-8.33 ms half
period. These residuals use the clock scale, offset and polarity bias fitted
only to the first fixed A; neither B nor the final A influences that fit.
The fitted offset absorbs capture start and display response, so it is not
absolute display latency. Residual scatter is not a calibrated accuracy claim.

To check local period variation as well as accumulated phase, 718 overlapping
same-polarity intervals in B were divided by their source vblank counts.
Optical and source period estimates correlated at r = 0.9967; their difference
had 6.34 us standard deviation. Of those intervals, 713 span two vblanks and
five span three. They are correlated observations, not independent trials.
Most source periods remained near the fast bound, with portions following the
requested ramp. The source still does not reproduce every requested interval.

All 359 within-phase source intervals in the final A returned to native
16.666–16.667 ms timing. Its optical residual against GPU timing had 9.87 us
standard deviation. A roughly 2.16 ms phase displacement from the *original*
60 Hz grid remained; returning to a fixed period does not undo phase accumulated
during B. This displacement is not a failed restoration.

The control had 1,484 raw crossings and ten settling groups; the experiment
had 1,450 raw crossings and four groups. The existing qualification rule
retained every intended transition, including timing outliers. Experimental
midpoint sensitivity at 0.20/0.26/0.32 V retained all edges, with B residual
standard deviations of 8.47/9.22/8.74 us. Quiet intervals of 50 and 200 us also
retained all edges. The primary 0.26 V / 100 us analysis was not replaced.
About 0.42% of experimental samples reached the ADC lower rail; none reached
the upper rail. Electrical noise and emission/response effects remain relevant.

The only new experimental kernel messages recorded `set_drr` calls for
1957/1989 and then 1956/1956. These are not register readbacks. Final reboot
checks verified the disabled override, native mode, `vrr_capable = 0`, disabled
next-boot selection, storage isolation and DPCD `0x107 = 00`. No standard AUX
write trace or control-byte read during B was collected; internal bridge
control behavior remains unresolved. No firmware was flashed.

The [anonymous result](../research/reports/optical-vrr-experiment.json) retains
capture/source hashes, integrity checks, timing statistics, sensitivity and
restoration evidence. Raw waveforms and device reports remain ignored. There
was no whole-screen visual assessment during this session. This was one
physical VRR run: repeatability, scan timing at other locations, tearing,
flicker, wider-range behavior and long-term reliability remain unestablished.
The evidence argues against an absolute ANX/panel timing incompatibility in
this narrow case; it does not establish standard Adaptive-Sync compliance or
exclude every possible buffering mechanism.

The later [controlled timing follow-up](vrr-optical-feedback.md) improved
cadence coverage in its completed portion but stopped at a submission-deadline
guard after 320 B flips. Its partial optical evidence supports this first
result; it did not meet completion/repeatability criteria. The disabled
baseline was restored, and nominal 58–60 Hz remains untested.

## Stimulus and guards

[`lab/vrr/optical_ab.c`](../lab/vrr/optical_ab.c) uses the same centered 160-pixel
gray/dark marker as the validated sensor setup. It requires the exact r04 EDID,
native mode, inactive VRR property and matching boot opt-in/capability. It
refuses DRM takeover. Control mode requires the disabled override; experiment
mode requires the existing guarded driver with the override enabled.

| Segment | Frames | Approximate duration | Content / request |
| --- | --- | --- | --- |
| Synchronization | 360 | 6 s | 2 s dark, 2 s gray, 2 s dark; VRR off |
| A | 360 | 6.05 s | Marker toggles each submitted frame; VRR off |
| B | 720 | 12.10 s | Same marker; VRR requested only in experiment mode |
| A again | 360 | 6.05 s | Marker toggles; VRR off |

There are 1,800 logged flips and 1,442 intended content transitions. Target
duration is 30.202131 seconds. All three phases use the earlier visual test's
absolute-deadline triangle cadence: target vertical totals 1960-1986, inside
the existing driver's 1957-1989 guard. Targets are submission requests, not
guarantees that every source period follows them. Actual event timestamps
and sequence steps remain the source evidence.

The driver, native 143.18 MHz pixel clock, horizontal timing, active area and
59-60 Hz experimental window are unchanged. The verified existing driver
bundle was reused; no driver rebuild or wider range was used. The earlier
[visual experiment](vrr-visual-experiment.md) explains the standard DPCD
MSA-ignore control request that can occur during the opt-in boot. The receiver
does not advertise this capability, and its response remains uncertain.

Pending flips have a two-second timeout, the synchronization/A segments have
eight-second bounds, B has a sixteen-second bound, and the phase loop has a
forty-second overall check. The SSH wrapper allows 45 seconds before SIGTERM,
then five seconds for cleanup before killing a stuck userspace process.
SIGINT, SIGTERM and SIGHUP request cleanup. Cleanup requests VRR off, restores
the previous framebuffer/native mode, and verifies both. These mechanisms do
not guarantee recovery from a kernel/GPU hang.

## Analysis and failure discrimination

[`tools/run_optical_ab.py`](../tools/run_optical_ab.py) records 50 seconds of
continuous Pico data around one source run. It verifies the staged RAM binary,
existing module hash, kernel release, lab RAM root, storage-driver isolation
and expected opt-in before starting the display test. It does not install,
select a boot slot, reboot, or turn on the driver override. Its mandatory
`--mode` is an explicit display action, including in control mode.

[`tools/analyze_optical_ab.py`](../tools/analyze_optical_ab.py) requires a
complete source sequence and restored state, validates the binary sensor
stream, and applies the existing 0.17/0.26/0.35 V thresholds with 100 us quiet
qualification. It refuses extra/missing qualified transitions rather than
silently matching around them. Raw recrossings remain in the report.

One clock scale, offset and polarity bias are fitted only to A's first 360
transitions. B and the final A are held out. Each observed transition is
compared with both the actual GPU event timing and an uninterrupted native
60 Hz grid anchored to the first A. The analysis never refits the clock in B
to conceal a cadence difference. Synthetic tests distinguish source-following
variable updates from a fixed-60-Hz buffered sink and preserve an injected
held-out 300 us delay. This does not cover every possible buffered/fixed-rate
behavior and does not automatically declare VRR support.

One sensor measures visible changes at one location. It cannot detect every
refresh that repeats the same pixels, prove whole-panel scan behavior, locate
delay inside the ANX versus panel, or establish a safe operating range.
Response asymmetry and electrical noise remain part of the uncertainty.

The first offline validation of the experimental capture rejected four- and
five-vblank holds at the atomic phase switches. The validator was revised to
retain phase-boundary holds when elapsed time and sequence count agree with
the bounded period range. Within-phase checks remain unchanged. The 67.518 ms
and 83.333 ms holds, all 1,442 transitions, thresholds and first-A-only clock
fit are retained; no experiment was rerun to obtain a passing result. New
regression tests accept a clock-consistent boundary hold and reject a corrupt
counter or oversized within-phase hold. All eight A/B analysis tests pass.

## Approved session procedure

1. Copy the reviewed optical binary into the lab's `/run` RAM filesystem.
   Run one approximately 30-second control sequence with the override off,
   capturing 50 seconds on the Pico. Check the full sequence/restoration
   before advancing; stop if the new control fails.
2. Use the verified existing USB update bundle to stage/select the inactive
   research slot with `amdgpu.ods_vrr_59_60=1`, preserving the disabled slot
   and recovery baseline. Reboot once into that slot. This opt-in boot can
   issue the standard AUX control request even before the animation.
3. As soon as SSH returns, select the verified disabled slot as the next
   boot default. Verify module identity, native mode, storage isolation and
   expected opt-in. Copy the same optical binary back into RAM and run one
   approximately 30-second A/B/A sequence with a 50-second Pico capture.
4. Verify userspace VRR-off/framebuffer restoration, save source and kernel
   logs, then reboot into the disabled slot. Verify the disabled override,
   native mode and next-boot selection again. Retain all raw reports locally.

This is two short display patterns and two lab reboots. It modifies only the
sacrificial USB and the lab's RAM; there is no BIOS, EC, bridge or panel
firmware flash. This session was explicitly approved without an observer, so
no visual-anomaly assessment is available. An observer would improve future
tests by allowing immediate reporting of whole-screen anomalies.
If SSH recovery fails, power off and remove the USB to boot the installed OS.
If the experimental boot hangs before SSH, its USB default may still point
to that slot; use the recovery menu or fix its selection before retrying.

Approval is required by [AGENTS.md](../AGENTS.md): “Anything potentially
dangerous to hardware or software MUST be confirmed by a human first.” The
USB's reversibility does not establish the panel's tolerance of unadvertised
VRR timing/control behavior. This session's concrete procedure was approved;
that approval does not authorize future expanded timing experiments.

## Local checks and reproducibility

The program built with GCC 16.2.1 and libdrm 2.4.134 using warnings as errors.
The rendering/sequence fixture passed ASan and UBSan, verified the centered
marker and framebuffer padding, counted all 1,442 transitions, and checked
every target against the guarded interior range. Experiment mode refused
`/dev/null`. All eight driver build-source hashes and the update bundle's
kernel/initramfs payload hashes match the earlier build record.

The prepared binary and build log/manifest remain in ignored `.tools/` and
`artifacts/`. The [anonymous preparation record](../research/reports/optical-ab-preparation.json)
pins their provenance at the pre-run checkpoint. It is preserved as historical
evidence; the result above supersedes its unperformed status. The wrapper's
completion message was clarified after both runs to mention a required baseline
reboot only for experiment mode; the deployed display binary was unchanged.
The new C fixture can be built in the existing Linux lab builder with:

```sh
cc -std=c11 -O2 -Wall -Wextra -Werror $(pkg-config --cflags libdrm) \
  lab/vrr/optical_ab.c -o ods-optical-ab $(pkg-config --libs libdrm)
cc -std=c11 -g -O1 -Wall -Wextra -Werror -fsanitize=address,undefined \
  $(pkg-config --cflags libdrm) tests/fixtures/optical_ab_test.c \
  -o optical-ab-test $(pkg-config --libs libdrm)
./optical-ab-test
python3 -m unittest tests.test_optical_ab
```

After the approved deployment and boot preparation, a run uses:

```sh
python3 tools/run_optical_ab.py USER@LAB --port SERIAL_PATH \
  --known-hosts artifacts/known_hosts --mode experiment \
  --driver-manifest DRIVER_BUILD.json --output-prefix artifacts/vrr/optical-ab/run
python3 tools/analyze_optical_ab.py artifacts/vrr/optical-ab/run.bin \
  artifacts/vrr/optical-ab/run.source.json --output artifacts/vrr/optical-ab/run.analysis.json
python3 tools/plot_optical_ab.py artifacts/vrr/optical-ab/run.analysis.json \
  --output artifacts/vrr/optical-ab/comparison.png
```

Use `--mode control` for the first, disabled-boot run. A successful experiment
wrapper does **not** complete restoration of the experimental boot: the final
disabled-slot reboot is still required.
