import io
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib

from opendecksight.optical_stream import read_capture
from tools.build_pico_capture import uf2


def packet(kind, seq, index, payload):
    header = struct.pack('<IHHIIQI', 0x4353444F, 1, kind, seq, len(payload), index, zlib.crc32(payload))
    return header + struct.pack('<I', zlib.crc32(header)) + payload


def recording(flags=0, values=None, **status):
    values = values if values is not None else [123] * 2049
    packets = [packet(1, 0, 0, struct.pack('<8I', 100000, len(values), 26, 2048, 16384, 48000000, 479 << 8, 1))]
    for i in range(0, len(values), 2048):
        block = values[i:i+2048]
        packets.append(packet(2, i//2048, i, struct.pack('<' + 'H'*len(block), *block)))
    fields = dict(flags=flags, sent=len(values), produced=len(values)+1, fcs=0x100000D,
                  cs=0x101, dma=0x01000000, backlog=2050, start=100, stop=20600)
    fields.update(status)
    packets.append(packet(3, len(packets)-1, len(values), struct.pack('<7I2Q', *fields.values())))
    return packets


class StreamTests(unittest.TestCase):
    def test_complete_and_partial_transport_reads(self):
        class Fragmented(io.BytesIO):
            def read(self, n): return super().read(min(n, 17))
        result, values = read_capture(Fragmented(b''.join(recording())))
        self.assertEqual(len(values), 2049)
        self.assertEqual(result['blocks'], 2)

    def test_missing_duplicate_reordered_and_truncated_packets(self):
        p = recording()
        damaged = [p[:1]+p[2:], p[:2]+p[1:], [p[0],p[2],p[1],p[3]], p[:-1]]
        for data in damaged:
            with self.subTest(data=len(data)), self.assertRaises((ValueError, EOFError)):
                read_capture(io.BytesIO(b''.join(data)))
        with self.assertRaises(EOFError):
            read_capture(io.BytesIO(b''.join(p)[:-1]))

    def test_crc_damage(self):
        for offset in (4, 28, 100):
            data = bytearray(b''.join(recording())); data[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                read_capture(io.BytesIO(data))

    def test_instrument_failures_even_with_valid_crcs(self):
        cases = [dict(flags=1 << n) for n in range(8)]
        cases += [dict(fcs=0x400),dict(fcs=0x800),dict(cs=0x200),dict(cs=0x400),
                  dict(dma=0x20000000),dict(backlog=16385),dict(produced=0),dict(sent=0),dict(stop=0)]
        for status in cases:
            with self.subTest(status=status), self.assertRaises(ValueError):
                read_capture(io.BytesIO(b''.join(recording(**status))))
        with self.assertRaises(ValueError):
            read_capture(io.BytesIO(b''.join(recording(values=[0x8000]))))

    @unittest.skipUnless(shutil.which('cc'), 'C compiler unavailable')
    def test_firmware_crc_and_header_layout(self):
        root = Path(__file__).resolve().parents[1]
        source = '''#include <stdio.h>
        #include "protocol.h"
        int main(void) {
            const char payload[]="123456789";
            struct ods_header h={.magic=ODS_MAGIC,.version=1,.type=2,
              .sequence=3,.bytes=9,.sample_index=4096,.payload_crc=ods_crc32(payload,9)};
            h.header_crc=ods_crc32(&h,28);
            fwrite(&h,1,sizeof(h),stdout); fwrite(payload,1,9,stdout);
        }'''
        with tempfile.TemporaryDirectory() as temp:
            src=Path(temp)/'crc.c'; src.write_text(source)
            exe=Path(temp)/'crc'
            subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-I',str(root/'lab/pico'),str(src),'-o',str(exe)],check=True)
            actual=subprocess.check_output([str(exe)])
        self.assertEqual(actual,packet(2,3,4096,b'123456789'))
        self.assertEqual(zlib.crc32(b'123456789'),0xcbf43926)

    def test_uf2_address_payload_and_vector_checks(self):
        binary=bytearray(777)
        struct.pack_into('<II',binary,256,0x20042000,0x10000109)
        output=uf2(binary)
        self.assertEqual(len(output),4*512)
        recovered=bytearray()
        for i in range(4):
            block=output[i*512:(i+1)*512]
            self.assertEqual(struct.unpack('<8I',block[:32]),
                             (0x0a324655,0x9e5d5157,0x2000,0x10000000+i*256,256,i,4,0xe48bff56))
            self.assertEqual(struct.unpack('<I',block[-4:])[0],0x0ab16f30)
            recovered.extend(block[32:288])
        self.assertEqual(recovered[:len(binary)],binary)
        struct.pack_into('<I',binary,256,0)
        with self.assertRaises(ValueError): uf2(binary)


if __name__ == '__main__': unittest.main()
