"""Repack the historical r04 Insyde container with its existing signatures.

The reconstruction consumes Valve's original wrapper code, a separately
reconstructed BIOSIMG, and three explicitly identified signature resources.
It does not copy release firmware regions, apply binary deltas, or sign new
firmware. All inputs and the final historical output are hash-pinned.
"""

from array import array
from dataclasses import dataclass
import struct
import sys

from .firmware import R04_SHA256, chunks, sha256

STOCK_FD_SHA256 = "c8b1e749ad709bf20899eed59bd9012a8482b55003d2785134f0b17876a240d9"
R04_FD_SHA256 = "4c0b33f4d48b9557337d690d20014941855acd39a1cfb7e3e46d04b1d12403ea"
SIGNATURE_HASHES = {
    "bioscer.sig": "9939dcfa18573e43afccf34d88e1ab6461af95aeb787315f653c5698c0f8490d",
    "driver.p7b": "b60aea2f5718bff14e6a1c2de317a0237aa751a33d722bf89f6cd72ce28d7952",
    "outer.p7b": "3f6afb6959e803ff13834a252306bb5067b575194301fe6ec7928a1833315382",
}


def align(value, boundary):
    if value < 0 or boundary <= 0 or boundary & (boundary - 1):
        raise ValueError("invalid alignment")
    return (value + boundary - 1) & -boundary


@dataclass(frozen=True)
class PE:
    optional: int
    last_section: int
    certificate_offset: int
    certificate_size: int

    @property
    def checksum_offset(self):
        return self.optional + 64

    @property
    def security_directory(self):
        return self.optional + 112 + 8 * 4


def parse_pe(data):
    """Validate the flat PE32+ layout used by the pinned two wrappers."""
    def get(fmt, offset):
        size = struct.calcsize(fmt)
        if offset < 0 or offset + size > len(data):
            raise ValueError("PE field outside input")
        return struct.unpack_from(fmt, data, offset)

    if len(data) < 64 or data[:2] != b"MZ":
        raise ValueError("missing DOS header")
    pe, = get("<I", 60)
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("missing PE header")
    machine, count = get("<HH", pe + 4)
    size, = get("<H", pe + 20)
    optional = pe + 24
    magic, = get("<H", optional)
    if machine != 0x8664 or magic != 0x20B or size < 152 or not 1 <= count <= 96:
        raise ValueError("unsupported PE layout")
    if get("<II", optional + 32) != (32, 32):
        raise ValueError("expected 32-byte section/file alignment")
    cert_offset, cert_size = get("<II", optional + 144)
    headers_size, = get("<I", optional + 60)
    previous_end = headers_size
    for i in range(count):
        header = optional + size + 40 * i
        virtual_size, address, raw_size, pointer = get("<IIII", header + 8)
        if pointer != address or pointer != previous_end or not 0 < virtual_size <= raw_size:
            raise ValueError("non-flat or noncontiguous PE section")
        if pointer % 32 or raw_size % 32 or pointer + raw_size > len(data):
            raise ValueError("invalid PE section bounds/alignment")
        previous_end = pointer + raw_size
    if previous_end != cert_offset or cert_offset + cert_size != len(data) or cert_size < 8:
        raise ValueError("expected certificate immediately after final section")
    if data[header:header + 8].rstrip(b"\0") != b".reloc":
        raise ValueError("expected final .reloc resource section")
    return PE(optional, header, cert_offset, cert_size)


def der_sequence(data):
    """Read one definite-length DER SEQUENCE and accept only zero alignment tail."""
    if len(data) < 2 or data[0] != 0x30:
        raise ValueError("missing DER SEQUENCE")
    if data[1] < 128:
        end = 2 + data[1]
    else:
        width = data[1] & 127
        if not 1 <= width <= 4 or 2 + width > len(data):
            raise ValueError("invalid DER length")
        end = 2 + width + int.from_bytes(data[2:2 + width], "big")
    if end > len(data) or any(data[end:]):
        raise ValueError("truncated DER or nonzero trailing data")
    return bytes(data[:end])


def extract_pkcs7(data):
    pe = parse_pe(data)
    length, revision, kind = struct.unpack_from("<IHH", data, pe.certificate_offset)
    if length != pe.certificate_size or revision != 0x200 or kind != 2:
        raise ValueError("unexpected WIN_CERTIFICATE")
    return der_sequence(data[pe.certificate_offset + 8:])


