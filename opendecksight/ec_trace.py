"""Bounded, in-memory interpretation of the recovered 8051 table-loading path.

This is deliberately NOT a general EC emulator. It implements only the integer,
memory and control-flow instructions needed here, assumes register bank zero,
and uses an abstract call stack. Interrupts, peripherals, timing, and unsupported
instructions are not modeled. Only carry is modeled among the arithmetic flags;
these paths do not read the others. No host or device I/O is exposed to firmware.
"""

from .firmware import EC_BASES, EC_SIZE, R04_SHA256, STOCK_SHA256, bios_image, sha256


class Machine:
    def __init__(self, code):
        if len(code) != 0x10000:
            raise ValueError("expected a 64 KiB code window")
        self.code = bytes(code)
        self.direct = bytearray(256)
        self.xram = bytearray(65536)
        self.carry = 0
        self.pc = 0
        self.stack = []
        self.visited = set()
        self.code_reads = []

    @property
    def a(self):
        return self.direct[0xE0]

    @a.setter
    def a(self, value):
        self.direct[0xE0] = value & 255

    @property
    def dptr(self):
        return self.direct[0x82] | self.direct[0x83] << 8

    @dptr.setter
    def dptr(self, value):
        self.direct[0x82] = value & 255
        self.direct[0x83] = value >> 8 & 255

    def fetch(self):
        value = self.code[self.pc]
        self.pc = (self.pc + 1) & 0xFFFF
        return value

    def relative(self, take):
        offset = self.fetch()
        if take:
            self.pc = (self.pc + (offset if offset < 128 else offset - 256)) & 0xFFFF

    def operand(self, opcode):
        low = opcode & 15
        if low == 4:
            return self.fetch()
        if low == 5:
            return self.direct[self.fetch()]
        if low >= 8:
            return self.direct[low - 8]
        raise ValueError("indirect arithmetic is outside this model")

    def run(self, start, *, stops=(), max_steps=20000):
        """Run to a top-level RET or a named boundary; never skip unknown code."""
        self.pc = start
        self.stack = []
        for _ in range(max_steps):
            if self.pc in stops:
                return self.pc
            address = self.pc
            self.visited.add(address)
            op = self.fetch()
            if op == 0x90:  # MOV DPTR,#imm16
                self.dptr = self.fetch() << 8 | self.fetch()
            elif op == 0x74:
                self.a = self.fetch()
            elif op == 0x75:
                dest, value = self.fetch(), self.fetch()
                if dest not in (0x82, 0x83, 0xE0, 0xF0) and dest >= 0x80:
                    raise ValueError("unmodeled SFR write")
                self.direct[dest] = value
            elif op == 0xE5:
                self.a = self.direct[self.fetch()]
            elif op == 0xF5:
                dest = self.fetch()
                if dest not in (0x82, 0x83, 0xE0, 0xF0) and dest >= 0x80:
                    raise ValueError("unmodeled SFR write")
                self.direct[dest] = self.a
            elif 0x78 <= op <= 0x7F:
                self.direct[op - 0x78] = self.fetch()
            elif 0xE8 <= op <= 0xEF:
                self.a = self.direct[op - 0xE8]
            elif 0xF8 <= op <= 0xFF:
                self.direct[op - 0xF8] = self.a
            elif op == 0xE0:
                self.a = self.xram[self.dptr]
            elif op == 0xF0:
                self.xram[self.dptr] = self.a
            elif op == 0x93:
                source = (self.dptr + self.a) & 0xFFFF
                self.code_reads.append(source)
                self.a = self.code[source]
            elif op == 0xA3:
                self.dptr += 1
            elif op == 0xE4:
                self.a = 0
            elif op == 0x04:
                self.a += 1
            elif op == 0x15:
                dest = self.fetch()
                self.direct[dest] = (self.direct[dest] - 1) & 255
            elif op == 0xD3:
                self.carry = 1
            elif op == 0xC3:
                self.carry = 0
            elif op == 0xC5:
                dest = self.fetch()
                self.a, self.direct[dest] = self.direct[dest], self.a
            elif op == 0xA4:  # MUL AB; subsequent code uses high byte in B
                value = self.a * self.direct[0xF0]
                self.a, self.direct[0xF0], self.carry = value & 255, value >> 8, 0
            elif op in (0x24, 0x25, 0x34, 0x35) or 0x28 <= op <= 0x2F or 0x38 <= op <= 0x3F:
                value = self.a + self.operand(op) + (self.carry if op & 0x10 else 0)
                self.a, self.carry = value & 255, int(value > 255)
            elif op == 0x94:
                value = self.a - self.fetch() - self.carry
                self.a, self.carry = value & 255, int(value < 0)
            elif op == 0x64:
                self.a ^= self.fetch()
            elif op == 0xB4:  # CJNE A,#imm,relative also updates carry
                value = self.fetch()
                self.carry = int(self.a < value)
                self.relative(self.a != value)
            elif op in (0x20, 0x30):  # JB/JNB; only accumulator bits needed here
                bit = self.fetch()
                if not 0xE0 <= bit <= 0xE7:
                    raise ValueError("unmodeled bit address")
                set_bit = bool(self.a & (1 << (bit - 0xE0)))
                self.relative(set_bit if op == 0x20 else not set_bit)
            elif op in (0x40, 0x50, 0x60, 0x70, 0x80):
                self.relative({0x40: bool(self.carry), 0x50: not self.carry,
                               0x60: self.a == 0, 0x70: self.a != 0, 0x80: True}[op])
            elif op in (0x02, 0x12):
                target = self.fetch() << 8 | self.fetch()
                if op == 0x12:
                    self.stack.append(self.pc)
                self.pc = target
            elif op == 0x22:
                if not self.stack:
                    return None
                self.pc = self.stack.pop()
            else:
                raise ValueError(f"unsupported opcode {op:#04x} at {address:#06x}")
        raise ValueError("instruction limit exceeded")


