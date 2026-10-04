"""Validate VRR requests with DRM_MODE_ATOMIC_TEST_ONLY, never apply them.

Requires the exact r04 eDP sink and its already-active native fixed mode.
Changes only this file descriptor's client capability. Does not modeset, flip,
change live properties, access AUX/MMIO, or request a new timing range.
"""

import ctypes as C
import hashlib
import os
from pathlib import Path
import platform
import struct

from .dpcd import R04_EDID_SHA256
from .vrr import load_libdrm

CONNECTOR = 0xC0C0C0C0
CRTC = 0xCCCCCCCC
ATOMIC_CLIENT_CAP = 3
TEST_ONLY = 0x0100
MODE = struct.Struct('=I10HIII32s')


class Blob(C.Structure):
    _fields_ = [('id', C.c_uint32), ('length', C.c_uint32), ('data', C.c_void_p)]


def load_atomic_libdrm():
    drm = load_libdrm()
    signatures = {
        'drmSetClientCap': ([C.c_int, C.c_uint64, C.c_uint64], C.c_int),
        'drmIsMaster': ([C.c_int], C.c_int),
        'drmModeGetPropertyBlob': ([C.c_int, C.c_uint32], C.POINTER(Blob)),
        'drmModeFreePropertyBlob': ([C.POINTER(Blob)], None),
        'drmModeAtomicAlloc': ([], C.c_void_p),
        'drmModeAtomicFree': ([C.c_void_p], None),
        'drmModeAtomicAddProperty':
            ([C.c_void_p, C.c_uint32, C.c_uint32, C.c_uint64], C.c_int),
        'drmModeAtomicCommit': ([C.c_int, C.c_void_p, C.c_uint32, C.c_void_p], C.c_int),
    }
    for name, (args, result) in signatures.items():
        function = getattr(drm, name)
        function.argtypes, function.restype = args, result
    return drm


def properties(drm, fd, object_id, kind, wanted):
    pointer = drm.drmModeObjectGetProperties(fd, object_id, kind)
    if not pointer:
        raise OSError(C.get_errno(), 'cannot read object properties')
    result = {}
    try:
        props = pointer.contents
        if props.count_props > 256:
            raise ValueError('unexpected property count')
        for index in range(props.count_props):
            prop = drm.drmModeGetProperty(fd, props.props[index])
            if not prop:
                raise OSError(C.get_errno(), 'cannot read property metadata')
            try:
                p = prop.contents
                name = p.name.decode('ascii', errors='replace')
                if name in wanted:
                    if name in result or not 0 <= p.count_values <= 16:
                        raise ValueError('unexpected property metadata')
                    result[name] = {'id': int(p.prop_id), 'value': int(props.prop_values[index]),
                                    'flags': int(p.flags),
                                    'values': [int(p.values[j]) for j in range(p.count_values)]}
            finally:
                drm.drmModeFreeProperty(prop)
    finally:
        drm.drmModeFreeObjectProperties(pointer)
    if result.keys() != set(wanted):
        raise ValueError('required properties missing: ' + ', '.join(sorted(set(wanted) - result.keys())))
    return result


def mode_bytes(drm, fd, blob_id):
    pointer = drm.drmModeGetPropertyBlob(fd, blob_id)
    if not pointer:
        raise OSError(C.get_errno(), 'cannot read active mode blob')
    try:
        if pointer.contents.length != MODE.size:
            raise ValueError('unexpected active mode blob size')
        return C.string_at(pointer.contents.data, MODE.size)
    finally:
        drm.drmModeFreePropertyBlob(pointer)


def require_native_mode(data):
    fields = MODE.unpack(data)
    # Clock, active/sync/total timing, skew, scan multiplier and sync flags.
    expected = (143180, 1080, 1112, 1120, 1220, 0, 1920, 1928, 1930, 1956, 0)
    if fields[:11] != expected or fields[12] != 5:
        raise ValueError('requires the existing exact native r04 timing')


