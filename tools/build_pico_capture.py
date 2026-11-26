#!/usr/bin/env python3
"""Build a pinned SDK optical recorder; create UF2 locally, never flash a device."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess

ROOT=Path(__file__).resolve().parents[1]
SDK_COMMIT="a1438dff1d38bd9c65dbd693f0e5db4b9ae91779"
USB_COMMIT="86ad6e56c1700e85f1c5678607a762cfe3aa2f47"


def uf2(binary):
    if not 264<=len(binary)<=2*1024*1024:
        raise ValueError("RP2040 image size invalid")
    stack,entry=struct.unpack_from('<II',binary,256)
    if not (0x20000000<stack<=0x20042000 and stack%8==0 and entry&1 and
            0x10000000<=(entry&~1)<0x10000000+len(binary)):
        raise ValueError("RP2040 vector table invalid")
    blocks=(len(binary)+255)//256
    result=bytearray()
    for i in range(blocks):
        header=struct.pack('<8I',0x0a324655,0x9e5d5157,0x2000,
                           0x10000000+i*256,256,i,blocks,0xe48bff56)
        payload=binary[i*256:(i+1)*256].ljust(256,b'\0')
        result.extend(header+payload+bytes(220)+struct.pack('<I',0x0ab16f30))
    return bytes(result)


def main():
    sdk=ROOT/'.tools/pico-sdk'
    for path,commit in ((sdk,SDK_COMMIT),(sdk/'lib/tinyusb',USB_COMMIT)):
        actual=subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()
        if actual!=commit: raise ValueError('SDK dependency revision mismatch')
    build=ROOT/'.tools/pico-build'
    output=ROOT/'artifacts/vrr/pico-continuous'
    output.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ,PICO_SDK_PATH=str(sdk))
    with (output/'build.log').open('w') as log:
        subprocess.run(['cmake','-S',str(ROOT/'lab/pico'),'-B',str(build),'-G','Ninja',
                        '-DPICO_BOARD=pico_w','-DPICO_NO_PICOTOOL=1','-DCMAKE_BUILD_TYPE=Release'],
                       env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
        subprocess.run(['cmake','--build',str(build),'-j','6'],stdout=log,stderr=subprocess.STDOUT,check=True)
    binary=(build/'ods-optical-capture.bin').read_bytes()
    data=uf2(binary)
    name=output/'ods-optical-capture.uf2'
    name.write_bytes(data)
    manifest={'sdk_tag':'2.2.0','sdk_commit':SDK_COMMIT,'tinyusb_commit':USB_COMMIT,
              'sdk_url':'https://github.com/raspberrypi/pico-sdk',
              'tinyusb_url':'https://github.com/hathach/tinyusb',
              'compiler':subprocess.check_output(['arm-none-eabi-gcc','--version'],text=True).splitlines()[0],
              'binary_sha256':hashlib.sha256(binary).hexdigest(),
              'uf2_sha256':hashlib.sha256(data).hexdigest(),'uf2_bytes':len(data),
              'sources':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in sorted((ROOT/'lab/pico').iterdir()) if p.is_file()}}
    (output/'build-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest,indent=2))


if __name__=='__main__': main()
