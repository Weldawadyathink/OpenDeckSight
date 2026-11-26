import math
import array
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from opendecksight.optical_ab import NATIVE_US,compare,expected_flips,expected_edges
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
            source['events'][-1]['success']=False;path.write_text(json.dumps(source))
            with self.assertRaises(ValueError):analyze(capture,path)


if __name__=='__main__':unittest.main()
