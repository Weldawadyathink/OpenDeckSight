#!/usr/bin/env python3
"""Summarize the recorded source schedule and candidate arithmetic; no device I/O."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from opendecksight.optical_ab import expected_edges,validate_pacing


def stats(values):
    return {'count':len(values),'min':min(values),'median':statistics.median(values),'max':max(values)}


def analyze(path):
    raw=path.read_bytes();source=json.loads(raw)
    if source['returncode'] or source['timed_out'] or source['stderr']:
        raise ValueError('Incomplete source experiment')
    flips=[e for e in source['events'] if e.get('event')=='flip']
    expected_edges(flips)
    pre=[e for e in source['events'] if e.get('event')=='preflight']
    if len(pre)!=1 or pre[0]['program']!='optical-ab-v1' or source['mode']!='experiment':
        raise ValueError('This comparison requires the original experimental sweep')
    validate_pacing(flips,'optical-ab-v1',True)
    middle=[f for f in flips if f['phase']==1]
    periods=[];misses=[];latency=[];late=[];errors=[]
    for a,b in zip(middle,middle[1:]):
        steps=(b['sequence']-a['sequence'])&0xffffffff
        period=(b['event_ns']-a['event_ns'])/1000/steps
        requested=b['target_total']*1220/143.18
        periods.append(period);errors.append(period-requested)
        late.append((b['submitted_ns']-b['deadline_ns'])/1000)
        if steps>1:misses.append({'frame':b['frame'],'vblank_steps':steps})
        if steps==1 and period>16700:
            latency.append((b['event_ns']-b['submitted_ns'])/1000)
    candidates=[]
    for lower in (59,58):
        # Match mod_freesync_calc_v_total_from_refresh at the lower bound:
        # integer nanoseconds, then round the vertical total down.
        duration_ns=1000000000//lower
        total=duration_ns*143180//1220//1000000
        period_us=total*1220/143.18
        candidates.append({'nominal_min_hz':lower,'maximum_total_candidate':total,
            'period_us':period_us,'quantized_min_hz':1e6/period_us,
            'extra_lines_from_native':total-1956,'front_porch_lines_if_stretched':8+total-1956,
            'extra_period_us_from_native':(total-1956)*1220/143.18})
    return {'schema':'vrr-source-pacing-review-v1','source_sha256':hashlib.sha256(raw).hexdigest(),
        'within_B_intervals':len(periods),'fast_bound_intervals_below_16680_us':sum(p<16680 for p in periods),
        'multi_vblank_content_holds':misses,'source_period_us':stats(periods),
        'actual_minus_requested_period_us':stats(errors),'submission_lateness_us':stats(late),
        'submission_to_event_us_for_single_step_periods_above_16700':stats(latency),
        'candidate_ranges':candidates,
        'interpretation':'Absolute scheduling persisted across three two-vblank holds; long fast-bound stretches followed. This supports trying event-anchored pacing, but does not isolate kernel or hardware causes.',
        'limitations':['Submission-to-event delay is not isolated driver latency or display latency.',
            'Candidate arithmetic is not a panel tolerance, hardware observation or approved range.',
            'The feedback lead is a fixed empirical starting point, not a proven latency correction.']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=analyze(a.source)
    with a.output.open('x') as out:json.dump(r,out,indent=2);out.write('\n')
    print(json.dumps(r,indent=2))


if __name__=='__main__':main()
