from pathlib import Path
import struct
import unittest

from opendecksight.container import (SIGNATURE_HASHES, build_container, der_sequence,
                                    extract_signatures, pack_record, parse_pe, pe_checksum)
from opendecksight.firmware import bios_image, sha256


class ContainerTests(unittest.TestCase):
    def test_record_extent_is_from_end_of_header(self):
        for length in (0, 1, 7, 8, 9, 31, 32, 256, 0xB05A):
            record = pack_record("BIOSIMG", b"x" * length)
            total, payload = struct.unpack_from("<II", record, 16)
            self.assertEqual(len(record) % 32, 0)
            self.assertEqual((total, payload), (len(record) - 24, length))
            self.assertEqual(record[24:24 + length], b"x" * length)
            self.assertFalse(any(record[24 + length:]))

    def test_der_bounds_and_alignment(self):
        self.assertEqual(der_sequence(bytes.fromhex("30 03 02 01 00 00 00")), bytes.fromhex("30 03 02 01 00"))
        for data in (b"", bytes.fromhex("30 80"), bytes.fromhex("30 04 00"), bytes.fromhex("30 00 01")):
            with self.assertRaises(ValueError):
                der_sequence(data)

    def test_checksum_ignores_field_and_handles_odd_length(self):
        # Checksum at 0; remaining words are 0xffff, 1, 2, yielding 3 + length 9.
        data = bytes.fromhex("ab cd ef 01 ff ff 01 00 02")
        self.assertEqual(pe_checksum(data, 0), 12)
        self.assertEqual(pe_checksum(bytes(4) + data[4:], 0), 12)

    def test_unrecognized_inputs_are_rejected(self):
        with self.assertRaises(ValueError):
            parse_pe(b"MZ" + bytes(62))
        with self.assertRaises(ValueError):
            build_container(b"not stock", b"not r04", {})
        with self.assertRaises(ValueError):
            extract_signatures(b"not r04")


ROOT = Path(__file__).resolve().parents[1]
STOCK = ROOT / "artifacts/extracted/stock/usr/share/jupiter_bios/F7A0133_sign.fd"
RELEASE = ROOT / "artifacts/extracted/r04/bios/F7A0133_DeckSight_signed_r04.fd"


@unittest.skipUnless(STOCK.exists() and RELEASE.exists(), "optional pinned artifacts are not downloaded")
class ArtifactContainerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stock, cls.release = STOCK.read_bytes(), RELEASE.read_bytes()
        cls.signatures = extract_signatures(cls.release)

    def test_named_signature_resources_and_container_reproduction(self):
        self.assertEqual({n: sha256(b) for n, b in self.signatures.items()}, SIGNATURE_HASHES)
        # Isolate container rebuilding; the separate end-to-end build generates BIOSIMG from stock.
        result = build_container(self.stock, bios_image(self.release), self.signatures)
        self.assertEqual(result, self.release)

    def test_pe_checksums_match_existing_independent_artifacts(self):
        for data in (self.stock, self.release):
            pe = parse_pe(data)
            stored, = struct.unpack_from("<I", data, pe.checksum_offset)
            self.assertEqual(pe_checksum(data, pe.checksum_offset), stored)

    def test_signature_tampering_is_rejected(self):
        bad = dict(self.signatures)
        bad["bioscer.sig"] = bytes(256)
        with self.assertRaisesRegex(ValueError, "signature resource hash mismatch"):
            build_container(self.stock, bios_image(self.release), bad)


if __name__ == "__main__":
    unittest.main()
