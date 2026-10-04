"""Resolve once, then verify/reuse exact signed Fedora RPM inputs."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

cache = Path("/out/inputs/runtime")
lock = Path("/out/inputs/runtime.lock.json")
refresh = os.environ.get("ODS_REFRESH_RUNTIME") == "1"
if refresh and cache.exists():
    suffix = str(time.time_ns())
    cache.rename(cache.with_name("runtime.previous-" + suffix))
    if lock.exists():
        lock.rename(lock.with_name("runtime.previous-" + suffix + ".json"))
cache.mkdir(parents=True, exist_ok=True)
default_lock = Path('/src/lab/usb/runtime.lock.json')
if not lock.exists() and not refresh and default_lock.exists():
    shutil.copyfile(default_lock, lock)
subprocess.run(["rpm", "--import", "/etc/pki/rpm-gpg/RPM-GPG-KEY-fedora-44-x86_64"], check=True)
if lock.exists():
    entries = json.loads(lock.read_text())["packages"]
    missing = [x["nevra"] for x in entries if not (cache / x["file"]).exists()]
    if missing:
        subprocess.run(["dnf", "download", "--destdir", str(cache)] + missing, check=True)
else:
    packages = [line.strip() for line in Path("/src/lab/usb/runtime-packages.txt").read_text().splitlines()
                if line.strip() and not line.startswith("#")]
    # Resolve one install transaction against an empty root; `download --resolve`
    # can collect multiple versions/architectures rather than a coherent rootfs.
    subprocess.run(["dnf", "-y", "--installroot=/work/resolve-root", "--releasever=44",
                    "--use-host-config", "--setopt=install_weak_deps=False",
                    "--setopt=destdir=" + str(cache), "install", "--downloadonly"] + packages, check=True)
    entries = []
    for path in sorted(cache.glob("*.rpm")):
        metadata = subprocess.run(["rpm", "-qp", "--qf", "%{NEVRA}\n%{SOURCERPM}\n", str(path)],
                                  check=True, capture_output=True, text=True).stdout.splitlines()
        entries.append({"file": path.name, "size": path.stat().st_size,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "nevra": metadata[0], "source_rpm": metadata[1]})
expected = {entry["file"] for entry in entries}
if {path.name for path in cache.glob("*.rpm")} != expected:
    raise SystemExit("Unexpected RPMs in runtime cache; refusing an unlocked package set")
for entry in entries:
    path = cache / entry["file"]
    if path.stat().st_size != entry["size"] or hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
        raise SystemExit("Runtime input hash mismatch: " + entry["file"])
    subprocess.run(["rpmkeys", "--checksig", str(path)], check=True, stdout=subprocess.DEVNULL)
if not lock.exists():
    lock.write_text(json.dumps({"schema": 1, "origin": "Fedora 44 signed repositories",
                               "packages": entries}, indent=2) + "\n")
print("Verified", len(entries), "locked Fedora RPM inputs.", flush=True)
