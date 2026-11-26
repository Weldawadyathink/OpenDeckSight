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
It is controlled through the CYW43 wireless chip, so use it for slow
light/dark checks, not as an assumed precise timing reference. For later
hardware-paced characterization, an external LED can use GP15 (physical
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
