#!/usr/bin/env python3
"""Extract the identified PNG resource from an existing r04 UEFIExtract dump."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from opendecksight.build import SPLASH_GUID, SPLASH_SHA256
from opendecksight.firmware import sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dump", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        matches = [p for p in args.dump.rglob("body.bin")
                   if SPLASH_GUID in str(p) and p.parent.name.endswith("Raw section")]
        if len(matches) != 2:
            raise ValueError("expected the splash raw section in both UEFI banks")
        resources = [p.read_bytes() for p in matches]
        if any(sha256(data) != SPLASH_SHA256 for data in resources):
            raise ValueError("splash resource differs from pinned r04 PNG")
        with args.output.open("xb") as output:
            output.write(resources[0])
        print(f"Extracted identified r04 artwork: {len(resources[0])} bytes, SHA-256 {SPLASH_SHA256}")
    except (OSError, ValueError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
