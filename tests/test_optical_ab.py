import math
import array
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from opendecksight.optical_ab import NATIVE_US,compare,expected_flips,expected_edges,validate_pacing
from tools.run_optical_ab import remote_program
from tools.analyze_optical_ab import analyze
from tests.test_optical_stream import packet


def fixture(fixed_sink=False):
    flips=[];t=0
    for ordinal,(phase,frame,lit) in enumerate(expected_flips()):
        period=NATIVE_US
        if phase==1:period+=40+200*((frame//30)%2)
        t+=period
        flips.append({'phase':phase,'frame':frame,'ordinal':ordinal,'marker_lit':lit,
                      'event_ns':round(t*1000),'sequence':ordinal+100})
    expected=expected_edges(flips)
    observed=[]
    for e in expected:
        x=e['source_us']
        if fixed_sink:x=math.ceil((x-.01)/NATIVE_US)*NATIVE_US
        observed.append({'state':e['state'],'time_us':123456+1.00002*x+210*e['state']})
    return flips,observed


class OpticalABTests(unittest.TestCase):
    def test_feedback_schedule_uses_latest_event_and_rejects_drift(self):
        flips,_=fixture()
        for i,f in enumerate(flips):
            paced=f['phase']==1
            f['target_total']=(1980 if ((f['frame']-1)//60)%2 else 1964) if paced else 1956
            f['deadline_ns']=(flips[i-1]['event_ns']+f['target_total']*1220*1000000000//143180000-350000
                              if paced and f['frame']>1 else 0)
            f['submitted_ns']=f['deadline_ns']+200
        validate_pacing(flips,'optical-feedback-v1',True)
        flips[900]['deadline_ns']+=1
        with self.assertRaises(ValueError):validate_pacing(flips,'optical-feedback-v1',True)
        flips[900]['deadline_ns']-=1;flips[900]['submitted_ns']+=150000
        with self.assertRaises(ValueError):validate_pacing(flips,'optical-feedback-v1',True)

    def test_feedback_disabled_control_has_no_scheduled_delays(self):
        flips,_=fixture()
        for f in flips:f.update(target_total=1956,deadline_ns=0)
        validate_pacing(flips,'optical-feedback-v1',False)
        flips[720]['target_total']=1980
        with self.assertRaises(ValueError):validate_pacing(flips,'optical-feedback-v1',False)

    def test_remote_wrapper_is_syntactically_valid_without_execution(self):
        program=remote_program('experiment','0'*64,{'kernel_release':'test','files':{}})
        compile(program,'<remote-wrapper>','exec')

    def test_variable_updates_follow_source_but_leave_native_grid(self):
        flips,observed=fixture()
        r=compare(flips,observed)
        b=[p for p in r['pairs'] if p['phase']==1]
        self.assertLess(max(abs(p['source_residual_us']) for p in b),.01)
        self.assertGreater(max(abs(p['fixed_native_grid_residual_us']) for p in b),7000)

    def test_fixed_buffered_updates_stay_on_grid_but_not_source(self):
        flips,observed=fixture(True)
        r=compare(flips,observed)
        b=[p for p in r['pairs'] if p['phase']==1]
        self.assertLess(max(abs(p['fixed_native_grid_residual_us']) for p in b),.01)
        self.assertGreater(max(abs(p['source_residual_us']) for p in b),15000)

    def test_missing_optical_edge_rejected(self):
        flips,observed=fixture()
        with self.assertRaises(ValueError):compare(flips,observed[:-2])

    def test_atomic_phase_boundary_hold_is_retained(self):
        flips,observed=fixture()
        for f in flips:
            if f['ordinal']>=720:
                f['sequence']+=3;f['event_ns']+=round(3*NATIVE_US*1000)
        for e,o in zip(expected_edges(flips),observed):
            if e['ordinal']>=720:o['time_us']+=3*NATIVE_US*1.00002
        result=compare(flips,observed)
        hold=next(h for h in result['phase_boundary_holds'] if h['to_phase']==1)
        self.assertEqual(hold['vblank_steps'],4)
        self.assertGreater(hold['source_interval_us'],66000)
        self.assertLess(max(abs(p['source_residual_us']) for p in result['pairs']),.01)

    def test_large_within_phase_hold_and_bad_boundary_counter_rejected(self):
        for ordinal in (720,800):
            flips,observed=fixture()
            for f in flips:
                if f['ordinal']>=ordinal:f['sequence']+=3
            with self.assertRaises(ValueError):compare(flips,observed)

    def test_held_out_delay_cannot_change_clock_fit(self):
        flips,observed=fixture()
        baseline=compare(flips,observed)
        index=next(i for i,p in enumerate(baseline['pairs']) if p['phase']==1 and p['frame']==300)
        observed[index]['time_us']+=300
        changed=compare(flips,observed)
        self.assertEqual(changed['model'],baseline['model'])
        self.assertAlmostEqual(changed['pairs'][index]['source_residual_us'],300,places=2)

    def test_complete_binary_and_source_pipeline_and_restore_failure(self):
        flips,observed=fixture()
        samples=array.array('H',[36])*3200000
        state=0;start=0
        for edge in observed:
            end=round(edge['time_us']/10)
            samples[start:end]=array.array('H',[640 if state else 36])*(end-start)
            start=end;state=edge['state']
        for f in flips:
            step=(f['frame']-1)%720
            f.update(event='flip',target_total=1956 if f['phase']<0 else 1960+26*min(step,720-step)//360)
        pre={'event':'preflight','program':'optical-ab-v1','native_mode_verified':True,
             'vrr_capable':1,'opt_in':True,'experiment':True}
        phases=[{'event':'phase','phase':p,'frames':n,'vrr_requested':p==1} for p,n in ((-1,360),(0,360),(1,720),(2,360))]
        source={'mode':'experiment','returncode':0,'timed_out':False,'stderr':'',
                'events':[pre]+phases+flips+[{'event':'restore','success':True}],
                'post_check':{'returncode':0,'stderr':'','stdout':json.dumps(dict(pre,experiment=False))}}
        with tempfile.TemporaryDirectory() as temp:
            capture=Path(temp)/'capture.bin';path=Path(temp)/'source.json'
            with capture.open('wb') as out:
                out.write(packet(1,0,0,struct.pack('<8I',100000,len(samples),26,2048,16384,48000000,479<<8,1)))
                blocks=0
                for i in range(0,len(samples),2048):
                    block=samples[i:i+2048]
                    if sys.byteorder!='little':block.byteswap()
                    out.write(packet(2,blocks,i,block.tobytes()));blocks+=1
                out.write(packet(3,blocks,len(samples),struct.pack('<7I2Q',0,len(samples),len(samples),0x100000D,0x101,0x01000000,2050,0,len(samples)*10)))
            path.write_text(json.dumps(source))
            result=analyze(capture,path)
            self.assertEqual(result['qualified_edges'],1442)
            self.assertLess(result['phase_summary']['1']['source_residual_us']['max'],20)
            self.assertGreater(result['phase_summary']['1']['fixed_native_grid_residual_us']['max'],7000)
            pre['program']='optical-feedback-v1'
            for i,f in enumerate(flips):
                paced=f['phase']==1
                f['target_total']=(1980 if ((f['frame']-1)//60)%2 else 1964) if paced else 1956
                f['deadline_ns']=(flips[i-1]['event_ns']+f['target_total']*1220*1000000000//143180000-350000
                                  if paced and f['frame']>1 else 0)
                f['submitted_ns']=f['deadline_ns']+200 if f['deadline_ns'] else f['event_ns']-100000
            deliveries=[{'event':'delivery','ordinal':f['ordinal'],'received_ns':f['event_ns']+100000} for f in flips]
            source['events']+=deliveries;path.write_text(json.dumps(source))
            self.assertEqual(analyze(capture,path)['qualified_edges'],1442)
            source['events'].pop();path.write_text(json.dumps(source))
            with self.assertRaises(ValueError):analyze(capture,path)
            source['events']=source['events'][:-1799]
            source['events'][-1]['success']=False;path.write_text(json.dumps(source))
            with self.assertRaises(ValueError):analyze(capture,path)


if __name__=='__main__':unittest.main()
