#!/usr/bin/env python3
"""Verify real-artifact EC reproduction and emit a deterministic evidence report."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from opendecksight.firmware import (EC_BASES, EC_SIZE, bios_image, build_r04_ec_reproduction,
                                  describe_ec, diff_spans, sha256)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock", type=Path, default=ROOT / "artifacts/extracted/stock/usr/share/jupiter_bios/F7A0133_sign.fd")
    parser.add_argument("--r04", type=Path, default=ROOT / "artifacts/extracted/r04/bios/F7A0133_DeckSight_signed_r04.fd")
    parser.add_argument("--r03", type=Path, default=ROOT / "artifacts/extracted/r03/bios/F7A0133_DeckSight_signed_r03.fd")
    args = parser.parse_args()
    try:
        manifest = json.loads((ROOT / "research/artifacts.json").read_text())
        images = {}
        for release, path in (("stock", args.stock), ("r03", args.r03), ("r04", args.r04)):
            data = bios_image(path.read_bytes())
            expected = next(r["sha256"] for r in manifest["payloads"]
                            if r["release"] == release and r["path"].endswith("chunks/BIOSIMG.bin"))
            if sha256(data) != expected:
                raise ValueError(f"unexpected {release} BIOSIMG hash")
            images[release] = data
        stock, released = images["stock"], images["r04"]
        built = build_r04_ec_reproduction(stock)
        regions = []
        for base in EC_BASES:
            a, b = built[base:base + EC_SIZE], released[base:base + EC_SIZE]
            regions.append({"base": base, "length": EC_SIZE, "reproduced_sha256": sha256(a),
                            "released_sha256": sha256(b), "identical": a == b})
        outside_unchanged = (built[0x20000:0x40000] == stock[0x20000:0x40000]
                             and built[0x60000:] == stock[0x60000:])
        if not outside_unchanged or not all(r["identical"] for r in regions):
            raise ValueError("reproduction failed; EC mismatch or changes outside EC banks")
        comparisons = []
        for before, after in (("stock", "r03"), ("r03", "r04")):
            a, b = images[before], images[after]
            comparisons.append({"before": before, "after": after,
                                "changed_bytes": sum(x != y for x, y in zip(a, b)),
                                "spans_gap_15": [{"start": hex(s), "end": hex(e), "size": e - s}
                                                 for s, e in diff_spans(a, b, gap=15)]})
        print(json.dumps({"stock_sha256": sha256(stock), "r04_sha256": sha256(released),
                          "research_output_sha256": sha256(built), "ec": regions,
                          "outside_ec_unchanged": outside_unchanged,
                          "ec_checksums": describe_ec(built), "comparisons": comparisons}, indent=2))
    except (OSError, ValueError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