def extract_signatures(release):
    if sha256(release) != R04_FD_SHA256:
        raise ValueError("signature extraction requires the pinned r04 release")
    parts = {c.name: c for c in chunks(release)}
    return {"bioscer.sig": parts["BIOSCER"].data,
            "driver.p7b": extract_pkcs7(parts["DRV_IMG"].data),
            "outer.p7b": extract_pkcs7(release)}


def pack_record(name, data):
    """24-byte IFLASH header; TotalSize excludes it and includes 32-byte padding."""
    if len(name) != 7 or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for c in name):
        raise ValueError("invalid IFLASH tag")
    total = align(24 + len(data), 32) - 24
    return (b"$_IFLASH_" + name.encode("ascii") + struct.pack("<II", total, len(data))
            + data + bytes(total - len(data)))


def pe_checksum(data, offset):
    if offset < 0 or offset + 4 > len(data) or offset % 2:
        raise ValueError("invalid PE checksum field")
    values = array("H", bytes(data) + (b"\0" if len(data) % 2 else b""))
    if sys.byteorder != "little":
        values.byteswap()
    values[offset // 2] = values[offset // 2 + 1] = 0
    total = sum(values)
    while total >> 16:
        total = (total & 65535) + (total >> 16)
    return (total + len(data)) & 0xFFFFFFFF


def attach_signature(unsigned, source_pe, pkcs7):
    """Regenerate final-section extents, image size, certificate wrapper and checksum."""
    data = bytearray(unsigned)
    if len(data) % 32 or der_sequence(pkcs7) != pkcs7:
        raise ValueError("invalid unsigned PE alignment or DER resource")
    cert_size = align(8 + len(pkcs7), 8)
    cert = struct.pack("<IHH", cert_size, 0x200, 2) + pkcs7 + bytes(cert_size - 8 - len(pkcs7))
    address, = struct.unpack_from("<I", data, source_pe.last_section + 12)
    size = len(data) - address  # Flat RVA/file layout, validated by parse_pe.
    if size <= 0:
        raise ValueError("invalid final-section extent")
    struct.pack_into("<I", data, source_pe.last_section + 8, size)
    struct.pack_into("<I", data, source_pe.last_section + 16, size)
    struct.pack_into("<I", data, source_pe.optional + 56, align(address + size, 32))
    struct.pack_into("<II", data, source_pe.security_directory, len(data), len(cert))
    data.extend(cert)
    struct.pack_into("<I", data, source_pe.checksum_offset, pe_checksum(data, source_pe.checksum_offset))
    return bytes(data)


def build_container(stock, biosimg, signatures):
    if sha256(stock) != STOCK_FD_SHA256 or sha256(biosimg) != R04_SHA256:
        raise ValueError("container build requires pinned stock .fd and reconstructed r04 BIOSIMG")
    if set(signatures) != set(SIGNATURE_HASHES):
        raise ValueError("expected exactly three historical signature resources")
    for name, expected in SIGNATURE_HASHES.items():
        if sha256(signatures[name]) != expected:
            raise ValueError(f"signature resource hash mismatch: {name}")
    outer = parse_pe(stock)
    parts = {c.name: c for c in chunks(stock)}
    driver = parts["DRV_IMG"].data
    inner = parse_pe(driver)
    inner_parts = {c.name: c for c in chunks(driver)}
    # Header offsets in the scanner include the eight preceding zero bytes;
    # the actual 24-byte IFLASH header starts at its ASCII marker, eight later.
    unsigned_driver = bytearray(driver[:inner_parts["BIOSIMG"].header_offset + 8])
    for name, payload in (("BIOSIMG", biosimg), ("INI_IMG", inner_parts["INI_IMG"].data),
                          ("BIOSCER", signatures["bioscer.sig"]), ("BIOSCR2", inner_parts["BIOSCR2"].data)):
        unsigned_driver.extend(pack_record(name, payload))
    signed_driver = attach_signature(unsigned_driver, inner, signatures["driver.p7b"])
    unsigned_outer = stock[:parts["DRV_IMG"].header_offset + 8] + pack_record("DRV_IMG", signed_driver)
    result = attach_signature(unsigned_outer, outer, signatures["outer.p7b"])
    if sha256(result) != R04_FD_SHA256:
        raise ValueError("container reconstruction is not byte-identical; no correction bytes applied")
    return result
