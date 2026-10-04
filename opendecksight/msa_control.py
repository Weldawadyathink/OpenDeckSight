"""Read one standard eDP control byte, DPCD 0x107, on the exact internal r04 sink.

No writes, arbitrary addresses, MMIO or modesets. This is separate from the
receiver-capability collector so its original 16-byte scope remains unchanged.
"""
import hashlib
import os
from pathlib import Path
import stat
from .dpcd import R04_EDID_SHA256


def read_control(fd):
    data = os.pread(fd, 1, 0x107)
    if len(data) != 1:
        raise ValueError('short MSA control read')
    return {'address': '0x107', 'value_hex': data.hex(),
            'ignore_msa_enabled': bool(data[0] & 0x80)}


def collect():
    connectors = list(Path('/sys/class/drm').glob('card*-eDP-*'))
    if len(connectors) != 1:
        raise ValueError('expected exactly one internal eDP connector')
    connector = connectors[0]
    if (connector / 'status').read_text().strip() != 'connected':
        raise ValueError('internal display disconnected')
    if hashlib.sha256((connector / 'edid').read_bytes()).hexdigest() != R04_EDID_SHA256:
        raise ValueError('exact r04 EDID required')
    candidates = list(connector.glob('drm_dp_aux[0-9]*'))
    if len(candidates) != 1 or candidates[0].resolve().parent != connector.resolve():
        raise ValueError('internal AUX association not established')
    aux = candidates[0]
    major, minor = map(int, (aux / 'dev').read_text().strip().split(':'))
    fd = os.open('/dev/' + aux.name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISCHR(info.st_mode) or info.st_rdev != os.makedev(major, minor):
            raise ValueError('AUX device-node identity mismatch')
        return read_control(fd)
    finally:
        os.close(fd)
