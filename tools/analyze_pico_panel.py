#!/usr/bin/env python3
"""Summarize separated optical bursts from the approved fixed-refresh control.

Never concatenate samples across capture gaps. Same-polarity repeats are
reported separately from mixed-polarity intervals. No VRR verdict is made.
"""

import argparse
import hashlib
import json
from pathlib import Path
import statistics as stats
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.analyze_pico_optical_dma import read_captures


def summary(values):
    if not values:
        return {"count": 0}
    return {"count": len(values), "min": min(values), "median": stats.median(values),
            "max": max(values), "stddev": stats.pstdev(values)}


def edges(samples, rate, low_v=0.17, middle_v=0.26, high_v=0.35):
    if not 0 <= low_v < middle_v < high_v <= 3.3 or rate <= 0:
        raise ValueError("invalid hysteresis thresholds/rate")
    low, middle, high = (v * 4095 / 3.3 for v in (low_v, middle_v, high_v))
    state = None
    result = []
    for i, value in enumerate(samples):
        if state is None:
            if value <= low:
                state = 0
            elif value >= high:
                state = 1
            continue
        new = 1 if value >= high else 0 if value <= low else state
        if new != state:
            # Walk back to the latest midpoint crossing leading into this
            # hysteresis transition. Interpolate, without claiming that much
            # accuracy; sampling period and waveform noise still apply.
            j = i
            while j > 0 and ((samples[j-1] >= middle) if new else (samples[j-1] <= middle)):
                j -= 1
            if j > 0 and samples[j] != samples[j-1]:
                sample_index = j - 1 + (middle - samples[j-1]) / (samples[j] - samples[j-1])
                result.append({"state": new, "time_us": sample_index * 1_000_000 / rate})
            state = new
    return result


def intervals(transitions):
    adjacent = [{"to_state": b["state"], "us": b["time_us"] - a["time_us"]}
                for a, b in zip(transitions, transitions[1:])]
    repeated = []
    for state in (0, 1):
        selected = [e for e in transitions if e["state"] == state]
        repeated.extend({"state": state, "us": b["time_us"] - a["time_us"]}
                        for a, b in zip(selected, selected[1:]))
    return adjacent, repeated


