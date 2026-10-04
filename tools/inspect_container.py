#!/usr/bin/env python3
"""Read PE section hashes and embedded certificate metadata; does NOT validate signatures."""

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from opendecksight.firmware import chunks
from opendecksight.container import align, der_sequence, pe_checksum


def inspect_pe(data):
    def bounded(start, size):
        if start < 0 or size < 0 or start + size > len(data):
            raise ValueError("PE field exceeds image bounds")
        return data[start:start + size]

    if bounded(0, 2) != b"MZ":
        raise ValueError("missing DOS header")
    pe = struct.unpack("<I", bounded(0x3C, 4))[0]
    if bounded(pe, 4) != b"PE\0\0":
        raise ValueError("missing PE signature")
    number = struct.unpack("<H", bounded(pe + 6, 2))[0]
    optional_size = struct.unpack("<H", bounded(pe + 20, 2))[0]
    optional = pe + 24
    magic = struct.unpack("<H", bounded(optional, 2))[0]
    if magic not in (0x10B, 0x20B):
        raise ValueError("unsupported PE optional header")
    dir_relative = 112 if magic == 0x20B else 96
    if optional_size < dir_relative + 40:
        raise ValueError("optional header lacks security directory")
    sections = []
    for i in range(number):
        header = bounded(optional + optional_size + 40 * i, 40)
        size, offset = struct.unpack_from("<II", header, 16)
        content = bounded(offset, size)
        sections.append({"name": header[:8].rstrip(b"\0").decode("ascii", errors="replace"),
                         "offset": offset, "size": size, "sha256": hashlib.sha256(content).hexdigest()})
    checksum = struct.unpack("<I", bounded(optional + 64, 4))[0]
    computed = pe_checksum(data, optional + 64)
    result = {"sections": sections, "signature_validation": "NOT PERFORMED",
              "pe_checksum": {"stored": checksum, "computed": computed, "valid": checksum == computed},
              "size_of_image": struct.unpack("<I", bounded(optional + 56, 4))[0],
              "file_alignment": struct.unpack("<I", bounded(optional + 36, 4))[0]}
    offset, size = struct.unpack("<II", bounded(optional + dir_relative + 32, 8))
    if size:
        certificate = bounded(offset, size)
        if len(certificate) < 8:
            raise ValueError("truncated WIN_CERTIFICATE")
        length, revision, kind = struct.unpack_from("<IHH", certificate)
        if length < 8 or length > size or kind != 2:
            raise ValueError("invalid/unsupported WIN_CERTIFICATE")
        der = der_sequence(certificate[8:length])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "certificate.der"
            path.write_bytes(der)
            info = subprocess.run(["openssl", "pkcs7", "-inform", "DER", "-in", str(path), "-print_certs", "-noout"],
                                  check=True, capture_output=True, text=True, timeout=10).stdout.strip()
        result["certificate"] = {"offset": offset, "size": size, "revision": revision,
                                 "pkcs7_sha256": hashlib.sha256(der).hexdigest(), "metadata": info}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("container", type=Path)
    args = parser.parse_args()
    try:
        data = args.container.read_bytes()
        result = {"sha256": hashlib.sha256(data).hexdigest(), "outer": inspect_pe(data), "iflash_records": []}
        for chunk in chunks(data):
            slot = align(24 + len(chunk.data), 32)
            convention = ("excludes 24-byte header" if chunk.declared_size == slot - 24 else
                          "includes 24-byte header" if chunk.declared_size == slot else "unclassified")
            result["iflash_records"].append({"name": chunk.name, "marker_offset": chunk.header_offset + 8,
                                            "payload_offset": chunk.payload_offset, "payload_size": len(chunk.data),
                                            "declared_size": chunk.declared_size, "aligned_slot_size": slot,
                                            "padding_size": slot - 24 - len(chunk.data), "extent_convention": convention})
            if chunk.name == "DRV_IMG":
                result["embedded_driver"] = inspect_pe(chunk.data)
        print(json.dumps(result, indent=2))
    except (OSError, ValueError, struct.error, subprocess.SubprocessError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
