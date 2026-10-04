#!/usr/bin/env python3
"""Build a USB lab disk image in an unprivileged Docker container; never flash it."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def fetch_kernel(cache):
    lock = json.loads((ROOT / "lab/usb/kernel.lock.json").read_text())
    repo = lock["repository"]
    with urllib.request.urlopen("https://ghcr.io/token?service=ghcr.io&scope=repository:"
                                + repo + ":pull", timeout=30) as response:
        token = json.load(response)["token"]
    request = urllib.request.Request(
        "https://ghcr.io/v2/" + repo + "/manifests/" + lock["manifest_digest"],
        headers={"Authorization": "Bearer " + token,
                 "Accept": "application/vnd.oci.image.manifest.v1+json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read()
    if "sha256:" + hashlib.sha256(data).hexdigest() != lock["manifest_digest"]:
        raise ValueError("Kernel OCI manifest hash mismatch")
    manifest = json.loads(data)
    (cache / "kernel-oci-manifest.json").write_bytes(data)
    available = {(x.get("annotations", {}).get("org.opencontainers.image.title"),
                  x["digest"], x["size"]) for x in manifest["layers"]}
    for entry in lock["packages"]:
        expected = (entry["name"], "sha256:" + entry["sha256"], entry["size"])
        if expected not in available:
            raise ValueError("Kernel package not present in pinned OCI manifest")
        path = cache / entry["name"]
        if not path.exists():
            request = urllib.request.Request("https://ghcr.io/v2/" + repo + "/blobs/sha256:"
                                             + entry["sha256"],
                                             headers={"Authorization": "Bearer " + token})
            temp = path.with_suffix(".partial")
            with urllib.request.urlopen(request, timeout=90) as response, temp.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
            temp.rename(path)
        if path.stat().st_size != entry["size"] or hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError("Cached kernel package hash mismatch: " + entry["name"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts/usb-lab")
    parser.add_argument("--refresh-runtime", action="store_true",
                        help="resolve a new Fedora package set instead of reusing the saved lock/cache")
    parser.add_argument("--skip-builder-build", action="store_true", help="reuse the local builder image")
    args = parser.parse_args()
    out = args.output_dir.resolve()
    if out != (ROOT / "artifacts").resolve() and (ROOT / "artifacts").resolve() not in out.parents:
        parser.error("Keep image outputs and downloads inside this repository's ignored artifacts/ directory")
    out.mkdir(parents=True, exist_ok=True)
    cache = out / "inputs"
    cache.mkdir(exist_ok=True)
    subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"], check=True)
    fetch_kernel(cache)
    if not args.skip_builder_build:
        subprocess.run(["docker", "build", "--platform", "linux/amd64", "-t", "opendecksight-lab-builder",
                        "-f", str(ROOT / "lab/usb/Containerfile"), str(ROOT / "lab/usb")], check=True)
    command = ["docker", "run", "--rm", "--platform", "linux/amd64",
               "--mount", f"type=bind,src={ROOT},dst=/src,readonly",
               "--mount", f"type=bind,src={out},dst=/out",
               "-e", "ODS_REFRESH_RUNTIME=" + ("1" if args.refresh_runtime else "0"),
               "opendecksight-lab-builder", "/src/lab/usb/build.sh"]
    subprocess.run(command, check=True)
    print("Created " + str(out / "opendecksight-lab.img"))
    print("No USB device was written. See docs/usb-lab.md for configuration and boot testing.")


if __name__ == "__main__":
    main()
