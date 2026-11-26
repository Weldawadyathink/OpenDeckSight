#!/usr/bin/env python3
"""Analyze an optical A/B capture; never infer hardware VRR support automatically."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from opendecksight.optical_ab import NATIVE_US,compare
from opendecksight.optical_alignment import qualify_edges
from opendecksight.optical_stream import read_capture
from tools.analyze_pico_panel import edges,summary


def analyze(capture_path,source_path):
    source=json.loads(Path(source_path).read_text())
    if source['returncode'] or source['timed_out'] or source['stderr']:
        raise ValueError('Display run did not finish cleanly')
    mode=source['mode']
    if mode not in ('control','experiment'):raise ValueError('Unknown source mode')
    enabled=mode=='experiment'
    events=source['events']
    pre=[e for e in events if e.get('event')=='preflight']
    if len(pre)!=1 or pre[0].get('program')!='optical-ab-v1' or not pre[0].get('native_mode_verified'):
        raise ValueError('Missing native-mode preflight')
    if (pre[0]['vrr_capable'],pre[0]['opt_in'],pre[0]['experiment'])!=(int(enabled),enabled,enabled):
        raise ValueError('Wrong capability/boot opt-in')
    phases=[(e['phase'],e['frames'],e['vrr_requested']) for e in events if e.get('event')=='phase']
    if phases!=[(-1,360,False),(0,360,False),(1,720,enabled),(2,360,False)]:
        raise ValueError('Unexpected phase configuration')
    restored=[e for e in events if e.get('event')=='restore']
    if len(restored)!=1 or restored[0].get('success') is not True:raise ValueError('Restoration unverified')
    post=source['post_check']
    if post['returncode'] or post['stderr']:raise ValueError('Post-test preflight failed')
    after=json.loads(post['stdout'])
    if (not after.get('native_mode_verified') or after.get('experiment') or
            after.get('opt_in')!=enabled or after.get('vrr_capable')!=int(enabled)):
        raise ValueError('Wrong post-test baseline; experimental boot may still be enabled')
    with Path(capture_path).open('rb') as stream:
        capture,values=read_capture(stream)
        if stream.read(1):raise ValueError('Trailing capture bytes')
    raw=edges(values,capture['config']['rate'])
    qualified,groups=qualify_edges(raw)
    flips=[e for e in events if e.get('event')=='flip']
    for f in flips:
        if f['phase']<0:expected_total=1956
        else:
            step=(f['frame']-1)%720
            expected_total=1960+26*min(step,720-step)//360
        if f['target_total']!=expected_total:raise ValueError('Unexpected submission target')
    result=compare(flips,qualified)
    phase_summary={}
    for phase in (-1,0,1,2):
        pp=[p for p in result['pairs'] if p['phase']==phase]
        ff=[f for f in flips if f['phase']==phase]
        periods=[(b['event_ns']-a['event_ns'])/1000/((b['sequence']-a['sequence'])&0xffffffff)
                 for a,b in zip(ff,ff[1:])]
        phase_summary[str(phase)]={'source_period_per_vblank_us':summary(periods),
            'source_intervals_outside_native_2us':sum(abs(v-NATIVE_US)>2 for v in periods),
            'source_residual_us':summary([p['source_residual_us'] for p in pp]),
            'fixed_native_grid_residual_us':summary([p['fixed_native_grid_residual_us'] for p in pp])}
    if any(phase_summary[str(phase)]['source_intervals_outside_native_2us']
           for phase in (-1,0,2) if phase_summary[str(phase)]['source_period_per_vblank_us']['count']):
        raise ValueError('Fixed source control was not native-periodic')
    if not enabled and phase_summary['1']['source_intervals_outside_native_2us']:
        raise ValueError('Control run has non-native source intervals')
    result.update(schema='optical-ab-analysis-v1',mode=mode,phase_summary=phase_summary,
        capture_sha256=hashlib.sha256(Path(capture_path).read_bytes()).hexdigest(),
        source_sha256=hashlib.sha256(Path(source_path).read_bytes()).hexdigest(),
        sample_count=len(values),raw_crossings=len(raw),qualified_edges=len(qualified),
        settling_groups=[g for g in groups if len(g['crossings'])>1],
        display_restore_verified=True,experimental_boot_still_enabled=enabled,
        automatic_vrr_verdict=None)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('capture',type=Path);p.add_argument('source',type=Path)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=analyze(a.capture,a.source)
    with a.output.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({'mode':result['mode'],'phase_summary':result['phase_summary']},indent=2))


if __name__=='__main__':main()
