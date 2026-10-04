"""Read Insyde containers, compare bytes and reproduce the observed EC changes.

This module neither signs firmware nor writes to a device. Offsets below are
specific to the SHA-256-identified Valve F7A0133 BIOSIMG, not arbitrary BIOSes.
"""

from dataclasses import dataclass
import hashlib
import struct

from .edid import encode_detailed_timing

STOCK_SHA256 = "b77eb694c5af0d125bbca0a018ee18a2ad54409211b454e38f9bb545a62f7f64"
EC_BASES = (0, 0x40000)
EC_SIZE = 0x20000
EDID_OFFSET = 0x68E5
EXTENDED_EDID_OFFSET = 0x7DCF
PANEL_INIT_OFFSET = 0x6E55
R04_SHA256 = "5ef3e6e8ddf84fb36c6368156ef67adfd0a92ad362a460fc264c748d653b3549"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Chunk:
    name: str
    header_offset: int
    payload_offset: int
    declared_size: int
    data: bytes


def chunks(data):
    """Find bounded IFLASH records, including records nested in DRV_IMG."""
    marker = bytes(8) + b"$_IFLASH_"
    pos = 0
    result = []
    names = set()
    while (pos := data.find(marker, pos)) != -1:
        if pos + 32 > len(data):
            raise ValueError("truncated IFLASH header")
        name_bytes = data[pos + 17:pos + 24]
        if not all(c in b"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for c in name_bytes):
            raise ValueError("invalid IFLASH chunk name")
        name = name_bytes.decode("ascii")
        declared, size = struct.unpack_from("<II", data, pos + 24)
        if size > declared or pos + 32 + size > len(data):
            raise ValueError(f"invalid IFLASH bounds for {name}")
        if name in names:
            raise ValueError(f"ambiguous duplicate IFLASH chunk: {name}")
        names.add(name)
        result.append(Chunk(name, pos, pos + 32, declared, data[pos + 32:pos + 32 + size]))
        pos += 32
    return result


def bios_image(data):
    records = chunks(data)
    if records:
        matches = [c.data for c in records if c.name == "BIOSIMG"]
        if len(matches) != 1:
            raise ValueError("expected exactly one BIOSIMG chunk")
        data = matches[0]
    if len(data) != 0x1000000:
        raise ValueError("expected a 16 MiB Jupiter BIOSIMG or its Insyde container")
    return data


def diff_spans(before, after, gap=0):
    """Half-open intervals of changed bytes, optionally coalescing unchanged gaps."""
    if len(before) != len(after):
        raise ValueError("images must have the same size; extract BIOSIMG first")
    if gap < 0:
        raise ValueError("gap cannot be negative")
    spans = []
    start = previous = None
    for i, (a, b) in enumerate(zip(before, after)):
        if a == b:
            continue
        if start is None:
            start = i
        elif i - previous - 1 > gap:
            spans.append((start, previous + 1))
            start = i
        previous = i
    if start is not None:
        spans.append((start, previous + 1))
    return spans


def ec_checksum(ec):
    if len(ec) != EC_SIZE:
        raise ValueError("expected 128 KiB EC image")
    return sum(ec[0x2000:0x1F7FE]) & 0xFFFF


def describe_ec(image):
    result = []
    for base in EC_BASES:
        ec = image[base:base + EC_SIZE]
        actual = ec_checksum(ec)
        stored = int.from_bytes(ec[0x1F7FE:0x1F800], "big")
        result.append({"base": base, "sha256": sha256(ec), "checksum": actual,
                       "stored_checksum": stored, "checksum_valid": actual == stored,
                       "edid_read_pointer": int.from_bytes(ec[0xF37D:0xF37F], "big"),
                       "edid_read_limit": ec[0xF3AD], "display_selector": ec[0xF2D2]})
    return result


def r04_edid():
    """Encode the 256-byte EDID observed at EC offset 0x7dcf in r04.

    This is a compatibility description, not a new color calibration.
    The base DTD is 1080x1920, 143.18 MHz, H 32/8/100, V 8/2/26.
    """
    base = bytearray(128)
    base[:18] = bytes.fromhex("00ffffffffffff00 126f0150 01000000 0123")
    base[18:38] = bytes.fromhex("0104 a5091078 17b974ae503db7230b4f51 000000")
    base[38:54] = b"\x01\x01" * 8
    base[54:72] = encode_detailed_timing(
        width=1080, height=1920, clock_hz=143180000,
        h_front=32, h_sync=8, h_back=100, v_front=8, v_sync=2, v_back=26,
        width_mm=90, height_mm=160)
    base[72:90] = b"\x00\x00\x00\xfc\x00DeckSight\n   "
    base[126] = 1
    base[127] = -sum(base) & 255
    cta = bytearray(128)
    # CTA revision 3; HDR static metadata: traditional SDR + PQ, type 1.
    cta[:11] = bytes.fromhex("02030b00 e60605016a6a00")
    cta[127] = -sum(cta) & 255
    return bytes(base + cta)


# Register/value records as consumed by the big-endian 8051 table interpreter.
# Values describe observed r04 behavior; vendor-specific commands remain opaque.
R04_PANEL_INIT = (
    (0x70, 0x00A5A59C), (0x6C, 0x00000339), (0x6C, 0x00001105),
    (0xAA, 60), (0x6C, 0x00034815), (0x6C, 0x00695315),
    (0x70, 0x00000951), (0x70, 0), (0x6C, 0x00000639),
    (0x6C, 0x00003405), (0x70, 0x00100044), (0x6C, 0x00000339),
    (0x6C, 0x00003505), (0x6C, 0x00000107), (0x6C, 0x00000007),
    (0x70, 0x005A5AFD), (0x6C, 0x00000339), (0x6C, 0x00029F15),
    (0x70, 0x003000ED), (0x6C, 0x00000339), (0x6C, 0x00019F15),
    (0x70, 0x000010B4), (0x70, 0x001003), (0x6C, 0x00000639),
    (0x6C, 0x00002905), (0xFF, 0),
)


def r04_bridge_timings():
    """ANX SPI register/value table, generated from named timing fields.

    These initialization timings intentionally differ from the EDID and Lua.
    0xb0: four MIPI lanes (encoded as 3), 0xb1: DPHY timing + mode field 1.
    0x9f/0x9e preserve the observed notification/control values.
    """
    geometry = (1080, 136, 1, 24, 1920, 20, 1, 15)
    records = bytearray()
    for index, value in enumerate(geometry):
        register = 0xA0 + index * 2
        records.extend((register, value & 255, register + 1, value >> 8))
    records.extend((0x9D, 80, 0xB0, 3 << 2, 0xB1, 0x40 | (1 << 2),
                    0x9F, 0x7B, 0x9E, 0xC0, 0xFF, 0xFF))
    return bytes(records)


def replace_instruction(image, offset, before, after):
    if len(before) != len(after) or image[offset:offset + len(before)] != before:
        raise ValueError(f"unexpected 8051 instruction at {offset:#x}")
    image[offset:offset + len(before)] = after


def build_r04_ec_reproduction(stock):
    """Reproduce both released r04 EC regions; keep stock UEFI and branding.

    Intentionally preserves the released second-bank byte-order anomaly.
    Output is a research image, with no claim that it can boot or be flashed.
    """
    stock = bios_image(stock)
    if sha256(stock) != STOCK_SHA256:
        raise ValueError("unsupported stock BIOS hash; refusing offset-based patching")
    output = bytearray(stock)
    edid = r04_edid()
    for bank, base in enumerate(EC_BASES):
        ec = bytearray(stock[base:base + EC_SIZE])
        ec[EDID_OFFSET:EDID_OFFSET + 128] = edid[:128]
        ec[EXTENDED_EDID_OFFSET:EXTENDED_EDID_OFFSET + 256] = edid
        ec[0x6967] = 0x0A  # DPCD MAX_LINK_RATE: 2.7 Gbit/s
        ec[0x696D] = 0x14  # Observed second link table field; meaning not established.
        timing_table = r04_bridge_timings()
        ec[0x69AE:0x69AE + len(timing_table)] = timing_table
        endian = "big" if bank == 0 else "little"
        table = b"".join(bytes([register]) + value.to_bytes(4, endian)
                         for register, value in R04_PANEL_INIT)
        ec[PANEL_INIT_OFFSET:PANEL_INIT_OFFSET + len(table)] = table
        replace_instruction(ec, 0xF2D1, b"\x74\x02", b"\x74\x01")  # MOV A,#display_id
        replace_instruction(ec, 0xF37C, b"\x90\x68\xe5", b"\x90\x7d\xcf")  # MOV DPTR,#edid
        replace_instruction(ec, 0xF3AC, b"\x94\x7f", b"\x94\xff")  # SUBB A,#last_edid_byte
        ec[0x1F7FE:0x1F800] = ec_checksum(ec).to_bytes(2, "big")
        output[base:base + EC_SIZE] = ec
    return bytes(output)
