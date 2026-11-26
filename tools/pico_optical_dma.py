"""Run ON an authorized RP2040 Pico W via mpremote run.

Capture GP26 with the ADC's 48 MHz clock divider, FIFO and DMA. The onboard
LED provides observable steps, NOT a known electrical timing reference.
No Deck access, external output drive, network connection or clock change.
Register meanings: pico-sdk 2.2.0, RP2040 hardware_regs adc.h and dreq.h.
"""

import array
import binascii
import gc
import json
import time
from machine import ADC, Pin, mem32
from rp2 import DMA

CS = 0x4004C000
FCS = CS + 8
FIFO = CS + 12
DIV = CS + 16
EN = 1
START_MANY = 8
READY = 1 << 8
ERR_STICKY = 1 << 10
FIFO_EMPTY = 1 << 8
FIFO_FAULTS = (1 << 10) | (1 << 11)
FIFO_CONFIG = (1 << 24) | 8 | 4 | 1  # threshold=1, DREQ, sample error bit, enable
RATE = 100_000
COUNT = 16_000


def capture(led, dma, buf, seq):
    led.off()
    time.sleep_ms(20)
    gc.collect()
    mem32[CS] = EN | ERR_STICKY  # GP26 / ADC0 only, clear error, stop free-run
    while not (mem32[CS] & READY):
        pass
    while not (mem32[FCS] & FIFO_EMPTY):
        _ = mem32[FIFO]
    mem32[DIV] = (48_000_000 // RATE - 1) << 8
    mem32[FCS] = FIFO_CONFIG | FIFO_FAULTS
    ctrl = dma.pack_ctrl(size=1, inc_read=False, inc_write=True, treq_sel=36)
    dma.config(read=FIFO, write=buf, count=COUNT, ctrl=ctrl, trigger=True)
    marks = []
    state = 0
    start = time.ticks_us()
    mem32[CS] = EN | START_MANY
    next_edge = 10_000
    # Stop issuing LED commands 20 ms before capture ends. This lets us stop
    # the ADC promptly at DMA completion without a slow LED call in progress.
    while dma.active():
        elapsed = time.ticks_diff(time.ticks_us(), start)
        if elapsed > 250_000:
            raise RuntimeError("ADC/DMA timeout")
        if elapsed >= next_edge and next_edge < 140_000:
            state ^= 1
            before = time.ticks_diff(time.ticks_us(), start)
            led.value(state)
            after = time.ticks_diff(time.ticks_us(), start)
            marks.append((state, before, after))
            next_edge += 10_000
    mem32[CS] = EN
    stop = time.ticks_us()
    while not (mem32[CS] & READY):
        pass
    fcs = mem32[FCS]
    cs = mem32[CS]
    dma_ctrl = dma.ctrl
    remaining = dma.count
    mem32[FCS] = 0
    led.off()
    view = memoryview(buf)
    print(json.dumps({
        "type": "capture", "schema": "pico-optical-dma-v1", "seq": seq,
        "gpio": 26, "samples": COUNT, "sample_rate_nominal_hz": RATE,
        "adc_clock_nominal_hz": 48_000_000, "adc_div_register": mem32[DIV],
        "elapsed_us": time.ticks_diff(stop, start),
        "fcs": fcs, "cs": cs, "dma_ctrl": dma_ctrl, "remaining": remaining,
        "format": "little-endian uint16; bits 0..11 ADC, bit 15 conversion error",
        "led_commands": marks, "led_command_timing_is_reference": False,
    }))
    # Send only after capture; avoid full-buffer hex/list allocations on MCU.
    for offset in range(0, COUNT, 256):
        print(json.dumps({"type": "data", "seq": seq, "offset": offset,
                          "hex": binascii.hexlify(view[offset:offset + 256]).decode()}))
    print(json.dumps({"type": "end", "seq": seq,
                      "crc32": binascii.crc32(view) & 0xFFFFFFFF}))


def main():
    adc = ADC(Pin(26))  # initialize clock, ADC and input pad through public API
    adc.read_u16()
    led = Pin("LED", Pin.OUT)
    led.off()  # initialize the wireless-chip LED driver before timed capture
    dma = DMA()
    buf = array.array("H", [0] * COUNT)
    old_div = mem32[DIV]
    old_cs = mem32[CS] & (1 | 2 | (7 << 12))
    try:
        for seq in range(4):
            capture(led, dma, buf, seq)
        print(json.dumps({"type": "complete", "captures": 4}))
    finally:
        mem32[CS] = EN
        while not (mem32[CS] & READY):
            pass
        dma.active(0)
        dma.close()
        mem32[FCS] = 0
        while not (mem32[FCS] & FIFO_EMPTY):
            _ = mem32[FIFO]
        mem32[DIV] = old_div
        mem32[CS] = old_cs
        led.off()


main()
