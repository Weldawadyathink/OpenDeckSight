"""Command line interface. All commands are offline/read-only unless explicitly stated."""

import argparse
import json
from pathlib import Path
import sys

from . import edid, firmware


def emit(value):
    print(json.dumps(value, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser(description="OpenDeckSight firmware research tools")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="report container, EC checksums and EDIDs")
    inspect.add_argument("image", type=Path)
    extract = commands.add_parser("extract", help="extract BIOSIMG (never execute the container)")
    extract.add_argument("image", type=Path)
    extract.add_argument("output", type=Path)
    compare = commands.add_parser("diff", help="compare extracted BIOSIMG bytes")
    compare.add_argument("before", type=Path)
    compare.add_argument("after", type=Path)
    compare.add_argument("--gap", type=int, default=15)
    display = commands.add_parser("edid", help="decode a standalone EDID")
    display.add_argument("path", type=Path)
    build = commands.add_parser("build-ec", help="create an UNSIGNED research BIOSIMG with r04 EC regions")
    build.add_argument("stock", type=Path)
    build.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            data = args.image.read_bytes()
            image = firmware.bios_image(data)
            emit({"input_sha256": firmware.sha256(data), "biosimg_sha256": firmware.sha256(image),
                  "chunks": [{"name": c.name, "offset": c.payload_offset, "size": len(c.data),
                              "sha256": firmware.sha256(c.data)} for c in firmware.chunks(data)],
                  "ec": firmware.describe_ec(image), "edids": edid.scan(image)})
        elif args.command == "extract":
            data = firmware.bios_image(args.image.read_bytes())
            with args.output.open("xb") as output:
                output.write(data)
            emit({"output": str(args.output), "sha256": firmware.sha256(data)})
        elif args.command == "edid":
            emit(edid.decode(args.path.read_bytes()))
        elif args.command == "diff":
            a, b = (firmware.bios_image(p.read_bytes()) for p in (args.before, args.after))
            emit({"before_sha256": firmware.sha256(a), "after_sha256": firmware.sha256(b),
                  "changed_bytes": sum(x != y for x, y in zip(a, b)),
                  "spans": [{"start": s, "end": e, "start_hex": hex(s), "end_hex": hex(e),
                             "length": e - s, "before_sha256": firmware.sha256(a[s:e]),
                             "after_sha256": firmware.sha256(b[s:e])}
                            for s, e in firmware.diff_spans(a, b, args.gap)]})
        elif args.command == "build-ec":
            if args.output.suffix.lower() != ".bin":
                raise ValueError("research output must use .bin, not a signed .fd filename")
            data = firmware.build_r04_ec_reproduction(args.stock.read_bytes())
            with args.output.open("xb") as output:
                output.write(data)
            emit({"output": str(args.output), "sha256": firmware.sha256(data),
                  "status": "UNSIGNED, NOT HARDWARE VALIDATED; reproduces the r04 second-bank anomaly",
                  "ec": firmware.describe_ec(data)})
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
