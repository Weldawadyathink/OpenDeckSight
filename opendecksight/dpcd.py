"""Read only the 16-byte DP receiver capability block of the known r04 sink.

This sends native AUX reads through the kernel; unlike vrr.py it is not a
cached-property query. No arbitrary address, write, MMIO or modeset interface
is exposed. Capability advertisement is not a physical VRR pass-through test.
"""

import hashlib
import os
from pathlib import Path
import platform
import stat

R04_EDID_SHA256 = "53c47cbd31b785b332a890d5074b46ac4efe88d96cc210b041ee07773a4dfe48"


def decode_receiver_caps(data):
    if len(data) != 16:
        raise ValueError("expected exactly 16 receiver capability bytes")
    return {
        "dpcd_revision_hex": hex(data[0]),
        "max_link_rate_code_hex": hex(data[1]),
        "max_lane_count": data[2] & 0x1F,
        "msa_timing_parameters_ignored": bool(data[7] & 0x40),
        "extended_receiver_caps_present": bool(data[14] & 0x80),
    }


def read_receiver_caps(fd):
    # One userspace read; the kernel may retry native AUX transactions.
    data = os.pread(fd, 16, 0)
    return data, decode_receiver_caps(data)


def collect():
    if platform.system() != "Linux":
        raise RuntimeError("run on Linux using a streamed collector")
    connectors = list(Path("/sys/class/drm").glob("card*-eDP-*"))
    if len(connectors) != 1:
        raise ValueError("expected exactly one internal eDP connector")
    connector = connectors[0]
    if (connector / "status").read_text().strip() != "connected":
        raise ValueError("internal display is not connected")
    edid_hash = hashlib.sha256((connector / "edid").read_bytes()).hexdigest()
    if edid_hash != R04_EDID_SHA256:
        raise ValueError("refusing AUX read: internal EDID does not match r04")
    candidates = list(connector.glob("drm_dp_aux[0-9]*"))
    if len(candidates) != 1:
        raise ValueError("expected exactly one AUX device under the internal connector")
    aux = candidates[0]
    if aux.resolve().parent != connector.resolve():
        raise ValueError("AUX device is not a child of the internal connector")
    major, minor = (int(v) for v in (aux / "dev").read_text().strip().split(":"))
    fd = os.open("/dev/" + aux.name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISCHR(metadata.st_mode) or metadata.st_rdev != os.makedev(major, minor):
            raise ValueError("device node does not match internal AUX sysfs entry")
        data, decoded = read_receiver_caps(fd)
    finally:
        os.close(fd)
    return {
        "schema": 1, "kernel": platform.release(),
        "method": "O_RDONLY native AUX receiver-capability read at 0x00000, length 16",
        "connector": connector.name, "aux_device": aux.name,
        "edid_sha256": edid_hash, "receiver_caps_hex": data.hex(),
        "receiver_caps_sha256": hashlib.sha256(data).hexdigest(),
        "decoded": decoded,
        "limit": "advertised base capabilities only; no VRR signal or physical scanout test",
    }
