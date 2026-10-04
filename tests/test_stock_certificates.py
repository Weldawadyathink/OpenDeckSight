import struct
import unittest
import uuid

from tools.inspect_stock_certificates import signature_lists


class SignatureListTests(unittest.TestCase):
    def make_list(self, payload=b"x" * 32):
        kind = uuid.UUID("c1c41626-504c-4092-aca9-41f936934328").bytes_le
        return kind + struct.pack("<III", 44 + len(payload), 0, 16 + len(payload)) + bytes(16) + payload

    def test_concatenated_lists_have_independent_boundaries(self):
        first = self.make_list()
        report = signature_lists(first + self.make_list(b"y" * 32))
        self.assertEqual([r["offset"] for r in report], [0, len(first)])
        self.assertEqual(report[1]["entries"][0]["payload_offset"], len(first) + 44)
        self.assertNotEqual(report[0]["entries"][0]["sha256"], report[1]["entries"][0]["sha256"])

    def test_rejects_truncated_header_and_payload(self):
        for data in (b"x", self.make_list()[:-1]):
            with self.subTest(length=len(data)), self.assertRaises(ValueError):
                signature_lists(data)

    def test_rejects_invalid_list_and_entry_sizes(self):
        for offset, value in ((16, 0), (16, 1000), (20, 1000), (24, 0), (24, 16), (24, 47)):
            data = bytearray(self.make_list())
            struct.pack_into("<I", data, offset, value)
            with self.subTest(offset=offset, value=value), self.assertRaises(ValueError):
                signature_lists(bytes(data))

    def test_empty_database(self):
        self.assertEqual(signature_lists(b""), [])
