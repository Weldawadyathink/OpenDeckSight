#!/usr/bin/env python3
"""Run a selected bounded USB-lab visual test; defaults to KMS/one-byte AUX checks."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from opendecksight.visual_report import summarize


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('target')
    p.add_argument('--known-hosts',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True,help='new local raw report in artifacts/')
    p.add_argument('--mode',choices=('check','control','experiment'),default='check')
    p.add_argument('--build-manifest',type=Path,default=ROOT/'artifacts/vrr/visual-ab/driver-build.json')
    a=p.parse_args()
    if a.target.startswith('-') or any(c.isspace() for c in a.target): p.error('invalid target')
    if (ROOT/'artifacts').resolve() not in a.output.resolve().parents: p.error('keep raw output in artifacts/')
    if a.output.exists(): p.error('output already exists')
    expected=json.loads(a.build_manifest.read_text())
    program='import sys, types\nsys.dont_write_bytecode=True\n'
    program+="package=types.ModuleType('opendecksight');package.__path__=[];sys.modules['opendecksight']=package\n"
    for name in ('dpcd','msa_control'):
        full='opendecksight.'+name
        program+=f'module=types.ModuleType({full!r});module.__package__="opendecksight";sys.modules[{full!r}]=module\n'
        program+=f'exec(compile({(ROOT/"opendecksight"/(name+".py")).read_text()!r},"<streamed>","exec"),module.__dict__)\n'
    program+='expected='+repr(expected)+'\nmode='+repr(a.mode)+'\n'+r'''
import hashlib,json,pathlib,signal,subprocess,time
from opendecksight.msa_control import collect as read_msa
P=pathlib.Path
binary=P('/usr/local/bin/ods-visual-ab')
assert hashlib.sha256(binary.read_bytes()).hexdigest()==expected['files']['ods-visual-ab']['sha256']
module=P('/usr/lib/modules')/expected['kernel_release']/'kernel/drivers/gpu/drm/amd/amdgpu/amdgpu.ko'
assert hashlib.sha256(module.read_bytes()).hexdigest()==expected['files']['amdgpu.ko']['sha256']
connectors=list(P('/sys/class/drm').glob('card*-eDP-*'))
assert len(connectors)==1
card='/dev/dri/'+connectors[0].name.split('-')[0]
before=subprocess.check_output(['dmesg'],text=True)
control_before=read_msa()
process=None
def interrupted(signum,frame):
    raise KeyboardInterrupt
for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP): signal.signal(sig,interrupted)
timed_out=False
try:
    process=subprocess.Popen([str(binary),'--'+mode,card],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        output,error=process.communicate(timeout=45)
    except subprocess.TimeoutExpired:
        timed_out=True
        process.terminate()
        try: output,error=process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill();output,error=process.communicate(timeout=5)
finally:
    if process is not None and process.poll() is None:
        process.terminate()
        try: process.wait(timeout=5)
        except subprocess.TimeoutExpired: process.kill();process.wait(timeout=5)
after=subprocess.check_output(['dmesg'],text=True)
try: control_after=read_msa()
except (OSError,ValueError) as error_reading: control_after={'error':str(error_reading)}
print(json.dumps({'mode':mode,'returncode':process.returncode,'timed_out':timed_out,
                  'events':[json.loads(line) for line in output.splitlines()],
                  'stderr':error,'kernel_log_before':before,'kernel_log_after':after,
                  'msa_control_before':control_before,'msa_control_after':control_after},indent=2))
'''
    result=subprocess.run(['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
        '-o','UpdateHostKeys=no','-o','UserKnownHostsFile='+str(a.known_hosts),
        '-o','ConnectTimeout=10',a.target,'python3 -B -'],input=program,capture_output=True,text=True,timeout=75)
    if result.returncode: p.exit(1,result.stderr)
    report=json.loads(result.stdout)
    report['timing_summary']=summarize(report['events'])
    with a.output.open('x') as f: json.dump(report,f,indent=2);f.write('\n')
    detail='preflight only' if a.mode=='check' else 'restore='+str(report['timing_summary']['restore_verified'])
    print('Saved '+str(a.output)+'; exit='+str(report['returncode'])+'; '+detail)
    if report['returncode'] or report['timed_out']: sys.exit(1)


if __name__=='__main__': main()
