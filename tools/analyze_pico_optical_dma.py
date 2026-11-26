#!/usr/bin/env python3
"""Validate a Pico optical DMA transcript and summarize observed step widths.

Command timestamps locate search windows only. They are not electrical edge
timestamps. Widths describe the combined LED/sensor/ADC response, not pure
sensor latency or independently calibrated time.
"""

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import struct
import zlib


def validate_capture(header, chunks, end):
    if header.get("schema") != "pico-optical-dma-v1":
        raise ValueError("unknown schema")
    seq = header["seq"]
    count = header["samples"]
    if count <= 0 or header["sample_rate_nominal_hz"] <= 0:
        raise ValueError("invalid sample count/rate")
    raw = bytearray()
    for chunk in chunks:
        if chunk["seq"] != seq or chunk["offset"] != len(raw) // 2:
            raise ValueError("missing, reordered or repeated data chunk")
        block = bytes.fromhex(chunk["hex"])
        if not block or len(block) % 2:
            raise ValueError("invalid sample bytes")
        raw.extend(block)
    if len(raw) != count * 2 or end["seq"] != seq:
        raise ValueError("incomplete capture")
    if zlib.crc32(raw) != end["crc32"]:
        raise ValueError("CRC mismatch")
    # Be conservative: even a FIFO fault occurring just after DMA completion
    # invalidates the capture because we cannot establish when it happened.
    if header["fcs"] & 0xC00:
        raise ValueError("ADC FIFO overflow/underflow")
    if header["cs"] & 0x600:
        raise ValueError("ADC conversion error status")
    if header["remaining"] or header["dma_ctrl"] & 0xE1000000:
        raise ValueError("unfinished DMA or DMA bus error")
    expected_div = (header["adc_clock_nominal_hz"] // header["sample_rate_nominal_hz"] - 1) << 8
    if header["adc_div_register"] != expected_div:
        raise ValueError("ADC clock divider/rate mismatch")
    samples = struct.unpack("<" + str(count) + "H", raw)
    if any(v & 0xF000 for v in samples):
        raise ValueError("conversion error bit or reserved sample bits")
    return samples


def read_captures(path):
    rows = [json.loads(line) for line in Path(path).read_text().splitlines()]
    if not rows or rows[-1].get("type") != "complete":
        raise ValueError("missing complete marker")
    result = []
    header = None
    chunks = []
    for row in rows[:-1]:
        kind = row["type"]
        if kind == "capture":
            if header is not None or row["seq"] != len(result):
                raise ValueError("missing/reordered capture")
            header, chunks = row, []
        elif kind == "data" and header is not None:
            chunks.append(row)
        elif kind == "end" and header is not None:
            result.append((header, validate_capture(header, chunks, row)))
            header = None
        else:
            raise ValueError("unexpected record")
    if header is not None or len(result) != rows[-1]["captures"] or not result:
        raise ValueError("capture count mismatch")
    return result


def step_width(samples, rate, command):
    state, start_us, end_us = command
    if state not in (0, 1) or end_us < start_us:
        raise ValueError("invalid LED command window")
    period = 1_000_000 / rate
    # Medians in stable windows 0.2-1 ms before and after the command.
    a, b = int(start_us / period), int(end_us / period)
    near, far = max(1, round(200 / period)), round(1000 / period)
    lo, hi = a - round(100 / period), b + round(1500 / period)
    if a - far < 0 or hi >= len(samples):
        raise ValueError("step too close to capture boundary")
    before = statistics.median(samples[a - far:a - near])
    after = statistics.median(samples[b + near:b + far])
    delta = after - before
    if abs(delta) < 128 or (delta > 0) != bool(state):
        raise ValueError("missing or inverted optical step")
    normalized = [(v - before) / delta for v in samples[lo:hi]]
    crossings = []
    bins = []
    for level in (0.1, 0.5, 0.9):
        k = next((i for i in range(1, len(normalized))
                  if normalized[i - 1] < level <= normalized[i]), None)
        if k is None:
            raise ValueError("missing threshold crossing")
        fraction = (level - normalized[k - 1]) / (normalized[k] - normalized[k - 1])
        crossings.append((lo + k - 1 + fraction) * period)
        bins.append(lo + k)
    if crossings != sorted(crossings):
        raise ValueError("inconsistent threshold order")
    return {
        "state": state, "before_adc": before, "after_adc": after,
        "width_10_90_interpolated_us": crossings[2] - crossings[0],
        # Sampling brackets only: these exclude noise/level/clock uncertainty.
        "width_sampling_bracket_us": [max(0, (bins[2] - bins[0] - 1) * period),
                                       (bins[2] - bins[0] + 1) * period],
        "midpoint_sample_time_us": crossings[1],
        "command_duration_us": end_us - start_us,
    }


def analyze(path):
    captures = read_captures(path)
    details = []
    all_edges = []
    for header, samples in captures:
        rate = header["sample_rate_nominal_hz"]
        edges = [step_width(samples, rate, command) for command in header["led_commands"]]
        if not edges:
            raise ValueError("no LED transitions")
        all_edges.extend(edges)
        details.append({
            "seq": header["seq"], "samples": len(samples),
            "sample_rate_nominal_hz": rate, "sample_period_nominal_us": 1_000_000 / rate,
            "elapsed_us": header["elapsed_us"], "fcs": header["fcs"],
            "cs": header["cs"], "dma_ctrl": header["dma_ctrl"],
            "min_adc": min(samples), "max_adc": max(samples),
            "adc_rail_samples": sum(v in (0, 4095) for v in samples), "edges": edges,
        })
    widths = [e["width_10_90_interpolated_us"] for e in all_edges]
    return {
        "schema": "pico-optical-dma-analysis-v1",
        "raw_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        "captures": details, "total_samples": sum(len(s) for _, s in captures),
        "total_edges": len(all_edges),
        "width_10_90_interpolated_us": {"min": min(widths), "median": statistics.median(widths), "max": max(widths)},
        "transport_and_status_checks_passed": True,
        "absolute_clock_calibrated": False,
        "limitations": [
            "Widths characterize the combined onboard LED, optical sensor and ADC path at this light level.",
            "LED command times are not reference electrical-edge times; no absolute sensor latency is established.",
            "Sub-sample interpolation does not imply sub-sample accuracy; sampling brackets omit other uncertainties.",
            "No independent clock reference or known frame-interval stimulus was used.",
            "Passing short captures do not establish long-run streaming reliability or panel VRR.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.capture)
    with args.output.open("x") as output:
        json.dump(result, output, indent=2)
        output.write("\n")
    print(json.dumps({key: result[key] for key in
                      ("total_samples", "total_edges", "width_10_90_interpolated_us")}, indent=2))


if __name__ == "__main__":
    main()
