"""The AUX capability reader must stay bounded and reject incomplete evidence."""

import unittest
from unittest.mock import patch

from opendecksight.dpcd import decode_receiver_caps, read_receiver_caps


class ReceiverCapsTests(unittest.TestCase):
    def test_msa_capability_bit_is_independent_of_oui_bit(self):
        data = bytearray(16)
        data[7] = 0x80
        self.assertFalse(decode_receiver_caps(data)["msa_timing_parameters_ignored"])
        data[7] = 0x40
        self.assertTrue(decode_receiver_caps(data)["msa_timing_parameters_ignored"])

    def test_extended_caps_are_reported_without_following_them(self):
        data = bytearray(16)
        data[14] = 0x80
        with patch("opendecksight.dpcd.os.pread", return_value=bytes(data)) as read:
            raw, decoded = read_receiver_caps(9)
        read.assert_called_once_with(9, 16, 0)
        self.assertEqual(raw, data)
        self.assertTrue(decoded["extended_receiver_caps_present"])

    def test_short_read_is_not_zero_capability(self):
        with patch("opendecksight.dpcd.os.pread", return_value=b"\0" * 7):
            with self.assertRaises(ValueError):
                read_receiver_caps(9)

    def test_read_error_is_propagated(self):
        with patch("opendecksight.dpcd.os.pread", side_effect=PermissionError()):
            with self.assertRaises(PermissionError):
                read_receiver_caps(9)


if __name__ == "__main__":
    unittest.main()
