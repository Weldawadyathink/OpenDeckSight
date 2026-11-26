#!/usr/bin/env python3
"""Capture a bounded continuous Pico recording through native USB serial."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from opendecksight.optical_stream import read_capture


class RecordingReader:
    def __init__(self,port,file): self.port,self.file=port,file
    def read(self,n):
        data=self.port.read(n)
        self.file.write(data)
        return data


def capture(port_name,samples,path,on_begin=None):
    import serial
    with serial.Serial(port_name,115200,timeout=3,write_timeout=3,exclusive=True) as port:
        time.sleep(.15)
        port.reset_input_buffer()
        port.write(b'INFO\n');port.flush()
        identity=json.loads(port.readline())
        if identity.get('firmware')!='ods-optical-capture' or identity.get('protocol')!=1:
            raise ValueError('Wrong Pico firmware')
        with Path(path).open('xb') as raw:
            port.write(('CAPTURE '+str(samples)+'\n').encode());port.flush()
            try: result,values=read_capture(RecordingReader(port,raw),on_begin)
            except BaseException:
                port.write(b'!\n');port.flush()
                raise
    if result['config']['requested']!=samples: raise ValueError('Requested sample count mismatch')
    result['raw_sha256']=hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return result,values


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',required=True)
    p.add_argument('--samples',type=int,default=2500000)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if not 0<a.samples<=6000000: p.error('samples must be 1..6000000')
    started=time.monotonic()
    def ready(info): print(json.dumps({'capture_started':True,'samples':info['requested']}),flush=True)
    result,_=capture(a.port,a.samples,a.output,ready)
    result['host_elapsed_s']=time.monotonic()-started
    a.output.with_suffix('.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
