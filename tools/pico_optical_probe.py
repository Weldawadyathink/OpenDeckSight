"""Run ON a Pico with MicroPython using mpremote run, not desktop Python.

Slow LED/ADC wiring check only: this is not a calibrated VRR timing capture.
GP26 and GP27 are inputs. Only the board-defined LED is driven. No network
connection, clock change, sensor bias change, or boot script is configured.
"""

import array
import gc
import json
import os
import sys
import time
from machine import ADC, Pin


def main():
    led = Pin("LED", Pin.OUT)
    inputs = (ADC(Pin(26)), ADC(Pin(27)))
    # Non-alternating order helps distinguish LED response from monotonic drift.
    states = (0, 1, 0, 1, 1, 0, 0, 1, 0, 1, 1, 0, 1, 0, 0, 1)
    count = 256
    samples = [array.array("H", [0] * count) for _ in inputs]
    print(json.dumps({
        "type": "metadata", "schema": "pico-optical-probe-v1",
        "machine": os.uname().machine, "version": sys.version,
        "gpio": [26, 27], "samples_per_window": count,
        "adc_format": "read_u16; scaled 12-bit conversions, not 16-bit precision",
        "nominal_reference_v": 3.3, "settle_ms": 50,
        "timing_validated": False,
    }))
    try:
        led.off()
        time.sleep_ms(100)
        for index, state in enumerate(states):
            gc.collect()
            led.value(state)
            time.sleep_ms(50)
            # Discard first conversions after switching ADC input.
            for adc in inputs:
                for _ in range(4):
                    adc.read_u16()
            begin = time.ticks_us()
            for sample in range(count):
                for channel, adc in enumerate(inputs):
                    adc.read_u16()
                    samples[channel][sample] = adc.read_u16()
                time.sleep_us(500)
            elapsed = time.ticks_diff(time.ticks_us(), begin)
            print(json.dumps({
                "type": "window", "index": index, "led": state,
                "elapsed_us": elapsed,
                "samples": [list(channel) for channel in samples],
            }))
        print(json.dumps({"type": "complete", "windows": len(states)}))
    finally:
        led.off()


main()
