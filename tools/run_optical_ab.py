#!/usr/bin/env python3
"""Record one explicitly approved optical test; never deploy, opt in or reboot.

The reviewed binary must already be in the remote lab's RAM. --mode is
mandatory: this tool changes the display even in control mode.
"""
import argparse
import hashlib
import json
from pathlib import Path
import select
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def remote_program(mode,binary_hash,driver):
    return ('mode='+repr(mode)+'\nbinary_hash='+repr(binary_hash)+'\ndriver='+repr(driver)+'\n'+r'''
import hashlib,json,pathlib,signal,subprocess
P=pathlib.Path
cmdline=P('/proc/cmdline').read_text().split()
assert any(x in cmdline for x in ('ods.slot=research-a','ods.slot=research-b'))
assert 'rootfs / rootfs ' in P('/proc/mounts').read_text()
assert len(P('/proc/swaps').read_text().splitlines())==1
for pci in P('/sys/bus/pci/devices').iterdir():
    if int((pci/'class').read_text(),16)>>8 in (0x0108,0x0106):
        assert not (pci/'driver').exists()
binary=P('/run/ods-optical-ab')
assert hashlib.sha256(binary.read_bytes()).hexdigest()==binary_hash
assert subprocess.check_output(['uname','-r'],text=True).strip()==driver['kernel_release']
module=P('/usr/lib/modules')/driver['kernel_release']/'kernel/drivers/gpu/drm/amd/amdgpu/amdgpu.ko'
assert hashlib.sha256(module.read_bytes()).hexdigest()==driver['files']['amdgpu.ko']['sha256']
opt=P('/sys/module/amdgpu/parameters/ods_vrr_59_60').read_text().strip()
assert opt in (('Y','1') if mode=='experiment' else ('N','0'))
connectors=list(P('/sys/class/drm').glob('card*-eDP-*'))
assert len(connectors)==1
card='/dev/dri/'+connectors[0].name.split('-')[0]
before=subprocess.check_output(['dmesg'],text=True)
process=None
def interrupted(signum,frame):raise KeyboardInterrupt
for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP):signal.signal(sig,interrupted)
timed_out=False
try:
    process=subprocess.Popen([str(binary),'--'+mode,card],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:stdout,stderr=process.communicate(timeout=45)
    except subprocess.TimeoutExpired:
        timed_out=True;process.terminate()
        try:stdout,stderr=process.communicate(timeout=5)
        except subprocess.TimeoutExpired:process.kill();stdout,stderr=process.communicate(timeout=5)
finally:
    if process is not None and process.poll() is None:
        process.terminate()
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
post=subprocess.run([str(binary),'--check',card],capture_output=True,text=True,timeout=5)
after=subprocess.check_output(['dmesg'],text=True)
print(json.dumps({'mode':mode,'binary_sha256':binary_hash,'returncode':process.returncode,'timed_out':timed_out,
 'events':[json.loads(line) for line in stdout.splitlines()],'stderr':stderr,
 'post_check':{'returncode':post.returncode,'stdout':post.stdout,'stderr':post.stderr},
 'kernel_log_before':before,'kernel_log_after':after},indent=2))
''')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('target');p.add_argument('--port',required=True)
    p.add_argument('--known-hosts',type=Path,required=True)
    p.add_argument('--mode',choices=('control','experiment'),required=True)
    p.add_argument('--driver-manifest',type=Path,required=True)
    p.add_argument('--binary',type=Path,default=ROOT/'.tools/optical-ab/ods-optical-ab')
    p.add_argument('--output-prefix',type=Path,required=True)
    a=p.parse_args()
    if a.target.startswith('-') or any(c.isspace() for c in a.target):p.error('invalid target')
    if (ROOT/'artifacts').resolve() not in a.output_prefix.resolve().parents:p.error('keep raw output in artifacts/')
    paths={suffix:Path(str(a.output_prefix)+suffix) for suffix in ('.bin','.json','.source.json','.source.stderr','.capture.stdout','.capture.stderr','.coordination.json')}
    if any(path.exists() for path in paths.values()):p.error('output prefix already exists')
    driver=json.loads(a.driver_manifest.read_text())
    program=remote_program(a.mode,hashlib.sha256(a.binary.read_bytes()).hexdigest(),driver)
    ssh=['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','UpdateHostKeys=no',
         '-o','UserKnownHostsFile='+str(a.known_hosts),'-o','ConnectTimeout=8',a.target,'python3 -B -']
    capture=None
    try:
        with paths['.capture.stderr'].open('x') as err:
            capture=subprocess.Popen([sys.executable,str(ROOT/'tools/capture_pico_stream.py'),'--port',a.port,
                '--samples','5000000','--output',str(paths['.bin'])],stdout=subprocess.PIPE,stderr=err,text=True)
            if not select.select([capture.stdout],[],[],10)[0]:raise RuntimeError('No Pico start acknowledgement')
            first=capture.stdout.readline()
            if not json.loads(first).get('capture_started'):raise RuntimeError('Pico failed before display test')
            result=subprocess.run(ssh,input=program,capture_output=True,text=True,timeout=65)
            paths['.source.json'].write_text(result.stdout);paths['.source.stderr'].write_text(result.stderr)
            output,_=capture.communicate(timeout=55)
            paths['.capture.stdout'].write_text(first+output)
            paths['.coordination.json'].write_text(json.dumps({'capture_returncode':capture.returncode,'ssh_returncode':result.returncode},indent=2)+'\n')
            if result.returncode or result.stderr or capture.returncode:raise RuntimeError('Capture or remote test failed; preserve raw output')
            source=json.loads(result.stdout)
            if source['returncode'] or source['timed_out'] or source['stderr']:raise RuntimeError('Display test did not finish cleanly')
            if not any(e.get('event')=='restore' and e.get('success') for e in source['events']):raise RuntimeError('Display restoration not verified')
            if source['post_check']['returncode'] or source['post_check']['stderr']:raise RuntimeError('Post-test preflight failed')
            print('Capture and framebuffer/VRR-off restoration completed. Experimental boot still requires baseline reboot.')
    finally:
        if capture is not None and capture.poll() is None:
            capture.terminate()
            try:capture.wait(timeout=5)
            except subprocess.TimeoutExpired:capture.kill();capture.wait(timeout=5)


if __name__=='__main__':main()
