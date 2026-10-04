"""Boot candidate initramfs in QEMU, load AMD module without AMD hardware, refuse VRR."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0,'/src')
from opendecksight.lab_update import BASE_ARGS, sha

out=Path('/out');work=Path('/work/vrr-vm');work.mkdir(parents=True,exist_ok=True)
canary=work/'internal.img'
with canary.open('wb') as f:
    f.write(b'OpenDeckSight VRR virtual storage canary\n');f.truncate(32*1024*1024)
before=sha(canary)
hosts=work/'known_hosts';hosts.unlink(missing_ok=True)
ssh=['ssh','-p','2233','-o','BatchMode=yes','-o','PreferredAuthentications=none',
     '-o','StrictHostKeyChecking=accept-new','-o','UserKnownHostsFile='+str(hosts),
     '-o','ConnectTimeout=2','root@127.0.0.1']
args=['qemu-system-x86_64','-machine','q35','-accel','tcg','-cpu','max','-smp','2','-m','3072',
      '-display','none','-monitor','none','-no-reboot','-serial','file:/out/vrr-vm-serial.log',
      '-kernel','/out/vmlinuz','-initrd','/out/initramfs.img',
      '-append',BASE_ARGS+' amdgpu.ods_vrr_59_60=0 ods.slot=baseline',
      '-device','qemu-xhci','-drive','if=none,id=labusb,format=raw,readonly=on,file=/src/artifacts/usb-lab/opendecksight-lab.img',
      '-device','usb-storage,drive=labusb','-drive','if=none,id=internal,format=raw,file='+str(canary),
      '-device','nvme,drive=internal,serial=ODS-VRR-CANARY','-device','virtio-rng-pci',
      '-nic','user,model=e1000,hostfwd=tcp:127.0.0.1:2233-:22']
with (out/'vrr-vm-qemu.log').open('w') as log:
    vm=subprocess.Popen(args,stdout=log,stderr=log)
    try:
        deadline=time.monotonic()+600
        while time.monotonic()<deadline:
            if vm.poll() is not None: raise RuntimeError('VM exited before SSH; inspect logs')
            try:
                check=subprocess.run(ssh+['true'],capture_output=True,timeout=5)
                if not check.returncode: break
            except subprocess.TimeoutExpired: pass
            time.sleep(3)
        else: raise RuntimeError('VM SSH timeout')
        print('Virtual guest booted; checking driver and isolation.',flush=True)
        program=r'''
import glob,hashlib,json,pathlib,subprocess
P=pathlib.Path
metadata=json.loads(P('/etc/ods-vrr-experiment.json').read_text())
release=metadata['kernel_release']
module=P('/usr/lib/modules')/release/'kernel/drivers/gpu/drm/amd/amdgpu/amdgpu.ko'
assert hashlib.sha256(module.read_bytes()).hexdigest()==metadata['files']['amdgpu.ko']['sha256']
binary=P('/usr/local/bin/ods-visual-ab')
assert hashlib.sha256(binary.read_bytes()).hexdigest()==metadata['files']['ods-visual-ab']['sha256']
subprocess.run(['modprobe','amdgpu'],check=True,capture_output=True)
assert P('/sys/module/amdgpu/parameters/ods_vrr_59_60').read_text().strip()=='N'
assert not glob.glob('/dev/nvme*')
controllers=[p for p in P('/sys/bus/pci/devices').iterdir() if (p/'class').read_text().strip()=='0x010802']
assert controllers and all(not(p/'driver').exists() for p in controllers)
assert not any(l.split()[0].startswith('/dev/') and l.split()[1] not in ('/dev','/dev/pts') for l in P('/proc/mounts').read_text().splitlines())
assert len(P('/proc/swaps').read_text().splitlines())==1
preview=subprocess.run([str(binary),'--preview'],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
assert preview.returncode==0
refusal=subprocess.run([str(binary),'--experiment','/dev/dri/card0'],capture_output=True,text=True)
assert refusal.returncode!=0
print(json.dumps({'module_loaded':True,'module_and_binary_hashes_verified':True,'override_disabled':True,
                 'storage_isolation_verified':True,'preview_runs':True,'wrong_display_refused':True,
                 'kernel_log':subprocess.check_output(['dmesg'],text=True)},indent=2))
'''
        result=subprocess.run(ssh+['python3 -B -'],input=program,text=True,capture_output=True,timeout=90)
        if result.returncode:
            (out/'vrr-vm-error.log').write_text(result.stdout+result.stderr)
            raise RuntimeError('VM checks failed; inspect vrr-vm-error.log')
        report=json.loads(result.stdout)
        report['scope']='QEMU direct kernel/initramfs boot and module load without AMD hardware; no physical display validation'
        report['initramfs_sha256']=sha(out/'initramfs.img')
        subprocess.run(ssh+['ods-poweroff'],capture_output=True,timeout=15)
        vm.wait(timeout=60)
        assert vm.returncode==0
    finally:
        if vm.poll() is None:
            vm.terminate()
            try: vm.wait(timeout=10)
            except subprocess.TimeoutExpired: vm.kill();vm.wait()
report['internal_storage_canary_unchanged']=sha(canary)==before
assert report['internal_storage_canary_unchanged']
(out/'vrr-vm-report.json').write_text(json.dumps(report,indent=2)+'\n')
print('Virtual module-load, default-off, refusal and storage checks passed.')
