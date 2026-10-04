#!/usr/bin/env python3
"""Measure VRR-relevant metadata in the pinned r04 BIOSIMG, entirely offline."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from opendecksight.edid import decode
from opendecksight.firmware import (
    EC_BASES, EXTENDED_EDID_OFFSET, R04_SHA256, bios_image, r04_edid, sha256,
)

LUA_SHA256 = "f47e4ee9dec2533e86fe784b339bff9bcbd0c2af38c9f157ffd04fb33b879bd7"


def inspect(data):
    image = bios_image(data)
    if sha256(image) != R04_SHA256:
        raise ValueError("expected the pinned r04 BIOSIMG")
    lua = (ROOT / "third_party/gamescope/DeckSight.lua").read_bytes()
    if sha256(lua) != LUA_SHA256:
        raise ValueError("profile changed; recheck the timing interpretation")
    edid = image[EXTENDED_EDID_OFFSET:EXTENDED_EDID_OFFSET + 256]
    if edid != r04_edid():
        raise ValueError("EDID differs from the semantic reconstruction")
    descriptors = [edid[i:i + 18] for i in range(54, 126, 18)]
    tables = []
    for base in EC_BASES:
        records = []
        for offset in range(0x6965, 0x6980, 3):
            raw = image[base + offset:base + offset + 3]
            records.append({"ec_offset": hex(offset), "bytes_hex": raw.hex(),
                            "address": hex(int.from_bytes(raw[:2], "big")),
                            "value": raw[2]})
            if raw == b"\xff\xff\xff":
                break
        else:
            raise ValueError("link table terminator missing")
        tables.append({"ec_base": hex(base), "records": records,
                       "contains_0x1007": any(r["address"] == "0x1007" for r in records)})
    # These constants are interpreted from the hash-checked public Lua profile.
    htotal = 1080 + 48 + 32 + 80
    vtotal = 1920 + 3 + 14 + 61
    clock80 = htotal * vtotal * 80
    return {
        "schema": 1,
        "scope": "public artifact static analysis; no live register values or device settings",
        "inputs": {"r04_biosimg_sha256": sha256(image), "gamescope_lua_sha256": sha256(lua)},
        "edid": {
            "sha256": sha256(edid), "decoded": decode(edid),
            "base_range_descriptor_count": sum(d[:5] == b"\x00\x00\x00\xfd\x00" for d in descriptors),
            "extension_tags": [edid[i] for i in range(128, len(edid), 128)],
        },
        "ec_link_configuration_tables": tables,
        "ideal_timing_arithmetic": {
            "note": "illustration, not validated modes; real clocks are quantized",
            "fixed_40_hz": {"clock_hz": htotal * vtotal * 40, "htotal": htotal,
                            "vtotal": vtotal, "v_front": 3},
            "fixed_80_hz": {"clock_hz": clock80, "htotal": htotal,
                            "vtotal": vtotal, "v_front": 3},
            "hypothetical_40_hz_vrr_frame_at_80_hz_clock": {
                "clock_hz": clock80, "htotal": htotal,
                "vtotal": vtotal * 2, "v_front": 3 + vtotal},
        },
        "unresolved": ["live DPCD 0x00007 bit 6", "bridge variable-interval behavior",
                       "panel controller identity and timing limits", "true VRR physical scanout"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(args.image.read_bytes()), indent=2))
    except (OSError, ValueError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
