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
    full = commands.add_parser("build-biosimg", help="rebuild the complete byte-identical r04 BIOSIMG")
    full.add_argument("stock", type=Path)
    full.add_argument("output", type=Path)
    full.add_argument("--splash", required=True, type=Path)
    full.add_argument("--uefireplace", required=True, type=Path)
    signed = commands.add_parser("build-fd", help="reconstruct historical r04 .fd by explicitly reusing its signatures")
    signed.add_argument("stock", type=Path)
    signed.add_argument("output", type=Path)
    signed.add_argument("--splash", required=True, type=Path)
    signed.add_argument("--uefireplace", required=True, type=Path)
    signed.add_argument("--reuse-release-signatures", required=True, type=Path,
                        help="directory with the three extracted r04 signatures; this does not sign new firmware")
    bright = commands.add_parser("brightness", help="preview brightness protocol; writes require --apply-mmio")
    bright.add_argument("--raw", type=int)
    bright.add_argument("--max", dest="maximum", type=int)
    bright.add_argument("--watch", action="store_true")
    bright.add_argument("--apply-mmio", action="store_true")
    bright.add_argument("--backlight", type=Path, help="brightness file for read-only preview")
    collect = commands.add_parser("collect", help="collect read-only Deck diagnostics without sudo")
    collect.add_argument("output", type=Path)
    panel = commands.add_parser("panel-init", help="decode EC initialization packets and unresolved commands")
    panel.add_argument("image", type=Path)
    panel.add_argument("--bank", type=int, choices=(0, 1), default=0)
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
        elif args.command == "build-biosimg":
            from .build import build_biosimg
            if args.output.suffix.lower() != ".bin":
                raise ValueError("BIOSIMG output must use .bin; this does not produce a signed .fd")
            if args.output.exists():
                raise ValueError("output already exists")
            data, report = build_biosimg(args.stock.read_bytes(), args.splash.read_bytes(), args.uefireplace)
            with args.output.open("xb") as output:
                output.write(data)
            emit({"output": str(args.output), "sha256": firmware.sha256(data),
                  "status": "byte-identical r04 BIOSIMG; not a signed update container", **report})
        elif args.command == "brightness":
            from .brightness import run
            run(args)
        elif args.command == "build-fd":
            from .build import build_biosimg
            from .container import SIGNATURE_HASHES, build_container
            if args.output.suffix.lower() != ".fd":
                raise ValueError("historical container output must use .fd")
            if args.output.exists():
                raise ValueError("output already exists")
            stock = args.stock.read_bytes()
            signatures = {name: (args.reuse_release_signatures / name).read_bytes() for name in SIGNATURE_HASHES}
            biosimg, report = build_biosimg(stock, args.splash.read_bytes(), args.uefireplace)
            data = build_container(stock, biosimg, signatures)
            with args.output.open("xb") as output:
                output.write(data)
            emit({"output": str(args.output), "sha256": firmware.sha256(data), "size": len(data),
                  "biosimg_sha256": firmware.sha256(biosimg),
                  "signature_mode": "explicit reuse of three existing historical r04 signatures; no new signing key",
                  "signature_resources": [{"name": n, "size": len(b), "sha256": firmware.sha256(b)}
                                          for n, b in signatures.items()],
                  "status": "byte-identical historical r04 .fd; vendor-command semantics and hardware validation remain incomplete",
                  **report})
        elif args.command == "panel-init":
            from .panel import inspect
            emit(inspect(args.image.read_bytes(), args.bank))
        elif args.command == "collect":
            from .collect import collect
            report = collect()
            with args.output.open("x") as output:
                json.dump(report, output, indent=2)
                output.write("\n")
            emit({"output": str(args.output)})
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
