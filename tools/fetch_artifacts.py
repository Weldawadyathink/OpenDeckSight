#!/usr/bin/env python3
"""Fetch hash-pinned public artifacts and extract only named data files.

Does not execute an installer, flasher or any downloaded executable. Uses the
host tar for Valve's .tar.zst archive (macOS bsdtar includes zstd support).
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
EXTRACTIONS = {
    "DeckSight-r04.tar.gz": (
        ("bios/F7A0133_DeckSight_signed_r04.fd", "r04/bios/F7A0133_DeckSight_signed_r04.fd"),
        ("decksight-brightnessctrl/decksight-brightnessctrl", "r04/decksight-brightnessctrl/decksight-brightnessctrl"),
    ),
    "DeckSight-r03.tar.gz": (("bios/F7A0133_DeckSight_signed_r03.fd", "r03/bios/F7A0133_DeckSight_signed_r03.fd"),),
    "jupiter-hw-support-20260930.1-1-any.pkg.tar.zst": (
        ("usr/share/jupiter_bios/F7A0133_sign.fd", "stock/usr/share/jupiter_bios/F7A0133_sign.fd"),
        ("usr/share/jupiter_bios_updater/h2offt", "stock/usr/share/jupiter_bios_updater/h2offt"),
    ),
}


def matches(path, record):
    return path.is_file() and path.stat().st_size == record["size"] and hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]


def fetch(record, directory):
    destination = directory / record["filename"]
    if destination.exists():
        if not matches(destination, record):
            raise ValueError(f"existing file does not match pinned hash: {destination}")
        print(f"verified {destination.name}")
        return destination
    request = urllib.request.Request(record["url"], headers={"User-Agent": "OpenDeckSight-artifact-research/0.1"})
    with tempfile.NamedTemporaryFile(dir=directory, delete=False) as output:
        temporary = Path(output.name)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                count = 0
                while block := response.read(1024 * 1024):
                    count += len(block)
                    if count > record["size"]:
                        raise ValueError("download exceeds pinned size")
                    output.write(block)
            output.flush()
            if not matches(temporary, record):
                raise ValueError(f"download hash/size mismatch: {record['filename']}")
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
    print(f"downloaded and verified {destination.name}")
    return destination


def extract(archive, member, destination, expected):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if not matches(destination, expected):
            raise ValueError(f"existing extracted file has wrong hash: {destination}")
        return
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as output:
        temporary = Path(output.name)
        try:
            subprocess.run(["tar", "-xOf", str(archive), member], stdout=output, check=True, timeout=60)
            output.flush()
            if not matches(temporary, expected):
                raise ValueError(f"extracted data hash mismatch: {member}")
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-tools", action="store_true", help="also download pinned analysis tool archives; do not execute them")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "research/artifacts.json").read_text())
    directory = ROOT / "artifacts/downloads"
    directory.mkdir(parents=True, exist_ok=True)
    try:
        for record in manifest["downloads"]:
            if record["filename"] not in EXTRACTIONS and not args.include_tools:
                continue
            archive = fetch(record, directory)
            for member, relative in EXTRACTIONS.get(record["filename"], ()):
                target = Path("artifacts/extracted") / relative
                expected = next(r for r in manifest["payloads"] if r["path"] == str(target))
                extract(archive, member, ROOT / target, expected)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
