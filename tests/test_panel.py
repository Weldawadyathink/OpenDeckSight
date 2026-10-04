import unittest

from opendecksight.panel import decode_table


class PanelTests(unittest.TestCase):
    def test_long_packet_excludes_fifo_padding_and_decodes_scanline(self):
        data = bytes.fromhex("70 00 10 00 44 6c 00 00 03 39 ff 00 00 00 00")
        event = decode_table(data, offset=0)[0]
        self.assertEqual(event["payload_hex"], "44 00 10")
        self.assertEqual(event["scanline"], 16)
        self.assertEqual(event["padding_hex"], "00")

    def test_missing_payload_rejected(self):
        with self.assertRaises(ValueError):
            decode_table(bytes.fromhex("6c 00 00 03 39 ff 00 00 00 00"), offset=0)

    def test_delay_counter_uses_low_byte(self):
        events = decode_table(bytes.fromhex("aa 3c 00 00 00 ab 00 00 01 06 ff 00 00 00 00"), offset=0)
        self.assertEqual(events[0]["value"], 0x3C000000)
        self.assertEqual(events[0]["counter"], 0)
        self.assertEqual(events[1]["counter"], 6)

    def test_missing_terminator_rejected(self):
        with self.assertRaises(ValueError):
            decode_table(bytes.fromhex("aa 00 00 00 3c"), offset=0)


if __name__ == "__main__":
    unittest.main()
