# Optical measurement for end-to-end VRR experiments

Research date: 2026-10-03. This is an instrument and experiment design, not a
record of successful VRR operation. No Deck or measurement-board configuration
was changed for this work.

## Treat the bridge as an unknown, then test observable behavior

Manufacturer confirmation is useful but is not a prerequisite for experimental
work. Leave ANX7580 variable-timing behavior explicitly unknown while preparing
a controlled source-to-light test. Preserve the measured facts separately:
the internal receiver does not advertise the MSA timing capability and Linux
reports `vrr_capable = 0`.

Success would establish end-to-end behavior for the tested configuration and
range, even if the bridge's internal mechanism remains unexplained. A failure
would not identify whether the source, bridge, panel or configuration caused
it. Only investigate the intermediate electrical interfaces when they are
needed to discriminate between remaining explanations. This approach does not
relax the project's requirement to explain firmware transformations or permit
claims about undocumented vendor command meanings.

Build a trustworthy optical measurement path first, then prepare the opt-in
GPU timing experiment described in the [bridge test plan](vrr-bridge-test-plan.md).
Do not widen an experimental timing range just to make it easier for a camera
to resolve. Ordinary application frame pacing alone does not enable VRR.

## Camera versus sensor

| Instrument | Useful role | Main limitation |
| --- | --- | --- |
| iPhone 14 Pro rear camera at 1080p/240 fps | Capture frame numbers, gross repeats, blanking, tearing and visible instability | Nominal whole-frame interval is 4.167 ms; exposure, rolling shutter and encoding complicate timing |
| RP2040 or suitable ESP32-family board plus amplified photodiode | Record actual local luminance transitions with tens of microseconds sample spacing | Requires a characterized analog circuit, reliable capture and separation of content changes from OLED modulation |
| Two optical channels plus camera | Compare content arrival at separated scan positions and corroborate visible whole-screen behavior | Still cannot isolate bridge from panel without additional evidence |

