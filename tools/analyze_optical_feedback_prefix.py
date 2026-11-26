#!/usr/bin/env python3
"""Diagnose a deadline-aborted feedback capture; never convert it to a passing run."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from opendecksight.optical_ab import NATIVE_US,expected_flips,validate_pacing
from opendecksight.optical_alignment import fit_clock,residual,qualify_edges
from opendecksight.optical_stream import read_capture
from tools.analyze_pico_panel import edges,summary


def compare_prefix(flips,observed):
    if not 720<len(flips)<1440:
        raise ValueError('Expected an incomplete B after complete preamble and fixed A')
    if [f['ordinal'] for f in flips]!=list(range(len(flips))):
        raise ValueError('Missing or reordered source events')
    if [(f['phase'],f['frame'],f['marker_lit']) for f in flips]!=expected_flips()[:len(flips)]:
        raise ValueError('Not the exact stimulus prefix')
    validate_pacing(flips,'optical-feedback-v1',True)
    for a,b in zip(flips,flips[1:]):
        steps=(b['sequence']-a['sequence'])&0xffffffff
        if not 1<=steps<=8:raise ValueError('Unexpected source sequence progression')
        if a['phase']==b['phase'] and steps>3:raise ValueError('Oversized within-phase hold')
        period=(b['event_ns']-a['event_ns'])/1000/steps
        lower=1220*1957/143180000*1e6 if a['phase']==b['phase']==1 else NATIVE_US
        upper=1220*1989/143180000*1e6 if b['phase']==1 else NATIVE_US
        if not lower-2<=period<=upper+2:raise ValueError('Source timing outside guards')
    base=flips[0]['event_ns']
    expected=[{'ordinal':b['ordinal'],'phase':b['phase'],'frame':b['frame'],
               'state':int(b['marker_lit']),'source_us':(b['event_ns']-base)/1000,'sequence':b['sequence']}
              for a,b in zip(flips,flips[1:]) if a['marker_lit']!=b['marker_lit']]
    if len(observed)!=len(expected):raise ValueError('Extra/missing optical edges; no trimming allowed')
    if any(a['state']!=b['state'] for a,b in zip(expected,observed)):
        raise ValueError('Polarity mismatch')
    if any(b['time_us']<=a['time_us'] for a,b in zip(observed,observed[1:])):
        raise ValueError('Nonmonotonic optical sequence')
    pairs=[dict(a,**b) for a,b in zip(expected,observed)]
    training=[p for p in pairs if p['phase']==0]
    model=fit_clock(training)
    if len(training)!=360 or abs(model['scale_error_ppm'])>1000 or max(abs(residual(p,model)) for p in training)>2000:
        raise ValueError('Fixed A alignment failed')
    if abs(observed[1]['time_us']-observed[0]['time_us']-2000000)>2000:
        raise ValueError('Preamble timing mismatch')
    period=model['scale']*NATIVE_US
    origin=model['offset_us']+model['scale']*training[0]['source_us']
    for p in pairs:
        p['source_residual_us']=residual(p,model)
        adjusted=p['time_us']-model['rising_relative_to_falling_us']*p['state']
        p['fixed_native_grid_residual_us']=(adjusted-origin+period/2)%period-period/2
    blocks=[];middle=[f for f in flips if f['phase']==1]
    for block in range((len(middle)+59)//60):
        selected=[f for f in middle if (f['frame']-1)//60==block]
        values=[(b['event_ns']-a['event_ns'])/1000/((b['sequence']-a['sequence'])&0xffffffff)
                for a,b in zip(middle,middle[1:]) if (b['frame']-1)//60==block]
        blocks.append({'block':block,'target_total':1980 if block%2 else 1964,
                       'completed_frames':len(selected),'complete':len(selected)==60,
                       'source_period_us':summary(values)})
    return {'completion_status':'aborted','progression_passed':False,'source_flips':len(flips),
        'completed_B_flips':len(middle),'matched_prefix_edges':len(pairs),'model':model,'pairs':pairs,
        'feedback_blocks':blocks,'final_fixed_phase_available':False,
        'phase_summary':{str(phase):{key:summary([p[key] for p in pairs if p['phase']==phase])
                                  for key in ('source_residual_us','fixed_native_grid_residual_us')}
                         for phase in (-1,0,1)},
        'limitations':['An exact observed prefix is analyzed; the planned full sequence failed.',
            'No final fixed A or independent repeat is available.',
            'Clock and polarity calibration use only the complete first fixed A.',
            'No timing outliers or extra optical edges are removed.']}


def analyze(capture_path,source_path):
    source=json.loads(source_path.read_text())
    if (source['mode']!='experiment' or source['returncode']!=1 or source['timed_out'] or
            source['stderr']!='Missed feedback submission deadline; refusing catch-up.\nOptical A/B test failed, timed out or preflight refused.\n'):
        raise ValueError('Not the reviewed deadline-abort outcome')
    events=source['events'];pre=[e for e in events if e.get('event')=='preflight']
    if len(pre)!=1 or pre[0]!={'event':'preflight','program':'optical-feedback-v1','native_mode_verified':True,'vrr_capable':1,'opt_in':True,'experiment':True}:
        raise ValueError('Unexpected preflight')
    if [(e['phase'],e['frames'],e['vrr_requested']) for e in events if e.get('event')=='phase']!=[(-1,360,False),(0,360,False),(1,720,True)]:
        raise ValueError('Unexpected phase configuration')
    if [e for e in events if e.get('event')=='restore']!=[{'event':'restore','success':True}]:
        raise ValueError('Restoration unverified')
    post=source['post_check']
    if post['returncode'] or post['stderr'] or json.loads(post['stdout'])!=dict(pre[0],experiment=False):
        raise ValueError('Post-test baseline failed')
    flips=[e for e in events if e.get('event')=='flip']
    deliveries=[e for e in events if e.get('event')=='delivery']
    if [e['ordinal'] for e in deliveries]!=list(range(len(flips))) or any(e['received_ns']<f['submitted_ns'] for f,e in zip(flips,deliveries)):
        raise ValueError('Invalid delivery record')
    with capture_path.open('rb') as raw:
        capture,values=read_capture(raw)
        if raw.read(1):raise ValueError('Trailing capture bytes')
    crossings=edges(values,capture['config']['rate']);observed,groups=qualify_edges(crossings)
    result=compare_prefix(flips,observed)
    result.update(schema='optical-feedback-aborted-prefix-v1',mode='experiment',
        capture_sha256=hashlib.sha256(capture_path.read_bytes()).hexdigest(),
        source_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),
        sample_count=len(values),raw_crossings=len(crossings),qualified_edges=len(observed),
        settling_groups=[g for g in groups if len(g['crossings'])>1],
        display_restore_verified=True,experimental_boot_still_enabled=True)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('capture',type=Path);p.add_argument('source',type=Path)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=analyze(a.capture,a.source)
    with a.output.open('x') as out:json.dump(r,out,indent=2);out.write('\n')
    print(json.dumps({k:r[k] for k in ('completion_status','progression_passed','matched_prefix_edges','phase_summary','feedback_blocks')},indent=2))


if __name__=='__main__':main()