def request_test_only(drm, fd, crtc_id, property_id, value):
    if type(value) is not int or value not in (0, 1, 2):
        raise ValueError('only off, on and invalid-boolean control are permitted')
    request = drm.drmModeAtomicAlloc()
    if not request:
        raise OSError(C.get_errno(), 'cannot allocate atomic request')
    try:
        if drm.drmModeAtomicAddProperty(request, crtc_id, property_id, value) < 0:
            raise OSError(C.get_errno(), 'cannot construct test request')
        C.set_errno(0)
        # Deliberately no flags argument or real-commit alternative for callers.
        result = drm.drmModeAtomicCommit(fd, request, TEST_ONLY, None)
        error = C.get_errno() if result else 0
        return {'requested_vrr_enabled': value, 'returncode': result, 'errno': error,
                'error': os.strerror(error) if error else None}
    finally:
        drm.drmModeAtomicFree(request)


def collect():
    if platform.system() != 'Linux':
        raise RuntimeError('run this streamed diagnostic in the Linux USB lab')
    connectors = list(Path('/sys/class/drm').glob('card*-eDP-*'))
    if len(connectors) != 1:
        raise ValueError('expected exactly one internal eDP connector')
    path = connectors[0]
    if (path / 'status').read_text().strip() != 'connected':
        raise ValueError('internal display is not connected')
    edid_hash = hashlib.sha256((path / 'edid').read_bytes()).hexdigest()
    if edid_hash != R04_EDID_SHA256:
        raise ValueError('refusing test: EDID differs from public r04')
    connector_id = int((path / 'connector_id').read_text())
    drm = load_atomic_libdrm()
    fd = os.open('/dev/dri/' + path.name.split('-')[0], os.O_RDWR | os.O_CLOEXEC)
    try:
        if drm.drmIsMaster(fd) != 1:
            raise ValueError('DRM master unavailable; no takeover attempted')
        if drm.drmSetClientCap(fd, ATOMIC_CLIENT_CAP, 1):
            raise OSError(C.get_errno(), 'atomic client capability unavailable')
        connection = properties(drm, fd, connector_id, CONNECTOR, ('CRTC_ID', 'vrr_capable'))
        crtc_id = connection['CRTC_ID']['value']
        if not crtc_id or connection['vrr_capable']['value'] != 0:
            raise ValueError('requires an active connector with advertised VRR capability zero')
        names = ('ACTIVE', 'MODE_ID', 'VRR_ENABLED')
        before = properties(drm, fd, crtc_id, CRTC, names)
        prop = before['VRR_ENABLED']
        if before['ACTIVE']['value'] != 1 or prop['value'] != 0 or prop['values'] != [0, 1]:
            raise ValueError('requires active fixed-refresh CRTC and boolean VRR property')
        mode = mode_bytes(drm, fd, before['MODE_ID']['value'])
        require_native_mode(mode)
        cases = []
        for value in (0, 1, 2):
            case = request_test_only(drm, fd, crtc_id, prop['id'], value)
            after = properties(drm, fd, crtc_id, CRTC, names)
            unchanged = (after == before and
                         mode_bytes(drm, fd, after['MODE_ID']['value']) == mode and
                         properties(drm, fd, connector_id, CONNECTOR,
                                    ('CRTC_ID', 'vrr_capable')) == connection)
            case['live_state_unchanged'] = unchanged
            cases.append(case)
            if not unchanged:
                raise RuntimeError('live state changed during test; stopping without further requests')
        return {'schema': 1, 'kernel': platform.release(), 'edid_sha256': edid_hash,
                'method': 'DRM atomic TEST_ONLY; no ALLOW_MODESET, event or real commit',
                'flags_hex': hex(TEST_ONLY), 'vrr_capable': 0, 'live_vrr_enabled': 0,
                'native_mode_verified': True, 'cases': cases,
                'limit': 'Request validation only; not variable timing or bridge/panel evidence'}
    finally:
        os.close(fd)
