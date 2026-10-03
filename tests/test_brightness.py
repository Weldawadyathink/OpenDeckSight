import unittest
from pathlib import Path
from unittest.mock import patch

from opendecksight.brightness import (
    COMMAND, DATA, REGISTER, TARGET, Controller, Mailbox, brightness_value, live_mailbox, packets,
)


class FakeRegisters:
    def __init__(self, stuck=False):
        self.writes = []
        self.stuck = stuck

    def read8(self, offset):
        return 0x80 if self.stuck else 0

    def write8(self, offset, value):
        self.writes.append((offset, 1, value))

    def write32(self, offset, value):
        self.writes.append((offset, 4, value))


class FakeClock:
    now = 0

    def read(self):
        return self.now

    def sleep(self, amount):
        self.now += amount


class BrightnessTests(unittest.TestCase):
    def test_unsupported_host_rejected_before_any_device_open(self):
        for system, machine in (("Darwin", "arm64"), ("Linux", "aarch64")):
            with patch("opendecksight.brightness.platform.system", return_value=system), \
                 patch("opendecksight.brightness.platform.machine", return_value=machine), \
                 patch("opendecksight.brightness.os.open") as device_open:
                with self.assertRaises(RuntimeError):
                    with live_mailbox(Path("/unused/brightness")):
                        self.fail("unsupported host obtained a live mailbox")
                device_open.assert_not_called()

    def test_failed_identity_guard_rejected_before_lock_or_memory_open(self):
        with patch("opendecksight.brightness.validate_device", side_effect=RuntimeError("wrong panel")), \
             patch("opendecksight.brightness.os.open") as device_open:
            with self.assertRaises(RuntimeError):
                with live_mailbox(Path("/unused/brightness")):
                    self.fail("failed validation obtained a live mailbox")
            device_open.assert_not_called()

    def test_observed_packet_vectors(self):
        self.assertEqual(packets(0, 65535), ((0x70, b"\x51\x02\x80\x00"), (0x6C, b"\x39\x03\x00\x00")))
        self.assertEqual(packets(32768, 65535)[0][1], b"\x51\x05\xc0\x00")
        self.assertEqual(packets(65535, 65535)[0][1], b"\x51\x09\x00\x00")
        self.assertEqual(brightness_value(0xFFFFFFFF, 1), 0x900)

    def test_scaling_monotonic_and_bounded(self):
        values = [brightness_value(i, 65535) for i in range(65536)]
        self.assertEqual(values, sorted(values))
        self.assertEqual((min(values), max(values)), (0x280, 0x900))
        for raw, maximum in ((-1, 1), (1, 0), (1, -1), (2**32, 1), (1, 2**32)):
            with self.assertRaises(ValueError):
                brightness_value(raw, maximum)

    def test_exact_mmio_sequence_payload_before_header(self):
        io = FakeRegisters()
        Mailbox(io).set_brightness(0, 65535)
        self.assertEqual(io.writes, [
            (TARGET, 1, 0xC0), (REGISTER, 1, 0x70), (DATA, 4, 0x00800251), (COMMAND, 1, 0x84),
            (TARGET, 1, 0xC0), (REGISTER, 1, 0x6C), (DATA, 4, 0x00000339), (COMMAND, 1, 0x84)])

    def test_already_busy_times_out_without_writes(self):
        io, clock = FakeRegisters(stuck=True), FakeClock()
        with self.assertRaises(TimeoutError):
            Mailbox(io, clock.read, clock.sleep).set_brightness(1, 100)
        self.assertEqual(io.writes, [])
        self.assertGreaterEqual(clock.now, 0.2)

    def test_payload_timeout_does_not_submit_header(self):
        class StuckAfterTrigger(FakeRegisters):
            def write8(self, offset, value):
                super().write8(offset, value)
                if offset == COMMAND:
                    self.stuck = True
        io, clock = StuckAfterTrigger(), FakeClock()
        with self.assertRaises(TimeoutError):
            Mailbox(io, clock.read, clock.sleep).set_brightness(1, 100)
        self.assertEqual(len(io.writes), 4)
        self.assertEqual(io.writes[1], (REGISTER, 1, 0x70))

    def test_failed_write_retries_and_resume_reapplies(self):
        class Transport:
            calls = 0
            fail = False

            def set_brightness(self, raw, maximum):
                self.calls += 1
                if self.fail:
                    raise TimeoutError
        transport = Transport()
        controller = Controller(transport)
        self.assertTrue(controller.tick(50, 100, 0))
        self.assertFalse(controller.tick(50, 100, 0.2))
        self.assertTrue(controller.tick(50, 100, 5))
        transport.fail = True
        with self.assertRaises(TimeoutError):
            controller.tick(50, 100, 10)
        transport.fail = False
        self.assertTrue(controller.tick(50, 100, 10.2))
        self.assertTrue(controller.tick(50, 200, 10.4))
        self.assertEqual(transport.calls, 5)


if __name__ == "__main__":
    unittest.main()
