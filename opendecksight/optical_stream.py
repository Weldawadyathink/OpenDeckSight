"""Strict parser for the binary Pico optical protocol, without resynchronization."""
import array
import struct
import sys
import zlib

HEADER=struct.Struct('<IHHIIQII')
BEGIN=struct.Struct('<8I')
END=struct.Struct('<7I2Q')
MAGIC=0x4353444F


def exact(stream,n):
    out=bytearray()
    while len(out)<n:
        chunk=stream.read(n-len(out))
        if not chunk: raise EOFError('Incomplete or timed-out optical stream')
        out.extend(chunk)
    return bytes(out)


def packet(stream):
    header=exact(stream,HEADER.size)
    magic,version,kind,seq,size,index,crc,hcrc=HEADER.unpack(header)
    if magic!=MAGIC or version!=1 or zlib.crc32(header[:28])!=hcrc:
        raise ValueError('Invalid header or header CRC')
    if kind not in (1,2,3) or size>4096:
        raise ValueError('Invalid packet kind/size')
    payload=exact(stream,size)
    if zlib.crc32(payload)!=crc: raise ValueError('Payload CRC mismatch')
    return kind,seq,index,payload


def read_capture(stream,on_begin=None):
    kind,seq,index,payload=packet(stream)
    if (kind,seq,index,len(payload))!=(1,0,0,BEGIN.size):
        raise ValueError('Missing begin packet')
    fields=BEGIN.unpack(payload)
    info=dict(zip(('rate','requested','gpio','block_samples','ring_samples',
                   'adc_clock','adc_div','firmware_revision'),fields))
    if not (info['rate']==100000 and 0<info['requested']<=6000000 and
            info['gpio']==26 and info['block_samples']==2048 and info['ring_samples']==16384 and
            info['adc_clock']==48000000 and info['adc_div']==479<<8 and info['firmware_revision']==1):
        raise ValueError('Unexpected acquisition configuration')
    if on_begin: on_begin(info)
    samples=array.array('H')
    blocks=0
    while True:
        kind,seq,index,payload=packet(stream)
        if seq!=blocks or index!=len(samples): raise ValueError('Missing, duplicated or reordered samples')
        if kind==2:
            expected=min(info['block_samples'],info['requested']-len(samples))*2
            if len(payload)!=expected or not expected: raise ValueError('Invalid data block length')
            values=array.array('H');values.frombytes(payload)
            if sys.byteorder!='little': values.byteswap()
            if any(v&0xF000 for v in values): raise ValueError('ADC error/reserved sample bits')
            samples.extend(values);blocks+=1
        elif kind==3:
            if len(payload)!=END.size: raise ValueError('Invalid end packet')
            end=dict(zip(('flags','sent','produced','fcs','cs','dma_ctrl','max_backlog',
                          'started_us','stopped_us'),END.unpack(payload)))
            if end['flags']: raise ValueError('Instrument failure flags: '+hex(end['flags']))
            if len(samples)!=info['requested'] or end['sent']!=len(samples): raise ValueError('Incomplete sample count')
            if end['produced']<len(samples) or end['produced']>len(samples)+info['ring_samples']:
                raise ValueError('Invalid produced sample count')
            if end['fcs']&0xC00 or end['cs']&0x600 or end['dma_ctrl']&0xE0000000:
                raise ValueError('Hardware error status')
            if end['max_backlog']>info['ring_samples']: raise ValueError('Ring overwrite')
            if end['stopped_us']<end['started_us']: raise ValueError('Invalid acquisition timestamps')
            return {'config':info,'end':end,'blocks':blocks,'sample_count':len(samples)},samples
        else: raise ValueError('Unexpected begin packet inside stream')
