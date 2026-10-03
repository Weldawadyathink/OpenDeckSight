import struct
import unittest

from opendecksight import edid, firmware


class FirmwareTests(unittest.TestCase):
    def record(self, name=b"BIOSIMG", payload=b"hello"):
        return bytes(8) + b"$_IFLASH_" + name + struct.pack("<II", len(payload), len(payload)) + payload

    def test_container_extracts_bounded_payload(self):
        record = firmware.chunks(b"prefix" + self.record())[0]
        self.assertEqual((record.name, record.payload_offset, record.data), ("BIOSIMG", 38, b"hello"))

    def test_nested_container_is_found(self):
        records = firmware.chunks(self.record(b"DRV_IMG", self.record()))
        self.assertEqual([x.name for x in records], ["DRV_IMG", "BIOSIMG"])

    def test_truncated_and_duplicate_records_rejected(self):
        for data in (self.record()[:-1], self.record() + self.record(), self.record(b"../EVIL")):
            with self.assertRaises(ValueError):
                firmware.chunks(data)

    def test_diff_boundaries(self):
        self.assertEqual(firmware.diff_spans(b"abcde", b"XbYdZ"), [(0, 1), (2, 3), (4, 5)])
        self.assertEqual(firmware.diff_spans(b"abcde", b"XbYdZ", 1), [(0, 5)])
        self.assertEqual(firmware.diff_spans(b"same", b"same"), [])
        with self.assertRaises(ValueError):
            firmware.diff_spans(b"a", b"ab")

    def test_wrong_firmware_never_patched(self):
        for data in (b"bad", bytes(0x1000000)):
            with self.assertRaises(ValueError):
                firmware.build_r04_ec_reproduction(data)

    def test_edid_profile_and_checksum(self):
        data = firmware.r04_edid()
        result = edid.decode(data)
        self.assertEqual(result["vendor"], "DSO")
        self.assertEqual(result["product"], 0x5001)
        self.assertEqual(result["timings"][0]["width"], 1080)
        self.assertEqual(result["timings"][0]["height"], 1920)
        self.assertAlmostEqual(result["timings"][0]["refresh_hz"], 60.0003352442)
        self.assertEqual(result["cta_blocks"][0]["eotf_flags"], 5)
        bad = bytearray(data)
        bad[54] ^= 1
        with self.assertRaises(ValueError):
            edid.decode(bad)
        with self.assertRaises(ValueError):
            edid.decode(data[:128])

    def test_ec_checksum_excludes_bootloader_and_checksum_field(self):
        data = bytearray(firmware.EC_SIZE)
        data[1] = 23
        data[0x2000] = 7
        data[0x1F7FD] = 9
        data[0x1F7FE] = 25
        self.assertEqual(firmware.ec_checksum(data), 16)


if __name__ == "__main__":
    unittest.main()
