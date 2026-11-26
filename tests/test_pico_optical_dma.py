import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

SPEC = importlib.util.spec_from_file_location(
    "pico_dma_analysis", Path(__file__).resolve().parents[1] / "tools/analyze_pico_optical_dma.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DmaValidationTests(unittest.TestCase):
    def setUp(self):
        raw = struct.pack("<4H", 10, 30, 2000, 2020)
        self.header = {"schema": "pico-optical-dma-v1", "seq": 0, "samples": 4,
                       "sample_rate_nominal_hz": 100_000, "adc_clock_nominal_hz": 48_000_000,
                       "adc_div_register": 479 << 8, "fcs": 0x100000D,
                       "cs": 0x101, "remaining": 0, "dma_ctrl": 0}
        self.chunks = [{"seq": 0, "offset": 0, "hex": raw.hex()}]
        self.end = {"seq": 0, "crc32": zlib.crc32(raw)}

    def test_valid_samples(self):
        self.assertEqual(MODULE.validate_capture(self.header, self.chunks, self.end),
                         (10, 30, 2000, 2020))

    def test_transport_damage(self):
        cases = [([], self.end), (self.chunks * 2, self.end),
                 ([dict(self.chunks[0], offset=1)], self.end),
                 (self.chunks, dict(self.end, crc32=0))]
        for chunks, end in cases:
            with self.subTest(chunks=chunks, end=end), self.assertRaises(ValueError):
                MODULE.validate_capture(self.header, chunks, end)

    def test_hardware_errors(self):
        for key, value in (("fcs", 0x800), ("fcs", 0x400), ("cs", 0x400),
                           ("cs", 0x200), ("remaining", 1), ("dma_ctrl", 0x80000000),
                           ("dma_ctrl", 0x01000000), ("adc_div_register", 0)):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                MODULE.validate_capture(dict(self.header, **{key: value}), self.chunks, self.end)

    def test_sample_error_even_with_valid_crc(self):
        raw = struct.pack("<4H", 10, 0x8000, 2000, 2020)
        with self.assertRaises(ValueError):
            MODULE.validate_capture(self.header, [{"seq": 0, "offset": 0, "hex": raw.hex()}],
                                    {"seq": 0, "crc32": zlib.crc32(raw)})

    def test_missing_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.jsonl"
            path.write_text(json.dumps(dict(self.header, type="capture")) + "\n")
            with self.assertRaises(ValueError):
                MODULE.read_captures(path)

    def test_rise_and_fall_use_optical_shape_not_command_duration(self):
        # A 100-us linear ramp has an 80-us 10-90 width. Change command
        # duration without changing the optical trace: width must not change.
        wave = [100] * 500 + list(range(100, 1101, 100)) + [1100] * 1000
        for state, values in ((1, wave), (0, [1200 - v for v in wave])):
            for command_end in (5200, 5400):
                edge = MODULE.step_width(values, 100_000, (state, 4900, command_end))
                self.assertAlmostEqual(edge["width_10_90_interpolated_us"], 80)
                self.assertLessEqual(edge["width_sampling_bracket_us"][0], 80)
                self.assertGreaterEqual(edge["width_sampling_bracket_us"][1], 80)

    def test_missing_optical_response(self):
        with self.assertRaises(ValueError):
            MODULE.step_width([100] * 2000, 100_000, (1, 5000, 5300))


if __name__ == "__main__":
    unittest.main()