def trace_record(ec, index, selector=1):
    """Trace one record to the bus-call boundary, delay return, or terminator.

    Stops BEFORE the bus routine at 0xf129; no success is assumed or injected.
    Inputs are an already-selected code window and explicit table index/selector.
    """
    if len(ec) != EC_SIZE or not 0 <= index < 256 or selector not in (1, 2):
        raise ValueError("invalid EC record trace inputs")
    machine = Machine(ec[:0x10000])
    machine.xram[0x0356] = selector
    machine.xram[0x0FD2] = 0x13
    machine.xram[0x0FD3:0x0FD5] = index.to_bytes(2, "big")
    boundary = machine.run(0xF75B, stops=(0xF129,))
    result = {"index": index, "code_reads": [hex(p) for p in machine.code_reads],
              "visited_instructions": len(machine.visited)}
    if boundary == 0xF129:
        length = machine.direct[2] << 8 | machine.direct[3]
        pointer = int.from_bytes(machine.xram[0x06B2:0x06B4], "big")
        result.update({"kind": "bus call boundary", "address": hex(boundary),
                       "device_argument": machine.direct[7], "port_argument": hex(machine.direct[5]),
                       "length": length, "pointer": hex(pointer),
                       "bytes_hex": machine.xram[pointer:pointer + length].hex(" ")})
    elif machine.xram[0x0FD2] == 0x14:
        result.update({"kind": "end", "next_state": "0x14"})
    else:
        result.update({"kind": "delay", "counter": int.from_bytes(machine.xram[0x0FD5:0x0FD7], "big"),
                       "next_index": int.from_bytes(machine.xram[0x0FD3:0x0FD5], "big"),
                       "unit": "scheduler invocations; wall-clock period unverified"})
    return result


def inspect(image):
    data = bios_image(image)
    digest = sha256(data)
    if digest not in (STOCK_SHA256, R04_SHA256):
        raise ValueError("EC trace requires the pinned stock or r04 BIOSIMG")
    banks = []
    for bank, base in enumerate(EC_BASES):
        ec = data[base:base + EC_SIZE]
        records = []
        for index in range(256):
            record = trace_record(ec, index)
            records.append(record)
            if record["kind"] == "end":
                break
        else:
            raise ValueError("no end record")
        selector_results = []
        for strap in (0, 0x40):
            machine = Machine(ec[:0x10000])
            machine.xram[0x160A] = strap
            machine.run(0xF2C3)
            selector_results.append({"xram_0x160a_bit6": bool(strap), "selector": machine.xram[0x0356]})
        counter_results = []
        for initial in (0, 1, 60, 256, 65535):
            machine = Machine(ec[:0x10000])
            machine.xram[0x0FD5:0x0FD7] = initial.to_bytes(2, "big")
            boundary = machine.run(0xF207, stops=(0xF214,))
            counter_results.append({"initial": initial,
                                    "after": int.from_bytes(machine.xram[0x0FD5:0x0FD7], "big"),
                                    "reached_state_dispatch": boundary == 0xF214})
        banks.append({"bank": bank, "base": hex(base), "selector_branch": selector_results,
                      "counter_probes": counter_results, "records": records})
    return {"biosimg_sha256": digest,
            "scope": "offline instruction interpretation; each record starts independently at index with selector 1; stops before bus I/O",
            "not_modeled": ["bank activation", "peripherals", "interrupts", "wall-clock scheduling", "bus success", "panel behavior"],
            "banks": banks}
