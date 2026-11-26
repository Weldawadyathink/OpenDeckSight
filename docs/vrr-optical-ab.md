# Prepared optical fixed / VRR / fixed experiment

Prepared 2026-11-26. **Built and locally tested; no optical VRR run yet.**
The [continuous fixed control](vrr-optical-measurement.md) resolved recorder
continuity and source alignment. The remaining gate for this experiment is
human approval of the concrete USB boot/display procedure below.

## What is ready

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
bundle is reused; no driver rebuild or wider range is proposed. The earlier
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

## Concrete session requiring approval

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
firmware flash. A human should be available to report/stop visible anomalies.
If SSH recovery fails, power off and remove the USB to boot the installed OS.
If the experimental boot hangs before SSH, its USB default may still point
to that slot; use the recovery menu or fix its selection before retrying.

Approval is required by [AGENTS.md](../AGENTS.md): “Anything potentially
dangerous to hardware or software MUST be confirmed by a human first.” The
USB's reversibility does not establish the panel's tolerance of unadvertised
VRR timing/control behavior. Existing approval of fixed-refresh acquisition
does not enable this experiment.

## Local checks and reproducibility

The program built with GCC 16.2.1 and libdrm 2.4.134 using warnings as errors.
The rendering/sequence fixture passed ASan and UBSan, verified the centered
marker and framebuffer padding, counted all 1,442 transitions, and checked
every target against the guarded interior range. Experiment mode refused
`/dev/null`. All eight driver build-source hashes and the update bundle's
kernel/initramfs payload hashes match the earlier build record.

The prepared binary and build log/manifest remain in ignored `.tools/` and
`artifacts/`. The [anonymous preparation record](../research/reports/optical-ab-preparation.json)
pins their provenance and records that the optical VRR test is unperformed.
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
```

Use `--mode control` for the first, disabled-boot run. A successful experiment
wrapper does **not** complete restoration of the experimental boot: the final
disabled-slot reboot is still required.
