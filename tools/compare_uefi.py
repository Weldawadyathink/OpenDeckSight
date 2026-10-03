#!/usr/bin/env python3
"""Compare UEFIExtract leaf payloads; report paths/hashes, never embed firmware."""

import argparse
import hashlib
import json
from pathlib import Path


def inventory(root):
    if not root.is_dir():
        raise ValueError(f"not a UEFIExtract dump directory: {root}")
    result = {}
    for path in root.rglob("body.bin"):
        # Parent objects include their children; compare leaves separately.
        if any(path.parent.glob("*/info.txt")):
            continue
        data = path.read_bytes()
        result[str(path.relative_to(root))] = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    if not result:
        raise ValueError(f"no leaf bodies in {root}")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stock", type=Path)
    parser.add_argument("modified", type=Path)
    args = parser.parse_args()
    try:
        a, b = inventory(args.stock), inventory(args.modified)
        print(json.dumps({"method": "UEFIExtract A75 leaf body paths and SHA-256; parser coverage only",
                          "stock_leaf_count": len(a), "modified_leaf_count": len(b),
                          "unchanged_leaf_count": sum(a[k] == b[k] for k in a.keys() & b.keys()),
                          "changed": [{"path": k, "before": a[k], "after": b[k]}
                                      for k in sorted(a.keys() & b.keys()) if a[k] != b[k]],
                          "added": [{"path": k, **b[k]} for k in sorted(b.keys() - a.keys())],
                          "removed": [{"path": k, **a[k]} for k in sorted(a.keys() - b.keys())]}, indent=2))
    except (ValueError, OSError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