def analyze(capture_path, source_path, middle_v=0.26):
    captures = read_captures(capture_path)
    source = json.loads(Path(source_path).read_text())
    if source["returncode"] or source["timed_out"] or source["stderr"]:
        raise ValueError("display experiment failed")
    preflight=[e for e in source["events"] if e.get("event")=="preflight"]
    if len(preflight)!=1 or not preflight[0].get("native_mode_verified") or preflight[0].get("vrr_capable")!=0:
        raise ValueError("missing fixed native-mode preflight")
    if not any(e.get("event") == "restore" and e.get("success") for e in source["events"]):
        raise ValueError("display restoration not verified")
    post = source["post_check"]
    if post["returncode"] or post["stderr"] or source["opt_in_after"] not in ("N", "0"):
        raise ValueError("post-test baseline check failed")
    post_event = json.loads(post["stdout"].strip())
    if post_event["vrr_capable"] != 0 or post_event["opt_in"]:
        raise ValueError("post-test VRR baseline is not disabled")
    flips = [e for e in source["events"] if e["event"] == "flip"]
    if [e["frame"] for e in flips] != list(range(1080)):
        raise ValueError("incomplete display sequence")
    event_periods = [(b["event_ns"]-a["event_ns"])/1000 for a,b in zip(flips, flips[1:])]
    steps = [(b["sequence"]-a["sequence"]) & 0xFFFFFFFF for a,b in zip(flips, flips[1:])]
    if any(step != 1 for step in steps):
        raise ValueError("source missed native vblank intervals")
    native_us = 1220 * 1956 / 143180000 * 1_000_000
    details, adjacent, repeated = [], [], []
    first = captures[0][0]["capture_start_ticks_us"]
    for h, values in captures:
        if h["led_stimulus"] or h["led_commands"]:
            raise ValueError("panel capture must not pulse onboard LED")
        transitions = edges(values, h["sample_rate_nominal_hz"], middle_v=middle_v)
        a, r = intervals(transitions)  # separately per burst, never across gaps
        adjacent.extend(a)
        repeated.extend(r)
        start_s = ((h["capture_start_ticks_us"]-first) % h["ticks_period_us"])/1_000_000
        details.append({"seq": h["seq"], "start_s": start_s,
                        "duration_s": len(values)/h["sample_rate_nominal_hz"],
                        "samples": len(values), "mean_v_nominal": stats.mean(values)*3.3/4095,
                        "min_v_nominal": min(values)*3.3/4095,
                        "max_v_nominal": max(values)*3.3/4095,
                        "adc_rail_samples": sum(v in (0,4095) for v in values),
                        "edges": transitions})
    # Descriptive clusters around the two intended cadences, not frame-by-frame
    # clock alignment. Preserve unmatched intervals rather than hiding them.
    clusters = []
    for frame_hold in (1,2):
        target = frame_hold*native_us
        a = [v for v in adjacent if abs(v["us"]-target)<500]
        r = [v for v in repeated if abs(v["us"]-2*target)<500]
        clusters.append({"intended_frames_between_changes":frame_hold,
                         "adjacent_interval_us":summary([v["us"] for v in a]),
                         "low_dwell_us":summary([v["us"] for v in a if v["to_state"]==1]),
                         "high_dwell_us":summary([v["us"] for v in a if v["to_state"]==0]),
                         "rising_repeat_us":summary([v["us"] for v in r if v["state"]==1]),
                         "falling_repeat_us":summary([v["us"] for v in r if v["state"]==0]),
                         "same_polarity_repeat_us":summary([v["us"] for v in r])})
    span = details[-1]["start_s"]+details[-1]["duration_s"]
    observed = sum(c["duration_s"] for c in details)
    result = {
        "schema":"pico-fixed-panel-analysis-v1", "date":"2026-11-26",
        "capture_sha256":hashlib.sha256(Path(capture_path).read_bytes()).hexdigest(),
        "source_sha256":hashlib.sha256(Path(source_path).read_bytes()).hexdigest(),
        "source_frames":len(flips), "source_event_period_us":summary(event_periods),
        "native_period_calculated_us":native_us, "source_sequence_steps":sorted(set(steps)),
        "display_restore_verified":True, "vrr_enabled":False,
        "kernel_log_unchanged":source["dmesg_before"]==source["dmesg_after"],
        "capture_checks_passed":True, "capture_bursts":len(captures),
        "total_samples":sum(len(v) for _,v in captures),
        "capture_span_s":span, "recorded_sample_time_s":observed,
        "coverage_fraction":observed/span,
        "sample_period_nominal_us":sorted({1_000_000/h["sample_rate_nominal_hz"] for h,_ in captures}),
        "thresholds_v_nominal":{"low":0.17,"middle":middle_v,"high":0.35},
        "clusters":clusters,
        "unmatched_adjacent_intervals":[v for v in adjacent if min(abs(v["us"]-n*native_us) for n in (1,2))>=500],
        "bursts":details,
        "limitations":[
            "Separated 160 ms bursts with transfer gaps, not a continuous recording of all display frames.",
            "No source-to-sensor clock offset/drift fit or exact optical frame matching was performed.",
            "Same-polarity intervals span two content changes; they do not resolve every individual frame.",
            "Mixed rising/falling intervals include asymmetric optical response and emission duty effects.",
            "Sub-sample interpolation and nominal reference voltage are not independent calibrations.",
            "Only one screen location and the native fixed-refresh mode were tested; no VRR pass-through conclusion.",
        ],
    }
    return result, captures


def plot(result, captures, destination):
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    # Select examples from stable gray and the fast-toggle cluster, solely for
    # illustration. Numeric summaries above retain every detected interval.
    gray = next(c for c in result["bursts"] if c["seq"]>0 and not c["edges"] and c["mean_v_nominal"]>0.4)
    toggling = next(c for c in result["bursts"] if len(c["edges"])>=9)
    fig, axes = plt.subplots(2,1,figsize=(10,6),constrained_layout=True)
    for axis, burst, title in zip(axes,(gray,toggling),
                                ("Static gray patch: sensor variation without content changes",
                                 "Marker changes every frame at fixed 60 Hz")):
        h, values = captures[burst["seq"]]
        t=np.arange(len(values))*1000/h["sample_rate_nominal_hz"]
        axis.plot(t,np.asarray(values)*3.3/4095,linewidth=0.7,color="#2366ad")
        axis.set(title=title,xlabel="Time within this capture (ms)",ylabel="Sensor output (V, nominal)",xlim=(0,160))
        axis.grid(alpha=.2)
    axes[1].axhline(result["thresholds_v_nominal"]["middle"],linestyle="--",color="#bd6725",linewidth=.8,label="Timing threshold")
    axes[1].legend(loc="upper right",fontsize=8)
    fig.suptitle("DeckSight optical fixed-refresh baseline\n100 ksample/s; one sensor; VRR disabled",fontsize=13)
    fig.savefig(destination,dpi=160)
    plt.close(fig)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("capture",type=Path)
    p.add_argument("source",type=Path)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--plot",type=Path)
    a=p.parse_args()
    result,captures=analyze(a.capture,a.source)
    with a.output.open("x") as f:
        json.dump(result,f,indent=2); f.write("\n")
    if a.plot: plot(result,captures,a.plot)
    print(json.dumps({k:result[k] for k in ("source_frames","capture_bursts","coverage_fraction","clusters")},indent=2))


if __name__=="__main__":
    main()
