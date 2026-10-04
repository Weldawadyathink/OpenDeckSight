#!/usr/bin/env python3
"""Compile and exercise pinned AMD VRR arithmetic locally, without a GPU.

Downloads are opt-in. Generated source/executables stay in ignored .tools/.
This is a userspace unit harness, not a kernel build or a hardware test.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "drivers/gpu/drm/amd/display/modules/freesync/freesync.c"
HEADER = "drivers/gpu/drm/amd/display/modules/inc/mod_freesync.h"
FUNCTIONS = [
    "calc_duration_in_us_from_refresh_in_uhz",
    "calc_max_hardware_v_total",
    "mod_freesync_calc_v_total_from_refresh",
    "mod_freesync_calc_nominal_field_rate",
    "vrr_settings_require_update",
    "mod_freesync_build_vrr_params",
    "apply_fixed_refresh",
]


def extract_function(source, name):
    """Extract an unchanged top-level definition from the hash-pinned source."""
    match = re.search(r"^(?:static )?(?:unsigned (?:long long|int)|void|bool) "
                      + re.escape(name) + r"\([^;{}]*\)\n\{.*?^\}", source, re.M | re.S)
    if not match:
        raise ValueError(f"function not found: {name}")
    return match.group(0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", help="fetch missing public sources locally")
    parser.add_argument("--cc", default="cc", help="local C compiler command")
    parser.add_argument("--output", type=Path, help="write a local JSON test report")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "research/vrr-kernel-sources.json").read_text())
    sources = {entry["path"]: entry for entry in manifest["sources"]}
    text = {}
    for name in (SOURCE, HEADER):
        path = ROOT / "artifacts/vrr/kernel-source" / name
        entry = sources[name]
        if not path.exists() and args.fetch:
            with urllib.request.urlopen(entry["url"], timeout=30) as response:
                data = response.read()
            if hashlib.sha256(data).hexdigest() != entry["sha256"]:
                raise ValueError(f"download hash mismatch: {name}")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise ValueError(f"source hash mismatch: {name}")
        text[name] = data.decode()

    source, header = text[SOURCE], text[HEADER]
    # Preserve the AMD license notices in the generated translation unit.
    notices = source[:source.index("#include")] + header[:header.index("#ifndef")]
    definitions = header[header.index("// Access structures"):
                         header.index("struct mod_freesync *mod_freesync_create")]
    constants = "\n".join(re.findall(r"^#define (?:MIN_REFRESH_RANGE|BTR_MAX_MARGIN|"
                                   r"FIXED_REFRESH_\w+)[^\n]*", source, re.M))
    functions = "\n\n".join(extract_function(source, name) for name in FUNCTIONS)
    scaffolding = (ROOT / "tests/fixtures/vrr_kernel_stubs.h").read_text()
    cases = (ROOT / "tests/fixtures/vrr_kernel_cases.c").read_text()
    build = ROOT / ".tools/vrr-kernel-tests"
    build.mkdir(parents=True, exist_ok=True)
    compiler = shlex.split(args.cc)
    runs = []
    for threshold in (10, 1):
        # A local control experiment ONLY. This is not a proposed global patch.
        altered = constants.replace("#define MIN_REFRESH_RANGE 10",
                                    f"#define MIN_REFRESH_RANGE {threshold}")
        assert altered.count(f"#define MIN_REFRESH_RANGE {threshold}") == 1
        unit = build / f"range-{threshold}.c"
        exe = build / f"range-{threshold}"
        unit.write_text(notices + scaffolding + definitions + "\n" + altered
                        + "\n" + functions + "\n" + cases)
        subprocess.run(compiler + ["-std=c11", "-Wall", "-Wextra", "-Werror",
                                   "-fsanitize=undefined", "-fno-sanitize-recover=all",
                                   str(unit), "-o", str(exe)], check=True)
        result = subprocess.run([str(exe)], capture_output=True, text=True, check=True)
        runs.append({"minimum_range_hz": threshold, "cases": json.loads(result.stdout)})
    report = {
        "schema": 1,
        "scope": "Local userspace tests of extracted source functions with minimal data stubs; no device I/O, kernel boot or electrical evidence.",
        "source_commit": manifest["commit"],
        "source_hashes": {name: sources[name]["sha256"] for name in (SOURCE, HEADER)},
        "functions": FUNCTIONS,
        "fixture": "Public r04 EDID timing: 143.18 MHz, 1220 x 1956 total, 8-line vertical front porch. Range fields and hardware limits are synthetic test inputs.",
        "compiler": subprocess.run(compiler + ["--version"], capture_output=True,
                                   text=True, check=True).stdout.splitlines()[0],
        "runs": runs,
    }
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered)
        print(f"Passed {sum(len(run['cases']) for run in runs)} source-function cases; saved {args.output}")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
