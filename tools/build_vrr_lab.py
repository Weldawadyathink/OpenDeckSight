#!/usr/bin/env python3
"""Build a local driver/visual-test USB update. VRR is OFF in its boot arguments."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from opendecksight.lab_update import sha, validate_manifest

BUILD_SOURCES = ('lab/vrr/ods_vrr_guard.h','lab/vrr/0001-ods-vrr-59-60.patch',
                 'lab/vrr/visual_ab.c','lab/usb/fixed_present.c','tools/prepare_vrr_patch.py',
                 'lab/vrr/build-driver.sh','lab/vrr/Containerfile','research/vrr-driver-build.json')


def source_hashes():
    return {n:sha(ROOT/n) for n in BUILD_SOURCES}


def record_build(out):
    lock=json.loads((ROOT/'research/vrr-driver-build.json').read_text())
    vermagic=(out/'vermagic.txt').read_text().strip()
    if vermagic.split()[0]!=lock['kernel_release']:
        raise ValueError('module vermagic does not match the baseline kernel')
    report={'schema':1,'kernel_release':lock['kernel_release'],'vermagic':vermagic,
            'source_sha256':source_hashes(), 'input_provenance':lock,
            'compiler':(out/'compiler.txt').read_text().splitlines()[0],
            'files':{n:{'sha256':sha(out/n),'size':(out/n).stat().st_size}
                     for n in ('amdgpu.ko','ods-visual-ab')}}
    (out/'driver-build.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def fetch(cache,lock):
    cache.mkdir(parents=True,exist_ok=True)
    for name,item in lock['inputs'].items():
        path=cache/name
        if not path.exists():
            headers={}
            if item['url'].startswith('https://ghcr.io/'):
                repo='opengamingcollective/kernel-packages-fedora'
                with urllib.request.urlopen('https://ghcr.io/token?service=ghcr.io&scope=repository:'+repo+':pull',timeout=30) as r:
                    headers['Authorization']='Bearer '+json.load(r)['token']
            request=urllib.request.Request(item['url'],headers=headers)
            with urllib.request.urlopen(request,timeout=120) as response,path.with_suffix('.partial').open('wb') as dest:
                shutil.copyfileobj(response,dest)
            path.with_suffix('.partial').rename(path)
        if path.stat().st_size!=item['size'] or sha(path)!=item['sha256']:
            raise ValueError('input integrity check failed: '+name)


def cpio_entry(name,data,mode,index):
    encoded=name.encode()+b'\0'
    fields=[index,mode,0,0,1,0,len(data),0,0,0,0,len(encoded),0]
    header=b'070701'+b''.join(f'{v:08x}'.encode() for v in fields)
    prefix=header+encoded
    return prefix+b'\0'*((-len(prefix))%4)+data+b'\0'*((-len(data))%4)


def package(out,base):
    report=json.loads((out/'driver-build.json').read_text())
    if report['source_sha256']!=source_hashes():
        raise ValueError('build sources changed; rebuild before packaging')
    for name,entry in report['files'].items():
        if sha(out/name)!=entry['sha256'] or (out/name).stat().st_size!=entry['size']:
            raise ValueError('built file integrity mismatch: '+name)
    with tarfile.open(base) as archive:
        manifest=validate_manifest(archive.extractfile('manifest.json').read())
        if manifest['kernel_release']!=report['kernel_release']:
            raise ValueError('base kernel release mismatch')
        for name,entry in manifest['files'].items():
            with archive.extractfile(name) as src,(out/name).open('wb') as dest:
                shutil.copyfileobj(src,dest)
            if sha(out/name)!=entry['sha256'] or (out/name).stat().st_size!=entry['size']:
                raise ValueError('base payload integrity mismatch')
    entries={
        'usr/lib/modules/'+report['kernel_release']+'/kernel/drivers/gpu/drm/amd/amdgpu/amdgpu.ko':
            ((out/'amdgpu.ko').read_bytes(),stat.S_IFREG|0o644),
        'usr/local/bin':(b'',stat.S_IFDIR|0o755),
        'usr/local/bin/ods-visual-ab':((out/'ods-visual-ab').read_bytes(),stat.S_IFREG|0o755),
        'usr/local/lib/opendecksight/lab_config.py':((ROOT/'opendecksight/lab_config.py').read_bytes(),stat.S_IFREG|0o644),
        'etc/ods-vrr-experiment.json':((out/'driver-build.json').read_bytes(),stat.S_IFREG|0o644),
    }
    extra=b''.join(cpio_entry(n,d,m,i+1) for i,(n,(d,m)) in enumerate(entries.items()))
    extra+=cpio_entry('TRAILER!!!',b'',0,len(entries)+1)
    with (out/'initramfs.img').open('ab') as stream:
        stream.write(gzip.compress(extra,compresslevel=1,mtime=0))
    manifest['boot_args']=['amdgpu.ods_vrr_59_60=0']
    manifest['experimental_driver']={'enabled_at_boot':False,'build_manifest_sha256':sha(out/'driver-build.json'),
                                     'base_bundle_sha256':sha(base),'source_commit':report['input_provenance']['source_commit']}
    manifest['files']={n:{'size':(out/n).stat().st_size,'sha256':sha(out/n)} for n in ('vmlinuz','initramfs.img')}
    raw=(json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode()
    validate_manifest(raw)
    (out/'update-manifest.json').write_bytes(raw)
    with tarfile.open(out/'opendecksight-vrr-update.tar','w') as archive:
        item=tarfile.TarInfo('manifest.json');item.size=len(raw);item.mode=0o644
        archive.addfile(item,io.BytesIO(raw))
        for name in manifest['files']: archive.add(out/name,arcname=name)
    print('Created '+str(out/'opendecksight-vrr-update.tar')+'; experimental VRR OFF, no device contacted.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reuse-build',action='store_true',help='package existing binaries only if their source hashes still match')
    p.add_argument('--output-dir',type=Path,default=ROOT/'artifacts/vrr/visual-ab')
    p.add_argument('--base-bundle',type=Path,default=ROOT/'artifacts/usb-lab/opendecksight-lab-update.tar')
    a=p.parse_args();out=a.output_dir.resolve()
    if (ROOT/'artifacts').resolve() not in out.parents: p.error('keep outputs in ignored artifacts/')
    out.mkdir(parents=True,exist_ok=True)
    if not a.reuse_build:
        lock=json.loads((ROOT/'research/vrr-driver-build.json').read_text())
        cache=ROOT/'artifacts/vrr/kernel-build-inputs';fetch(cache,lock)
        subprocess.run(['docker','build','--platform','linux/amd64','-t','opendecksight-vrr-builder',
                        '-f',str(ROOT/'lab/vrr/Containerfile'),str(ROOT/'lab/vrr')],check=True)
        with (out/'amdgpu-build.log').open('w') as log:
            subprocess.run(['docker','run','--rm','--platform','linux/amd64',
                '--mount',f'type=bind,src={ROOT},dst=/src,readonly',
                '--mount',f'type=bind,src={cache},dst=/inputs,readonly',
                '--mount',f'type=bind,src={out},dst=/out',
                'opendecksight-vrr-builder','/src/lab/vrr/build-driver.sh'],stdout=log,stderr=subprocess.STDOUT,check=True)
        if (out/'applied.patch').read_bytes()!=(ROOT/'lab/vrr/0001-ods-vrr-59-60.patch').read_bytes():
            raise ValueError('generated patch differs from checked-in reviewed patch')
        record_build(out)
    package(out,a.base_bundle)


if __name__=='__main__': main()