Apple specifies 1080p slow motion at 120 or 240 fps for the rear camera; the
front camera is limited to 120 fps. These are capture specifications, not
guarantees of measurement accuracy.
[iPhone 14 Pro specifications](https://support.apple.com/en-us/111849)

For the proposed narrow experiment, the interval difference between 59 and
60 Hz is `1/59 - 1/60 = 282.486 microseconds`. Simple 240-fps frame counting is
too coarse to resolve each such interval reliably. Long captures can reveal
average differences, and calibrated rolling-shutter analysis can extract
additional timing information, but neither should be the initial proof of
per-frame VRR. Faster shutter speed reduces exposure blur; it does not increase
the number of independent captured frames.

Start camera work with native 1080p/240-fps slow motion. Mount the camera,
maintain a clear view of test markers and frame numbers, and preserve the
original file rather than a rendered slow-motion or interpolated export.
Inspect capture timestamps, retiming metadata and duplicate/dropped frames.
Treat banding cautiously: the display's brightness modulation and the camera's
readout can interact even on a normally working fixed-refresh display.

If manual control is needed, Apple's Final Cut Camera provides shutter, ISO,
focus and white-balance controls; Apple says up to 240 fps is available on
certain devices. Verify the actual device/lens/format combination before using
it. The built-in camera is enough to begin visual documentation; no paid app
is a prerequisite.
[Final Cut Camera overview](https://support.apple.com/en-euro/guide/final-cut-camera/dev154067693/ios)

## Preferred timing instrument

Use a photodiode and analog front end that turns its current into a buffered
voltage, connected to the board's ADC. Aim initially for **20–50 ksample/s per
channel** using hardware-paced capture. This gives 50–20 microseconds between
samples, not a promise of equal timing accuracy. Calibrate the complete path
and its uncertainty before interpreting a 282-microsecond difference.

**Prefer an RP2040 board with exposed ADC inputs and USB for the first
implementation.** Its ADC supports hardware-paced conversion, a FIFO and DMA;
the chip has native USB. The documented maximum ADC rate is 500 ksample/s
aggregate, comfortably above this experiment's initial target. These are
available hardware features, not achieved end-to-end capture performance.
Use the Pico C/C++ SDK for acquisition. Exact board pinout and analog reference
must be checked before choosing wiring.
[Raspberry Pi hardware APIs](https://www.raspberrypi.com/documentation/pico-sdk/hardware.html#hardware_adc)
and [RP2040 hardware design guide](https://datasheets.raspberrypi.com/rp2040/hardware-design-with-rp2040.pdf)

ESP32-family alternatives remain viable. Identify the exact chip, ADC limits,
usable pins, memory and USB interface first; the ESP8266 is not the preferred
starting point when an RP2040 is available. Espressif documents continuous ADC
sampling with DMA on the S3. Multiple channels share the conversion stream;
the aggregate configured rate must allow the intended per-channel rate.
Handle reported capture-pool overflows as invalid data, not as long display
frames.
[ESP-IDF ADC continuous mode](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/adc/adc_continuous.html)

An **OPT101-class integrated photodiode/amplifier** is a plausible simple
front-end candidate: TI specifies an integrated 1-megohm feedback amplifier
and nominal 14-kHz bandwidth. A discrete photodiode with a correctly designed
transimpedance amplifier is another option. Board-level filtering, saturation,
output loading and supply headroom must be checked; an arbitrary module sold
as a light sensor is not equivalent. Select the final circuit only after the
microcontroller board and available parts are known.
[TI OPT101](https://www.ti.com/product/OPT101)

The measurement fixture is entirely optical at the Deck: place the sensor over
a small dedicated marker, with an opaque shroud to reduce ambient light. No
electrical connection to the Deck's display cable, bridge or motherboard is
needed. Power and capture the sensor through a separate development host. Keep
the amplifier output within the selected ADC's valid voltage range; a
5-V sensor module is not automatically safe for a 3.3-V microcontroller input.

Retain sampled waveforms for the first experiments rather than recording only
threshold crossings. This reveals saturation, amplifier settling, OLED
modulation and noise. Choose analog bandwidth/anti-alias filtering after
characterizing the signal. A comparator and hardware edge-capture peripheral
could later reduce data volume once the relevant transitions are understood.

USB/serial access is sufficient for control and data transfer. Timing must come
from sample indices and the board's acquisition clock, not host receipt times
or serial line timestamps. Use buffered binary blocks with sequence numbers,
sample counts, acquisition settings and loss indicators, or short captures
stored in RAM then transferred. At 20 ksample/s, one packed 16-bit channel
already produces 40 kB/s; 115200-baud 8N1 serial cannot continuously carry that.
Raw native ADC records can be larger still. Transport choice depends on the
board and must be verified rather than assumed.

## Measurement sequence and acceptance criteria

1. **Validate the instrument independently.** Use an LED with known pulse
   timing to check rise/fall response, interval recovery and capture losses.
   If the same microcontroller clocks both LED and ADC, this verifies their
   relative operation but does not independently calibrate absolute clock accuracy.
2. **Characterize the panel at its existing fixed mode.** Record a static dark
   patch, a static lit patch, and a changing marker. Identify luminance
   modulation that exists without new content. Do not call every optical
   pulse a refresh; identical repeated frames can produce no content edge.
3. **Use an identifiable test sequence.** Change a small marker on each
   intended new frame, include visible frame IDs and a synchronization
   preamble, and record submission/presentation events. Measure both rising
   and falling marker transitions; alternating black/white has one rising
   edge only every two frames. Correlate the full sequence to detect repeats,
   losses and ambiguous matches. Keep most of the scene constant to limit
   luminance-dependent confounders.
4. **Run fixed-refresh and experimental controls.** Use deliberately irregular
   frame intervals and the same content sequence. Establish whether optical
   updates remain tied to a fixed scan cadence, skip updates, or follow the
   changing intervals. Compare source and sensor clocks with a bounded offset
   and drift model; do not adjust each frame independently to force agreement.
5. **Check spatial consistency.** One diode is enough to develop the capture
   path. Add a second at a different position along the measured native scan
   direction for stronger evidence. DeckSight is natively portrait, so that
   axis should not be assumed to be top-to-bottom in the landscape desktop.
   Account for channel multiplexing delay. Use the camera to look for tearing
   and whole-screen faults beyond the two measured positions.

Success requires validated source timing, optical intervals that track the
irregular sequence beyond the instrument's uncertainty, and evidence against
fixed-cadence frame dropping or asynchronous tearing as alternative causes.
An average FPS match, moving camera bands or a changed kernel property is
insufficient. Two sensors do not prove every pixel is correct, and local
luminance alone does not expose the bridge's electrical protocol.

Sensor calibration and host-side analysis can be developed independently of
the experimental kernel. No runtime pattern or timing experiment has been
launched on the Deck here. Device changes and experimental timing remain
subject to approval of a concrete procedure under [AGENTS.md](../AGENTS.md).

## Pico W / OPT101 bring-up checkpoint, 2026-11-26

The selected prototype uses an OPT101P with its internal feedback resistor:

| Pico connection | Physical pin | OPT101 connection |
| --- | --- | --- |
| 3V3 OUT | 36 | Pin 1 |
| AGND | 33 | Pins 3 and 8 |
| GP26 / ADC0 | 31 | Pin 5, also jumpered to pin 4 |
| GP27 / ADC1, optional second sensor | 32 | Second sensor pin 5, jumpered to its pin 4 |

Place one 100 nF ceramic capacitor between pins 1 and 3 at each sensor.
Leave pins 2, 6 and 7 open. Viewed from the clear top with the pin-1 dot
upper left, the left pins are 1, 2, 3, 4 and the right pins are 8, 7, 6, 5.
Supply the sensors from 3.3 V, not VBUS or VSYS. Keep separate sensor outputs
on separate ADC inputs. These are the intended connections, not a remotely
verified inspection of the physical wiring.

Sources: [TI OPT101 pinout and Figure 21](https://www.ti.com/lit/gpn/OPT101),
[Pico W pinout](https://datasheets.raspberrypi.com/picow/PicoW-A4-Pinout.pdf).

The onboard Pico W LED is near the USB connector, opposite the antenna end.
It is controlled through the CYW43 wireless chip. It can provide light/dark
steps for hardware-paced response-shape measurements, but its command times
are not an assumed precise timing reference. An optional external LED can use GP15 (physical
pin 20), a series 1 kOhm resistor and GND (physical pin 18). The ordinary
non-wireless Pico instead has its onboard LED directly on GP25.
[Board layouts](https://www.raspberrypi.com/documentation/microcontrollers/pico-series.html#board-layouts).

The initial diagnostic uses official Pico W MicroPython v1.29.0 and
[`tools/pico_optical_probe.py`](../tools/pico_optical_probe.py), sent to RAM:

```sh
mpremote connect "$PICO_PORT" run tools/pico_optical_probe.py > artifacts/pico-probe.jsonl
```

Set `PICO_PORT` to the identified Pico USB serial port. Run only with
authorization to control that instrument. The script drives the board LED,
reads GP26 and GP27, records raw scaled ADC samples in sixteen LED-state
windows, then turns the LED off in a `finally` block. It makes no network
connection, changes no clocks and installs no boot script. A raw `read_u16`
value represents a scaled 12-bit conversion, not 16-bit ADC precision.
[MicroPython RP2 reference](https://docs.micropython.org/en/v1.29.0/rp2/quickref.html).

The [anonymous bring-up report](../research/reports/pico-optical-bringup.json)
records a complete initial run. At GP26, the nominal mean was 57.57 mV with
the LED off and 57.83 mV with it on: a difference of only 0.26 mV, smaller
than one nominal 12-bit ADC step and the 1.4-1.7 mV sample noise. This does
not establish an optical response; supply coupling can also correlate with
LED commands. Programming, REPL communication, ADC acquisition and LED
command/readback worked. Neither correct sensor wiring nor optical emission
and alignment are proven by those facts. GP27 was observed as an auxiliary
input, not treated as a second sensor.

Next, establish an unmistakable change by pointing the sensor's clear
sensing face directly at the LED, then comparing covered and brightly lit
conditions. Check the physical pinout if there is still no response. Only
after this check should capture progress to hardware-paced ADC/FIFO/DMA
and edge characterization. One working sensor is sufficient to begin local
content-arrival measurements and VRR implementation experiments. A second
sensor strengthens spatial consistency and tearing checks; one trace alone
does not prove correct whole-panel VRR.

### Successful optical response after repositioning

A subsequent run of the same probe, after repositioning the sensor toward
the onboard LED, established a strong functional response on GP26. Across
eight windows of each state (2,048 samples per state), the nominal mean was
31.12 mV with the LED off and 1.71260 V with it on: a 1.68148 V difference.
Every on-window was clearly separated from every off-window. Within-state
sample standard deviations were 2.57 mV off and 27.64 mV on. No ADC-rail hits
were observed. The [successful response report](../research/reports/pico-optical-response.json)
preserves the statistics, source/capture hashes and limitations; the earlier
unsuccessful placement remains in the initial report.

This confirms a functional sensor-to-ADC path and removes the initial
light-detection blocker. It does not independently verify every connection,
the bypass capacitor, amplifier linearity, or temporal response. GP27 showed
coupling as an auxiliary unconnected input and must not be interpreted as a
second working sensor. The next instrument work is hardware-paced acquisition
and edge characterization; one validated optical channel is enough to begin.

### Onboard LED with hardware-paced capture: no extra LED required to start

On 2026-11-26, [`tools/pico_optical_dma.py`](../tools/pico_optical_dma.py)
successfully captured GP26 at a nominal 100,000 samples/s using the RP2040
ADC divider, FIFO and a DREQ-paced DMA channel. MicroPython schedules the
onboard LED commands and transfers the completed buffers; it does not time
individual ADC conversions. This is an initial short-capture implementation,
not the longer-running instrument originally proposed with the C/C++ SDK.

Four 16,000-sample recordings produced 64,000 samples and 52 optical
transitions. All chunks, sample counts, CRCs, conversion-error bits and
DMA/FIFO status checks passed. The measured capture loop durations were
160.038-160.050 ms for nominal 160 ms buffers. That compares clocks derived
from the same board reference and includes software start/stop overhead; it
does not independently calibrate absolute sample timing.

The combined LED/sensor/ADC transition widths were approximately 20-30 us
(10-90% of each local step, about 24 us median), with a 10 us sample period.
Linear interpolation gives more digits in the report, not equivalent
accuracy. Sampling brackets omit amplitude noise, baseline estimation and
clock uncertainty. Two isolated dark-level readings reached ADC code zero;
no bright-level reading reached the upper ADC rail. The threshold crossings
were well above the dark noise floor. These observations characterize this
light level and geometry, not all panel brightness levels or pure sensor
latency.

Onboard LED calls took 294-567 us. Their latency does not prevent measuring
the *shape of the observed optical edge*: the ADC/DMA runs independently,
and both thresholds come from that same waveform. Command timestamps only
locate broad search windows. Do not equate requested LED periods to a known
optical period or use these calls as an electrical-edge reference. This
distinction removes an external LED purchase as a prerequisite for starting
panel measurements. A direct GPIO-driven LED remains useful later if a
known electrical stimulus or tighter timing calibration becomes necessary.

[`tools/analyze_pico_optical_dma.py`](../tools/analyze_pico_optical_dma.py)
rejects incomplete/corrupt recordings and hardware error flags before
estimating rising/falling widths. Seven focused tests cover corrupted data,
hardware faults, missing optical response, and recovery of a synthetic
80 us edge independently of LED-command duration. The
[anonymous timing report](../research/reports/pico-onboard-led-timing.json)
preserves the measured results, code/capture hashes and limits. Raw buffers
remain ignored under `artifacts/`. The probe turns the LED off and stops
ADC/DMA capture on exit; it installs no startup script.

Next: develop longer captures, characterize fixed-refresh panel waveforms,
then compare identifiable content sequences against source presentation
timing. A second optical channel is useful corroboration, not a prerequisite
for that first stage. No Deck experiment was performed in this checkpoint.

### Fixed-refresh panel target and passive snapshots

[`lab/vrr/optical_fixed.c`](../lab/vrr/optical_fixed.c) supplies a centered
160-by-160-pixel gray marker with a thin outer positioning border. Centering
avoids ambiguity from the panel's native portrait orientation. It reuses the
exact r04 EDID, native mode and `vrr_capable=0` guards from the fixed-refresh
control. It sends no VRR, AUX, firmware or altered timing request. Its active
modes require an authorized lab session:

- `--check /dev/dri/cardN`: cached preflight only, with no frame submission.
- `--position /dev/dri/cardN`: steady gray marker for up to 600 seconds, with
  SIGINT/SIGTERM/SIGHUP cleanup and restoration of the prior framebuffer/mode.
- `--measure /dev/dri/cardN`: 1,080 native page flips, nominally 18 seconds:
  2 s dark, 2 s gray, 2 s dark, 2 s of changes every two frames, 8 s of
  changes every frame, and 2 s dark. A timestamped record identifies each
  flip and marker state. These are intended source events, not panel light
  measurements; late/missing event intervals must be checked in the result.
- `--preview`: landscape PPM rendering without opening a DRM device.

The local rendering/sequence fixture passed address/undefined-behavior
sanitizers, including the marker area, framebuffer pitch padding and phase
boundaries. The shared native-mode guard also passed its existing 16
rejection cases. An initial physical `--check` and positioning launch
accepted the exact fixed native mode. Panel waveform acquisition and
measurement-mode completion remain unverified at this checkpoint.

Use the clear sensing face over the solid center square, keeping metal leads
off the display glass; a soft opaque shroud can reduce ambient light. Keep
the Pico attached to the separate capture host. The marker begins at gray
level 128, not full white, but signal headroom must still be measured before
interpreting edge timing. Use a more suitable light level or aperture if
the sensor saturates.

Passive snapshots use the same ADC/FIFO/DMA path with the onboard LED held
off. Set the explicit option in the same `mpremote` interpreter session:

```sh
mpremote connect "$PICO_PORT" exec 'OPTICAL_LED_STIMULUS=False' \
  run tools/pico_optical_dma.py > artifacts/panel-snapshot.jsonl
```

This records four separate 160 ms snapshots at nominal 100 ksample/s, with
transfer gaps between captures. It is useful for signal level and static
brightness-modulation checks, not a continuous 18-second recording.
`read_captures()` in the host analyzer validates its chunks, CRCs and status
flags; the LED-step summary deliberately rejects recordings with no LED
commands. Before sensor placement, the passive option completed 64,000
samples with empty LED-command lists and no reported capture errors. Longer
continuous acquisition and panel/source alignment are still required for
the eventual VRR comparison.

### First optical fixed-refresh panel measurement, 2026-11-26

One OPT101P over the center marker produced a clear signal: the steady gray
patch averaged approximately 0.517 V, while the dark patch was around
0.029 V, using nominal ADC reference scaling. Gray-only snapshots had no
ADC-rail hits. Static gray traces contain variation even without new
content; panel emission modulation and instrument/electrical noise have not
been separately identified. Do not count every fluctuation as a content edge.

The approved 1,080-frame fixed-refresh sequence completed successfully.
Every consecutive source event advanced one vblank and was separated by
16.666-16.667 ms. The original framebuffer/native mode was restored and
verified, the override remained disabled, and no new kernel log lines
appeared. No variable-refresh experiment occurred in this checkpoint.

The Pico captured 128 separate 160 ms buffers at nominal 100 ksample/s,
including time before and after the display test. All 2,048,000 samples
passed chunk-count, CRC, conversion-error, FIFO and DMA checks. Transfer
gaps were approximately 451-454 ms: recorded sample time was 20.48 s over
approximately 78 s, about 26% coverage. This is explicitly **not** a
continuous record of the 18-second stimulus. The analyzer never joins
samples or computes intervals across those gaps.

At the fixed global 0.26 V midpoint with 0.17/0.35 V hysteresis, 140 optical
transitions were detected. Within the every-frame portion of the stimulus:

| Quantity | Observations | Median | Interpretation |
| --- | --- | --- | --- |
| Rising-to-rising interval | 50 | 33.33297 ms | Two content changes at native 60 Hz |
| Falling-to-falling interval | 49 | 33.33300 ms | Same cadence, independent edge polarity |
| Combined same-polarity repeats | 99 | 33.33299 ms | Approximately 6.4 us sample standard deviation |
| Bright dwell, rising to falling | 56 | 16.44499 ms | Includes optical waveform/duty asymmetry |
| Dark dwell, falling to rising | 56 | 16.88751 ms | Includes the complementary asymmetry |

The slower every-two-frame portion yielded eight same-polarity repetitions
with a median 66.66954 ms, consistent with the intended approximately
66.666 ms repeat period at this limited sample count. These are descriptive
cadence clusters, not a source-to-sensor clock fit or exact frame matching.

The alternating bright/dark dwell bias is roughly 0.22 ms at the selected
threshold, comparable to the proposed 0.282 ms difference between 59 and
60 Hz. Treating each mixed-polarity interval as an unbiased frame period
would therefore be wrong even in this fixed-refresh control. Shifting the
global midpoint to 0.20 or 0.32 V substantially changed the dwell estimates,
but the same-polarity median remained 33.33266-33.33302 ms. Outliers and
spread also depend on the threshold; this is not a complete uncertainty
budget. Same-polarity intervals span two changes and cannot, by themselves,
prove variable timing for each individual frame.

[`tools/analyze_pico_panel.py`](../tools/analyze_pico_panel.py) validates the
source/restoration checks and DMA transcript, preserves unmatched intervals,
and separates opposite/same-polarity measurements. The combined optical
analysis suite has 13 focused passing tests, including asymmetric duty,
noise within hysteresis and preventing artificial intervals across bursts.
The [anonymous panel report](../research/reports/pico-panel-fixed-refresh.json)
records source/capture hashes, interval statistics, threshold sensitivity and
limitations. Raw traces, source logs and a two-panel waveform plot remain in
ignored `artifacts/`.

The single-sensor setup is sufficient to continue development. The next
software tasks are gap-free buffered acquisition with loss detection and
global source-to-sensor sequence alignment. Keep edge-polarity effects in
that model. A later separately approved bounded VRR comparison is required
before drawing any conclusion about ANX bridge or panel VRR pass-through.

### Continuous recorder implementation, 2026-11-26

[`lab/pico`](../lab/pico/README.md) now contains a native USB recorder intended
to remove the burst-transfer gaps. ADC DMA runs continuously into a 32 KiB
circular buffer while USB transfers copied blocks. Checksummed headers and
payloads, absolute sample indices, final counts and sticky hardware/overrun
flags make data loss invalidate a recording. The strict host reader and
capture CLI preserve the original binary stream. No per-block timing gaps
are inserted intentionally, but physical continuity remains unverified.

The pinned SDK build succeeded and the combined optical host suite passed
19 tests. New checks cover partial transport reads, dropped/reordered and
duplicated packets, truncation, CRC damage, reported instrument failures,
C/Python packet layout and CRC agreement, and UF2 address/vector checks.
These are host/build checks, not evidence that the hardware stream works.

The authorized Pico accepted the UF2 copy and exposed the SDK USB device
identity. Its serial interface did not appear on the host, so physical
validation stopped before acquisition. Host authorization/enumeration and
firmware behavior remain possible causes. A normal USB reconnect is the
next recovery step; ROM BOOTSEL recovery is available if needed. No further
display stimulus or VRR experiment was run at this checkpoint. Continuous
capture, deliberate-stall loss detection, and global optical/source
alignment remain open.

### Continuous acquisition and source alignment validated, 2026-11-26

The native USB serial interface subsequently enumerated without another
firmware flash. The exact cause of the initial host-access problem was not
established. A 100,001-sample partial-block capture and a 25-second,
2,500,000-sample capture passed checksums, sequence/count checks and final
ADC/FIFO/DMA status checks. The largest pending sample count was 2,051 of
16,384 available ring slots. Unlike the MicroPython bursts, the ADC ran
continuously throughout each recording.

A three-second pause in host reads did not exhaust transport buffers and
the recording remained valid. A 12-second pause produced an incomplete
stream, which was rejected. No intact final status packet survived that
stall; do not claim a specific firmware error flag was measured. The Pico
responded to INFO afterward and passed another short capture without reset.
Software tests separately verify rejection of reported overrun/error flags,
missing/duplicated packets and CRC corruption.

Two 25-second continuous captures then covered complete 18-second native
fixed-refresh stimuli. Each source run completed 1,080 flips with one vblank
sequence increment per flip, restored the original framebuffer/native mode,
and produced no new kernel log lines. VRR remained disabled throughout.

The first trace contained 556 raw threshold crossings, including four
clusters of repeated crossings during falling transitions. The second had
548 raw crossings and two such clusters. These may reflect emission shape,
electrical interference, or both; their cause has not been isolated.
Consequently, raw threshold crossings are not all counted as content changes.
The detector qualifies a net transition after 100 us without another
crossing, timestamps the last crossing without adding that delay, and
retains every raw crossing and the full settling span. The largest span was
139 us in the first capture and 113 us in the second. This rule was selected
after inspection of the first trace; the second was acquired with the
thresholds, qualification rule and fitting procedure unchanged.

[`tools/analyze_optical_continuous.py`](../tools/analyze_optical_continuous.py)
matches the unique two-second preamble and the entire contiguous 542-edge
sequence without per-frame time warping or discarded timing outliers. All
542 intended transitions matched in each run, with no outside qualified
edges. A single relative clock scale, clock offset and rising-versus-falling
offset are fit to frames 480-719. The other 302 transitions, including the
last 240 fast transitions, do not influence that fit. Coefficients are
estimated separately for each recording. The 2 ms association guard only
rejects gross misalignment; it is not a precision claim.

| Measurement | First recording | Repeat recording |
| --- | --- | --- |
| Valid continuous samples | 2,500,000 | 2,500,000 |
| Matched intended content changes | 542 / 542 | 542 / 542 |
| Relative sample/source clock scale error | -0.89 ppm | -0.76 ppm |
| Rising relative to falling offset | 213 us | 218 us |
| Held-out fast-edge residual standard deviation | 10.2 us | 9.5 us |
| Held-out fast-edge residual range | -39 to +56 us | -25 to +67 us |
| All-edge residual range, including calibration segment | -39 to +56 us | -43 to +116 us |
| Same-polarity fast-repeat median | 33.33290 ms | 33.33291 ms |

These residuals are model discrepancies, not a complete uncertainty budget.
Falling edges in the slower two-frame-hold portion retain roughly 35-40 us
of systematic offset relative to the fast-segment fit. Threshold sensitivity
also remains material: global midpoints of 0.20, 0.26 and 0.32 V all retained
the full sequence but changed polarity offsets and residual spread. Held-out
standard deviations across those midpoints ranged from 9.5 to 15.7 us, with
individual residuals reaching approximately 105 us. Qualification intervals
of 50 and 200 us also retained the full sequence; they did not improve or
replace the primary 100 us result.

Approximately 0.50% and 0.56% of samples reached the ADC's lower rail;
none reached its upper rail. Dark-level noise, electrical coupling and
emission variation therefore remain relevant even though the content edges
were recovered. Keep raw waveforms, qualification spans and polarity effects
in subsequent analyses. A single sensor observes one screen location and
cannot reveal refreshes that repeat the same pixel value, scanout elsewhere,
or whether a delay originates in the bridge versus the panel. The fitted
clock offset also absorbs pipeline/scan/response latency and does not measure
absolute display latency.

The [anonymous continuous-capture report](../research/reports/pico-continuous-fixed-refresh.json)
preserves build/capture/source hashes, status and timing summaries. Full raw
recordings, source logs and plots remain in ignored `artifacts/`. The combined
optical suite passes 25 tests, including known clock/bias recovery, missing
edge rejection, raw settling preservation, and a held-out 120 us delay that
must remain visible rather than being fitted away.

The continuous acquisition and fixed-refresh alignment blockers are resolved.
This is enough to develop a bounded optical VRR comparison with the existing
single sensor. A next experiment must compare against a fixed control and
retain a common clock model so that fitting cannot absorb the effect under
test. No optical VRR conclusion follows yet; enabling experimental timings
still needs concrete human approval under [AGENTS.md](../AGENTS.md).
