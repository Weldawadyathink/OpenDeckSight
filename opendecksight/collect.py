"""Read-only, bounded device inventory. Does not read serial numbers or journals."""

import hashlib
from pathlib import Path
import platform
import subprocess

from .edid import decode


def read(path, binary=False, limit=16384):
    try:
        with path.open("rb") as source:
            data = source.read(limit + 1)
        if len(data) > limit:
            return {"error": "exceeds collection limit"}
        return data if binary else data.decode("utf-8", errors="replace").strip()
    except OSError as error:
        return {"error": error.strerror}


def service_state(name):
    try:
        result = subprocess.run(
            ["systemctl", "show", name, "--no-pager", "--property=LoadState,ActiveState,SubState,FragmentPath"],
            capture_output=True, text=True, timeout=5, check=False)
        return {"returncode": result.returncode, "properties": result.stdout[:8192]}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"error": type(error).__name__}


def collect():
    if platform.system() != "Linux":
        raise RuntimeError("run the collector on the Steam Deck's Linux OS")
    dmi = Path("/sys/class/dmi/id")
    result = {"schema": 1, "kernel": platform.release(), "machine": platform.machine(),
              "dmi": {key: read(dmi / key) for key in
                      ("board_vendor", "board_name", "bios_version", "bios_date")},
              "os": {}, "connectors": [], "backlights": [], "services": {}}
    os_release = read(Path("/etc/os-release"))
    if isinstance(os_release, str):
        for line in os_release.splitlines():
            key, separator, value = line.partition("=")
            if separator and key in ("ID", "NAME", "PRETTY_NAME", "VERSION_ID", "BUILD_ID", "VARIANT_ID"):
                result["os"][key] = value.strip('"')
    for path in sorted(Path("/sys/class/drm").glob("card*-eDP-*")):
        connector = {"name": path.name, "status": read(path / "status"), "modes": read(path / "modes")}
        data = read(path / "edid", binary=True)
        if isinstance(data, bytes):
            connector["edid_hex"] = data.hex()
            try:
                connector["edid"] = decode(data)
            except ValueError as error:
                connector["edid_error"] = str(error)
        else:
            connector["edid_error"] = data
        result["connectors"].append(connector)
    for path in sorted(Path("/sys/class/backlight").glob("*")):
        result["backlights"].append({"name": path.name, **{key: read(path / key) for key in
                                      ("brightness", "actual_brightness", "max_brightness", "type")}})
    for name in ("decksight-brightnessctrl.service", "opendecksight-brightness.service"):
        result["services"][name] = service_state(name)
    result["installed_brightness_binaries"] = []
    for directory in ("/var/local/bin", "/usr/local/bin"):
        path = Path(directory) / "decksight-brightnessctrl"
        if path.exists():
            data = read(path, binary=True, limit=4 * 1024 * 1024)
            if isinstance(data, bytes):
                result["installed_brightness_binaries"].append({"path": str(path), "size": len(data),
                                                               "sha256": hashlib.sha256(data).hexdigest()})
    return result
