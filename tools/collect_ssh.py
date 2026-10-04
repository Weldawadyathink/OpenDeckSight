#!/usr/bin/env python3
"""Stream the read-only collector over SSH, without creating remote files."""

import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def collector_program(kind="baseline"):
    if kind not in ("baseline", "vrr", "dpcd"):
        raise ValueError("unknown collector")
    program = ["import sys, types, json", "sys.dont_write_bytecode = True",
               "package = types.ModuleType('opendecksight')", "package.__path__ = []",
               "sys.modules['opendecksight'] = package"]
    for name in (("edid", "collect") if kind == "baseline" else (kind,)):
        source = (ROOT / "opendecksight" / (name + ".py")).read_text()
        full_name = "opendecksight." + name
        program.extend([f"module = types.ModuleType({full_name!r})",
                        "module.__package__ = 'opendecksight'",
                        f"sys.modules[{full_name!r}] = module",
                        f"exec(compile({source!r}, '<streamed-{name}>', 'exec'), module.__dict__)"])
    module_name = "collect" if kind == "baseline" else kind
    program.append(f"print(json.dumps(sys.modules['opendecksight.{module_name}'].collect(), indent=2))")
    return "\n".join(program) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", help="user@host; SSH key/Tailscale authentication only")
    parser.add_argument("--output", required=True, type=Path, help="new LOCAL JSON file")
    parser.add_argument("--kind", choices=("baseline", "vrr", "dpcd"), default="baseline",
                        help="baseline inventory, cached VRR query, or 16-byte native AUX capability read")
    parser.add_argument("--sudo-read-only", action="store_true",
                        help="DPCD only: use sudo -n for the bounded read; never prompt for a password")
    args = parser.parse_args()
    if args.sudo_read_only and args.kind != "dpcd":
        parser.error("--sudo-read-only is restricted to --kind dpcd")
    if args.target.startswith("-") or any(c.isspace() for c in args.target):
        parser.error("invalid SSH target")
    if args.output.exists():
        parser.error("local output already exists")
    try:
        result = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "UpdateHostKeys=no",
             "-o", "ConnectTimeout=10", args.target,
             "sudo -n python3 -B -" if args.sudo_read_only else "python3 -B -"],
            input=collector_program(args.kind), capture_output=True, text=True, timeout=45, check=True)
        report = json.loads(result.stdout)
        with args.output.open("x") as output:
            json.dump(report, output, indent=2)
            output.write("\n")
        print(f"Saved local read-only report: {args.output}")
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        detail = error.stderr if isinstance(error, subprocess.CalledProcessError) else str(error)
        parser.exit(1, f"error: {detail}\n")


if __name__ == "__main__":
    main()
