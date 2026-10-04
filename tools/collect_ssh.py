#!/usr/bin/env python3
"""Stream the read-only collector over SSH, without creating remote files."""

import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def collector_program():
    program = ["import sys, types, json", "sys.dont_write_bytecode = True",
               "package = types.ModuleType('opendecksight')", "package.__path__ = []",
               "sys.modules['opendecksight'] = package"]
    for name in ("edid", "collect"):
        source = (ROOT / "opendecksight" / (name + ".py")).read_text()
        full_name = "opendecksight." + name
        program.extend([f"module = types.ModuleType({full_name!r})",
                        "module.__package__ = 'opendecksight'",
                        f"sys.modules[{full_name!r}] = module",
                        f"exec(compile({source!r}, '<streamed-{name}>', 'exec'), module.__dict__)"])
    program.append("print(json.dumps(sys.modules['opendecksight.collect'].collect(), indent=2))")
    return "\n".join(program) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", help="user@host; SSH key/Tailscale authentication only")
    parser.add_argument("--output", required=True, type=Path, help="new LOCAL JSON file")
    args = parser.parse_args()
    if args.target.startswith("-") or any(c.isspace() for c in args.target):
        parser.error("invalid SSH target")
    if args.output.exists():
        parser.error("local output already exists")
    try:
        result = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "UpdateHostKeys=no",
             "-o", "ConnectTimeout=10", args.target, "python3 -B -"],
            input=collector_program(), capture_output=True, text=True, timeout=45, check=True)
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
