#!/usr/bin/env python3
"""Extract ONLY the three pinned historical r04 signature resources, for explicit reuse."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from opendecksight.container import extract_signatures
from opendecksight.firmware import sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release", type=Path)
    parser.add_argument("output_directory", type=Path)
    args = parser.parse_args()
    try:
        resources = extract_signatures(args.release.read_bytes())
        args.output_directory.mkdir(parents=True, exist_ok=False)
        for name, content in resources.items():
            with (args.output_directory / name).open("xb") as output:
                output.write(content)
        print(json.dumps({"purpose": "reuse existing r04 signatures; no new signing key",
                          "resources": [{"name": n, "size": len(b), "sha256": sha256(b)}
                                        for n, b in resources.items()]}, indent=2))
    except (OSError, ValueError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
