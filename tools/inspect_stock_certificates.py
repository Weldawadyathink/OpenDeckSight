#!/usr/bin/env python3
"""Inventory public certificates in a local UEFIExtract dump of stock F7A0133.

Reads files and invokes OpenSSL for certificate metadata only. Does not inspect
live NVRAM, execute firmware, change trust settings, or establish updater policy.
"""

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from opendecksight.firmware import STOCK_SHA256

CERT_FILE_GUID = "9F4F421C-CE02-42C1-92FB-CF26C52B9526"
X509_GUID = uuid.UUID("a5c059a1-94e4-4aa7-87b5-ab155c2bf072")
QA_SHA256 = "f14700fcca6aed9c5d33f356e3f8a3413beda76dacaa1324b00e3d0a05446b18"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def signature_lists(data):
    """Parse bounded EFI_SIGNATURE_LIST entries; retain no certificate payloads."""
    result = []
    offset = 0
    while offset < len(data):
        if len(data) - offset < 28:
            raise ValueError("truncated EFI_SIGNATURE_LIST header")
        kind = uuid.UUID(bytes_le=data[offset:offset + 16])
        size, header_size, entry_size = struct.unpack_from("<III", data, offset + 16)
        if (size < 28 + header_size or size > len(data) - offset
                or entry_size <= 16 or (size - 28 - header_size) % entry_size):
            raise ValueError("invalid EFI_SIGNATURE_LIST bounds")
        entries = []
        for start in range(offset + 28 + header_size, offset + size, entry_size):
            payload = data[start + 16:start + entry_size]
            fingerprint = sha256(payload)
            entry = {"payload_offset": start + 16, "size": len(payload),
                     "sha256": fingerprint, "matches_decksight_r04_qa": fingerprint == QA_SHA256}
            if kind == X509_GUID:
                info = subprocess.run(
                    ["openssl", "x509", "-inform", "DER", "-noout", "-subject", "-issuer"],
                    input=payload, capture_output=True, check=True, timeout=10)
                entry["certificate"] = info.stdout.decode().strip().splitlines()
            entries.append(entry)
        result.append({"offset": offset, "type": str(kind), "size": size,
                       "header_size": header_size, "entry_size": entry_size, "entries": entries})
        offset += size
    return result


def inspect(root):
    source_hash = sha256((root / "body.bin").read_bytes())
    if source_hash != STOCK_SHA256:
        raise ValueError("expected the pinned Valve F7A0133 BIOSIMG extraction")
    report = {"schema": 1, "stock_biosimg_sha256": source_hash,
              "decksight_r04_qa_certificate_sha256": QA_SHA256,
              "scope": "static public firmware data; live NVRAM and execution paths not verified",
              "certificate_resources": [], "driver_guid_occurrences": []}
    patterns = [("firmware certificate resource", f"**/* {CERT_FILE_GUID}/0 Raw section/body.bin"),
                ("factory default db in Insyde FDC store", "**/* Insyde FDC store/* VSS store/* db/body.bin")]
    for role, pattern in patterns:
        paths = sorted(root.glob(pattern))
        if len(paths) != 2:
            raise ValueError(f"expected two copies of {role}, found {len(paths)}")
        for path in paths:
            data = path.read_bytes()
            report["certificate_resources"].append(
                {"role": role, "path": path.relative_to(root).as_posix(),
                 "size": len(data), "sha256": sha256(data), "signature_lists": signature_lists(data)})
    needle = uuid.UUID(CERT_FILE_GUID).bytes_le
    for module in ("BdsDxe", "SecureFlashDxe", "SecurityStubDxe"):
        for path in sorted(root.glob(f"**/* {module}/* PE32 image section/body.bin")):
            data = path.read_bytes()
            offsets = []
            offset = data.find(needle)
            while offset != -1:
                offsets.append(offset)
                offset = data.find(needle, offset + 1)
            report["driver_guid_occurrences"].append(
                {"module": module, "path": path.relative_to(root).as_posix(),
                 "sha256": sha256(data), "file_offsets": offsets})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dump", type=Path, help="local UEFIExtract dump directory")
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(args.dump), indent=2))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
