#!/usr/bin/env python3
"""Validate continuous fixed-refresh optical capture and global source alignment."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from opendecksight.optical_stream import read_capture
from opendecksight.optical_alignment import align,qualify_edges,source_edges
from tools.analyze_pico_panel import edges,intervals,summary,validate_source


def analyze(capture_path,source_path,middle_v=.26,quiet_us=100):
    with Path(capture_path).open('rb') as stream:
        capture,values=read_capture(stream)
        if stream.read(1):raise ValueError('Trailing data after capture END')
    source,flips,periods,steps=validate_source(source_path)
    raw=edges(values,capture['config']['rate'],middle_v=middle_v)
    qualified,groups=qualify_edges(raw,quiet_us=quiet_us)
    matched=align(source_edges(flips),qualified)
    pairs=matched['pairs'];model=matched['model']
    phases={
        'preamble':[p for p in pairs if p['frame']<360],
        'two_frame_holds':[p for p in pairs if 360<=p['frame']<480],
        'training_fast':[p for p in pairs if 480<=p['frame']<720],
        'held_out_fast':[p for p in pairs if 720<=p['frame']<960],
        'final_dark':[p for p in pairs if p['frame']==960],
    }
    adjacent,repeated=intervals(phases['training_fast']+phases['held_out_fast'])
    calibrated=[]
    fast=phases['training_fast']+phases['held_out_fast']
    for a,b in zip(fast,fast[1:]):
        if b['frame']-a['frame']!=1:raise ValueError('Missing fast frame')
        dt=(b['time_us']-a['time_us']-model['rising_relative_to_falling_us']*(b['state']-a['state']))/model['scale']
        calibrated.append(dt)
    result={
        'schema':'pico-continuous-fixed-analysis-v1',
        'capture_sha256':hashlib.sha256(Path(capture_path).read_bytes()).hexdigest(),
        'source_sha256':hashlib.sha256(Path(source_path).read_bytes()).hexdigest(),
        'source_frames':len(flips),'source_event_period_us':summary(periods),
        'source_sequence_steps':sorted(set(steps)), 'display_restore_verified':True,
        'vrr_enabled':False,'kernel_log_unchanged':source['dmesg_before']==source['dmesg_after'],
        'capture_checks_passed':True,'sample_count':len(values),'packet_blocks':capture['blocks'],
        'acquisition_config':capture['config'],
        'instrument_status':{k:v for k,v in capture['end'].items() if k not in ('started_us','stopped_us')},
        'instrument_elapsed_us':capture['end']['stopped_us']-capture['end']['started_us'],
        'recorded_nominal_seconds':len(values)/capture['config']['rate'],
        'adc_rail_samples':sum(v in (0,4095) for v in values),
        'voltage_range_nominal':[min(values)*3.3/4095,max(values)*3.3/4095],
        'thresholds_v_nominal':{'low':.17,'middle':middle_v,'high':.35},
        'qualification_quiet_us':quiet_us,'raw_crossings':len(raw),
        'qualified_edges':len(qualified),'matched_edges':len(pairs),
        'settling_groups':[g for g in groups if len(g['crossings'])>1],
        'alignment':matched,
        'residual_us':summary([p['residual_us'] for p in pairs]),
        'phase_residual_us':{name:summary([p['residual_us'] for p in pp]) for name,pp in phases.items()},
        'fast_intervals':{
            'raw_dark_dwell_us':summary([p['us'] for p in adjacent if p['to_state']==1]),
            'raw_bright_dwell_us':summary([p['us'] for p in adjacent if p['to_state']==0]),
            'same_polarity_repeat_us':summary([p['us'] for p in repeated]),
            'clock_and_polarity_corrected_us':summary(calibrated)},
        'limitations':[
            'One sensor location and native fixed refresh only; no optical VRR pass-through test.',
            '100 us qualification groups raw recrossings; brief real light pulses and electrical noise are not distinguished.',
            'Settling spans and all alignment residuals are retained; individual edge uncertainty exceeds nominal sample spacing.',
            'First-half fast edges calibrate one affine clock transform and polarity bias; remaining edges are held out.',
            'Association guard is 2 ms, not the claimed measurement accuracy.',
            'Clock scale is relative to GPU event timestamps, not an independent oscillator calibration.',
            'Offset absorbs scan position, pipeline and response latency; it is not absolute display latency.',
            'A content transition does not expose refreshes that repeat the same pixel value.',
            'The raw ADC voltage reference, electrical interference, scan position and systematic timing errors are not independently calibrated.'
        ]}
    return result,values


def plot(result,values,destination):
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(3,1,figsize=(10,9))
    fig.subplots_adjust(left=.11,right=.98,bottom=.08,top=.91,hspace=.55)
    rate=result['acquisition_config']['rate']
    # Envelope preserves excursions that downsampling to isolated points could hide.
    block=100
    wave=np.asarray(values,dtype=float)*3.3/4095
    n=len(wave)//block
    chunks=wave[:n*block].reshape(n,block)
    t=(np.arange(n)*block+block/2)/rate
    axes[0].fill_between(t,chunks.min(axis=1),chunks.max(axis=1),color='#3579b5',alpha=.7)
    axes[0].set(title='Continuous acquisition: 1 ms min/max envelope',xlabel='Time in capture (s)',ylabel='Sensor voltage (nominal V)')
    pairs=result['alignment']['pairs']
    for state,color,label in ((0,'#3579b5','Falling'),(1,'#c26d27','Rising')):
        pp=[p for p in pairs if p['state']==state]
        axes[1].scatter([p['source_us']/1e6 for p in pp],[p['residual_us'] for p in pp],s=9,color=color,label=label)
    axes[1].axvspan(8,12,color='#888888',alpha=.12,label='Fit segment')
    axes[1].axhline(0,color='black',linewidth=.6)
    axes[1].set(title='Optical minus predicted transition time; all matched edges retained',xlabel='GPU time from first flip (s)',ylabel='Residual (us)')
    axes[1].legend(fontsize=8,ncol=3)
    settling=result['settling_groups']
    if settling:
        group=max(settling,key=lambda g:g['span_us'])
        base=group['crossings'][0]['time_us']
        lo=max(0,int((base-150)*rate/1e6));hi=min(len(wave),int((base+450)*rate/1e6))
        axes[2].plot(np.arange(lo,hi)*1e6/rate-base,wave[lo:hi],linewidth=.8)
        for e in group['crossings']:
            axes[2].axvline(e['time_us']-base,color='#c26d27',alpha=.5,linewidth=.8)
        axes[2].axhline(result['thresholds_v_nominal']['middle'],color='gray',linestyle='--',linewidth=.7)
        axes[2].set(title='Largest threshold-recrossing group; cause not isolated',xlabel='Time from first crossing (us)',ylabel='Sensor voltage (nominal V)')
    else:axes[2].text(.5,.5,'No threshold-recrossing groups',ha='center',transform=axes[2].transAxes)
    for axis in axes:axis.grid(alpha=.2)
    fig.suptitle('DeckSight fixed 60 Hz optical baseline — VRR disabled',fontsize=13,y=.975)
    fig.savefig(destination,dpi=160);plt.close(fig)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('capture',type=Path);p.add_argument('source',type=Path)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--plot',type=Path)
    a=p.parse_args();result,values=analyze(a.capture,a.source)
    with a.output.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    if a.plot:plot(result,values,a.plot)
    print(json.dumps({k:result[k] for k in ('sample_count','raw_crossings','matched_edges','residual_us','phase_residual_us')},indent=2))


if __name__=='__main__':main()
