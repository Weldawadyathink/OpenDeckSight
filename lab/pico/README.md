# Continuous optical recorder

This firmware replaces MicroPython on an authorized Pico W. It initializes
GP26 as ADC0 and native USB; it does not initialize wireless or drive external
pins. Its intended rate is 100 ksample/s, with a 16,384-sample DMA circular
buffer and independent 2,048-sample USB packets. Acquisition is finite,
at most 60 seconds. Continuous 25-second captures and deliberate-stall
rejection have passed. Two fixed-refresh optical runs have been aligned with
GPU events; this is not yet an optical VRR test.

## Build

Install CMake, Ninja and an Arm bare-metal GCC toolchain locally. Place the
official Raspberry Pi SDK in ignored `.tools/pico-sdk`, checked out at
`a1438dff1d38bd9c65dbd693f0e5db4b9ae91779` (tag `2.2.0`). Initialize its
`lib/tinyusb` submodule at `86ad6e56c1700e85f1c5678607a762cfe3aa2f47`.
Other SDK submodules are unnecessary for this USB-only program.

From the repository root:

```sh
python3 tools/build_pico_capture.py
python3 -m unittest tests.test_optical_stream
```

The build writes a UF2, build log and provenance manifest to ignored
`artifacts/vrr/pico-continuous/`. The script verifies dependency revisions,
checks the image vector table, and records source/compiler/image hashes.
It does not flash any device. Flashing replaces existing Pico firmware and
requires device-management authorization. Copy the UF2 to the intended
Pico's `RPI-RP2` boot volume only after verifying the connected device.

## Protocol and capture

Serial commands use newline termination and nominal baud 115200:

* `INFO` reports firmware identity and limits as JSON.
* `CAPTURE N` emits binary BEGIN, DATA and END packets for N samples.
* `!` during capture aborts it and marks the result invalid.
* `BOOT` enters the ROM USB bootloader for an authorized firmware update.

`protocol.h` specifies little-endian packet fields. Every header and payload
has CRC32; each data block includes its sequence and first sample index.
END reports sample counts, timestamps, DMA/ADC/FIFO state and sticky failure
flags. DMA overwrite, conversion errors, transport corruption, missing data,
abort and missing END all invalidate a capture. The host never silently
resynchronizes or joins separated runs. USB congestion can still make a run
invalid; buffering is not a guarantee against indefinite host stalls.

With PySerial installed, use the current Pico serial path:

```sh
python3 tools/capture_pico_stream.py --port SERIAL_PATH --samples 2500000 \
  --output artifacts/vrr/pico-continuous/capture.bin
```

The output must be new. Its adjacent JSON summary is written only after the
entire capture validates. Preserve a failed raw stream for diagnosis; it
must not be analyzed as valid optical timing. ADC values are unscaled 12-bit
samples and the 10 us sample period is nominal, not independently calibrated.

## Bring-up and recovery

The first UF2 build passed host protocol/CRC/layout tests and was copied to
the authorized Pico. USB descriptors initially appeared without a serial
interface. On the subsequent check the serial interface enumerated with the
same firmware, without another flash. The precise cause of the initial host
enumeration/authorization issue was not established.

First try reconnecting normally with the host unlocked and accepting an
accessory prompt if one appears. If USB serial still cannot enumerate,
hold BOOTSEL while reconnecting to expose `RPI-RP2`; ROM recovery remains
available regardless of the application firmware. A known-good MicroPython
image and its hash are retained in ignored artifacts. Do not change wiring
or move the optical sensor as part of USB recovery.

Bring-up passed a 100,001-sample capture with a partial final packet, a
2,500,000-sample continuous capture, and recovery after an intentionally
stalled reader. A three-second read pause was absorbed by host buffers; a
12-second pause truncated the stream, which the strict reader rejected.
The failure had no intact END packet, so no particular firmware overrun flag
is claimed to have been observed. Host tests separately cover those flags.

Two subsequent 25-second recordings covered the complete fixed-refresh
display sequence, each matching all 542 intended optical transitions.
See [measurement notes](../../docs/vrr-optical-measurement.md) for the
100 us settling qualification, polarity bias, held-out residuals and
unresolved electrical/optical noise. With optional NumPy/Matplotlib installed:

```sh
python3 tools/analyze_optical_continuous.py CAPTURE.bin SOURCE.json \
  --output artifacts/vrr/analysis.json --plot artifacts/vrr/analysis.png
```

The source transcript must include the completed sequence, successful
restoration and post-test native-mode checks. An experimental VRR display
change still requires concrete human approval.
