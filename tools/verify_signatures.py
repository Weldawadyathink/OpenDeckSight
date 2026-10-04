#!/usr/bin/env python3
"""Offline cryptographic checks using the container's own certificate as an explicit anchor.

This does not establish Valve trust, updater acceptance, or possession of a
private key. Requires OpenSSL and an explicitly supplied osslsigncode executable.
"""

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from opendecksight.firmware import chunks, sha256
from opendecksight.container import der_sequence


def certificate(data):
    if len(data) < 64 or data[:2] != b"MZ":
        raise ValueError("not a PE image")
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if pe + 26 > len(data) or data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("invalid PE header")
    optional = pe + 24
    magic = struct.unpack_from("<H", data, optional)[0]
    if magic not in (0x10B, 0x20B):
        raise ValueError("unknown PE optional header")
    directory = optional + (112 if magic == 0x20B else 96) + 32
    if directory + 8 > len(data):
        raise ValueError("missing security directory")
    offset, size = struct.unpack_from("<II", data, directory)
    if size < 8 or offset + size > len(data):
        raise ValueError("invalid certificate bounds")
    length, revision, kind = struct.unpack_from("<IHH", data, offset)
    if not 8 <= length <= size or kind != 2:
        raise ValueError("unsupported WIN_CERTIFICATE")
    return der_sequence(data[offset + 8:offset + length])


def run(command):
    result = subprocess.run([str(c) for c in command], capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise ValueError(f"verification command failed: {result.stdout}\n{result.stderr}")
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--osslsigncode", required=True, type=Path)
    args = parser.parse_args()
    try:
        data = args.image.read_bytes()
        parts = {part.name: part.data for part in chunks(data)}
        if not all(name in parts for name in ("DRV_IMG", "BIOSIMG", "BIOSCER")):
            raise ValueError("expected nested Insyde firmware/signature records")
        report = {"input_sha256": sha256(data), "biosimg_sha256": sha256(parts["BIOSIMG"]),
                  "trust_scope": "artifact's own embedded certificate explicitly trusted for mathematical verification only",
                  "valve_trust_or_updater_acceptance": "NOT ESTABLISHED", "authenticode": []}
        with tempfile.TemporaryDirectory(prefix="opendecksight-signatures-") as directory:
            root = Path(directory)
            for name, image in (("outer", data), ("embedded_driver", parts["DRV_IMG"])):
                image_path, der_path, pem_path = (root / (name + suffix) for suffix in (".pe", ".der", ".pem"))
                image_path.write_bytes(image)
                der_path.write_bytes(certificate(image))
                run(["openssl", "pkcs7", "-inform", "DER", "-in", der_path, "-print_certs", "-out", pem_path])
                if pem_path.read_text().count("BEGIN CERTIFICATE") != 1:
                    raise ValueError("verification helper expects a single embedded certificate")
                log = run([args.osslsigncode.resolve(), "verify", "-in", image_path, "-CAfile", pem_path, "-ignore-cdp"])
                report["authenticode"].append({"layer": name, "verified": True,
                                               "pkcs7_sha256": sha256(der_path.read_bytes()),
                                               "method": "osslsigncode verify with artifact certificate, CRL fetching disabled",
                                               "digest_lines": [line.strip() for line in log.splitlines()
                                                                if "message digest " in line.lower()]})
            public_key = root / "public.pem"
            run(["openssl", "x509", "-in", root / "outer.pem", "-pubkey", "-noout", "-out", public_key])
            (root / "bioscer.bin").write_bytes(parts["BIOSCER"])
            recovered_path = root / "digest-info.der"
            run(["openssl", "pkeyutl", "-verifyrecover", "-pubin", "-inkey", public_key,
                 "-in", root / "bioscer.bin", "-pkeyopt", "rsa_padding_mode:pkcs1", "-out", recovered_path])
            recovered = recovered_path.read_bytes()
            digest_info_prefix = bytes.fromhex("3031300d060960864801650304020105000420")
            if recovered != digest_info_prefix + hashlib.sha256(parts["BIOSIMG"]).digest():
                raise ValueError("BIOSCER DigestInfo does not match BIOSIMG SHA-256")
            report["bioscer"] = {"verified": True, "scheme": "RSA PKCS#1 v1.5 / SHA-256",
                                 "signed_content": "entire BIOSIMG", "recovered_digest_info_hex": recovered.hex()}
        print(json.dumps(report, indent=2))
    except (OSError, ValueError, struct.error, subprocess.SubprocessError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
