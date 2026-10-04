"""Read cached internal-connector properties without probing or changing displays.

Only libdrm object/property GET calls are used. In particular, do not acquire
DRM master, set client capabilities, query connectors (which can reprobe), read
AUX/MMIO/debugfs, or submit a modeset. A missing property is not a false value.
"""

import ctypes as C
import hashlib
import os
from pathlib import Path
import platform


class ObjectProperties(C.Structure):
    _fields_ = [("count_props", C.c_uint32),
                ("props", C.POINTER(C.c_uint32)),
                ("prop_values", C.POINTER(C.c_uint64))]


class Property(C.Structure):
    # Stable public libdrm ABI, xf86drmMode.h (not kernel ioctl structs).
    _fields_ = [("prop_id", C.c_uint32), ("flags", C.c_uint32),
                ("name", C.c_char * 32), ("count_values", C.c_int),
                ("values", C.POINTER(C.c_uint64)), ("count_enums", C.c_int),
                ("enums", C.c_void_p), ("count_blobs", C.c_int),
                ("blob_ids", C.POINTER(C.c_uint32))]


def load_libdrm():
    drm = C.CDLL("libdrm.so.2", use_errno=True)
    signatures = {
        "drmModeObjectGetProperties":
            ([C.c_int, C.c_uint32, C.c_uint32], C.POINTER(ObjectProperties)),
        "drmModeGetProperty": ([C.c_int, C.c_uint32], C.POINTER(Property)),
        "drmModeFreeObjectProperties": ([C.POINTER(ObjectProperties)], None),
        "drmModeFreeProperty": ([C.POINTER(Property)], None),
    }
    for name, (args, result) in signatures.items():
        function = getattr(drm, name)
        function.argtypes, function.restype = args, result
    return drm


def connector_properties(drm, fd, connector_id):
    pointer = drm.drmModeObjectGetProperties(fd, connector_id, 0xC0C0C0C0)
    if not pointer:
        raise OSError(C.get_errno(), "cannot read connector properties")
    result = {}
    try:
        props = pointer.contents
        if props.count_props > 256:
            raise ValueError("unexpected property count")
        for index in range(props.count_props):
            prop = drm.drmModeGetProperty(fd, props.props[index])
            if not prop:
                raise OSError(C.get_errno(), "cannot read property metadata")
            try:
                name = prop.contents.name.decode("ascii", errors="replace")
                # Capability only; avoid collecting desktop settings/blob IDs.
                if name == "vrr_capable":
                    result[name] = int(props.prop_values[index])
            finally:
                drm.drmModeFreeProperty(prop)
    finally:
        drm.drmModeFreeObjectProperties(pointer)
    return result


def collect():
    if platform.system() != "Linux":
        raise RuntimeError("run on Linux using the SSH streaming tool")
    result = {"schema": 1, "kernel": platform.release(), "connectors": [],
              "method": "cached DRM object/property GET queries on O_RDONLY fd"}
    drm = load_libdrm()
    for path in sorted(Path("/sys/class/drm").glob("card*-eDP-*")):
        entry = {"name": path.name}
        result["connectors"].append(entry)
        try:
            entry["status"] = (path / "status").read_text().strip()
            connector_id = int((path / "connector_id").read_text())
            data = (path / "edid").read_bytes()
            entry["edid_sha256"] = hashlib.sha256(data).hexdigest()
            card = path.name.split("-", 1)[0]
            fd = os.open("/dev/dri/" + card, os.O_RDONLY | os.O_CLOEXEC)
            try:
                entry["properties"] = connector_properties(drm, fd, connector_id)
            finally:
                os.close(fd)
        except (OSError, ValueError) as error:
            entry["error"] = str(error)
    return result
