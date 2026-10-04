from pathlib import Path
import unittest

from opendecksight.ec_trace import Machine, inspect, trace_record
from opendecksight.firmware import EC_BASES, EC_SIZE, R04_PANEL_INIT


def program(hex_bytes):
    code = bytes.fromhex(hex_bytes)
    return Machine(code + bytes(65536 - len(code)))


class MachineTests(unittest.TestCase):
    def test_add_carry_and_exchange(self):
        # 0xff + 1 = 0x100; ADDC propagates the carry into B after XCH.
        m = program("74 ff 24 01 75 f0 00 c5 f0 34 00 22")
        m.run(0)
        self.assertEqual((m.a, m.direct[0xF0], m.carry), (1, 0, 0))

    def test_multiply_and_pointer_carry(self):
        # Address 0x6e55 + 5*171 = 0x71ac, including both carries.
        m = program("90 6e 55 74 ab 75 f0 05 a4 25 82 f5 82 e5 f0 35 83 f5 83 22")
        m.run(0)
        self.assertEqual(m.dptr, 0x71AC)

    def test_code_and_external_memory_are_separate(self):
        m = program("90 00 00 e4 93 90 12 34 f0 22")
        m.run(0)
        self.assertEqual(m.xram[0x1234], 0x90)
        self.assertEqual(m.code[0], 0x90)
        self.assertEqual(m.code_reads, [0])

    def test_call_and_signed_relative_branch(self):
        # MOV A,2; call decrement; JNZ back to call; RET.
        m = program("74 02 12 00 08 70 fb 22 94 01 22")
        m.run(0)
        self.assertEqual(m.a, 0)

    def test_reject_unknown_instruction_and_infinite_loop(self):
        with self.assertRaisesRegex(ValueError, "unsupported opcode"):
            program("a5").run(0)
        with self.assertRaisesRegex(ValueError, "instruction limit"):
            program("80 fe").run(0, max_steps=10)


R04 = Path(__file__).resolve().parents[1] / "artifacts/extracted/r04/chunks/BIOSIMG.bin"


@unittest.skipUnless(R04.exists(), "optional pinned artifact is not downloaded")
class ArtifactTraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = R04.read_bytes()
        cls.report = inspect(cls.image)  # Checks the complete artifact hash.

    def test_original_instructions_produce_expected_bus_words(self):
        for bank in self.report["banks"]:
            self.assertEqual(len(bank["records"]), len(R04_PANEL_INIT))
            for record, (register, word) in zip(bank["records"], R04_PANEL_INIT):
                if register in (0xAA, 0xFF):
                    continue
                # Independent semantic table encoder versus interpreted code.
                value = word.to_bytes(4, "little" if bank["bank"] == 0 else "big")
                self.assertEqual(record["bytes_hex"], (bytes([register]) + value).hex(" "))
                self.assertEqual((record["device_argument"], record["port_argument"], record["length"]),
                                 (1, "0xc0", 5))

    def test_delay_counter_and_forced_selector(self):
        for bank, counter in zip(self.report["banks"], (60, 0)):
            self.assertEqual(bank["records"][3]["counter"], counter)
            self.assertEqual(bank["records"][3]["next_index"], 4)
            self.assertEqual([r["selector"] for r in bank["selector_branch"]], [1, 1])
            for probe in bank["counter_probes"]:
                self.assertEqual(probe["after"], max(0, probe["initial"] - 1))
                self.assertEqual(probe["reached_state_dispatch"], probe["initial"] == 0)

    def test_selector_two_reads_different_table(self):
        ec = self.image[EC_BASES[0]:EC_BASES[0] + EC_SIZE]
        record = trace_record(ec, 0, selector=2)
        self.assertEqual(record["code_reads"], ["0x6a4a", "0x6a4e", "0x6a4d", "0x6a4c", "0x6a4b"])


if __name__ == "__main__":
    unittest.main()
