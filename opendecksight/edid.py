"""Small bounded EDID/CTA decoder for the observed DeckSight artifacts."""

HEADER = bytes.fromhex("00ffffffffffff00")


def encode_detailed_timing(*, width, height, clock_hz, h_front, h_sync, h_back,
                           v_front, v_sync, v_back, width_mm, height_mm):
    """Encode a progressive DTD with separate positive H/V synchronization."""
    hblank, vblank = h_front + h_sync + h_back, v_front + v_sync + v_back
    if (clock_hz % 10000 or not 0 < clock_hz // 10000 <= 65535
            or any(not 0 <= v <= 4095 for v in (width, height, hblank, vblank, width_mm, height_mm))
            or any(not 0 <= v <= 1023 for v in (h_front, h_sync))
            or any(not 0 <= v <= 63 for v in (v_front, v_sync))
            or min(width, height) == 0 or min(h_back, v_back) < 0):
        raise ValueError("timing cannot be represented in an EDID DTD")
    d = bytearray(18)
    d[:2] = (clock_hz // 10000).to_bytes(2, "little")
    d[2:5] = bytes((width & 255, hblank & 255, (width >> 8) << 4 | hblank >> 8))
    d[5:8] = bytes((height & 255, vblank & 255, (height >> 8) << 4 | vblank >> 8))
    d[8:12] = bytes((h_front & 255, h_sync & 255, (v_front & 15) << 4 | (v_sync & 15),
                     (h_front >> 8) << 6 | (h_sync >> 8) << 4 | (v_front >> 4) << 2 | v_sync >> 4))
    d[12:15] = bytes((width_mm & 255, height_mm & 255, (width_mm >> 8) << 4 | height_mm >> 8))
    d[17] = 0x1E
    return bytes(d)


def detailed_timing(d):
    if len(d) != 18:
        raise ValueError("DTD must contain 18 bytes")
    clock = int.from_bytes(d[:2], "little") * 10000
    if not clock:
        return None
    hactive = d[2] | (d[4] >> 4) << 8
    hblank = d[3] | (d[4] & 15) << 8
    vactive = d[5] | (d[7] >> 4) << 8
    vblank = d[6] | (d[7] & 15) << 8
    hfront = d[8] | (d[11] >> 6) << 8
    hsync = d[9] | ((d[11] >> 4) & 3) << 8
    vfront = (d[10] >> 4) | ((d[11] >> 2) & 3) << 4
    vsync = (d[10] & 15) | (d[11] & 3) << 4
    total = (hactive + hblank) * (vactive + vblank)
    return {"width": hactive, "height": vactive, "pixel_clock_hz": clock,
            "refresh_hz": clock / total if total else None,
            "h_front": hfront, "h_sync": hsync, "h_back": hblank - hfront - hsync,
            "v_front": vfront, "v_sync": vsync, "v_back": vblank - vfront - vsync}


def decode(data):
    if len(data) < 128 or len(data) % 128 or data[:8] != HEADER:
        raise ValueError("invalid EDID header or block length")
    expected = 128 * (1 + data[126])
    if len(data) != expected:
        raise ValueError(f"EDID declares {expected} bytes, received {len(data)}")
    if any(sum(data[i:i + 128]) & 255 for i in range(0, len(data), 128)):
        raise ValueError("invalid EDID block checksum")
    vendor = int.from_bytes(data[8:10], "big")
    result = {"vendor": "".join(chr(64 + ((vendor >> s) & 31)) for s in (10, 5, 0)),
              "product": int.from_bytes(data[10:12], "little"),
              "version": f"{data[18]}.{data[19]}", "extensions": data[126],
              "timings": [], "name": None, "cta_blocks": []}
    for i in range(54, 126, 18):
        d = data[i:i + 18]
        timing = detailed_timing(d)
        if timing:
            result["timings"].append(timing)
        elif d[:5] == b"\0\0\0\xfc\0":
            result["name"] = d[5:].decode("ascii", errors="replace").strip()
    for offset in range(128, len(data), 128):
        block = data[offset:offset + 128]
        if block[0] != 2:
            continue
        end = block[2]
        if end == 0:
            continue
        if not 4 <= end <= 127:
            raise ValueError("invalid CTA data-block boundary")
        pos = 4
        while pos < end:
            tag, size = block[pos] >> 5, block[pos] & 31
            if pos + 1 + size > end:
                raise ValueError("CTA data block exceeds declared boundary")
            payload = block[pos + 1:pos + 1 + size]
            entry = {"tag": tag, "payload_hex": payload.hex()}
            if tag == 7 and payload and payload[0] == 6:
                if len(payload) < 3:
                    raise ValueError("truncated CTA HDR block")
                entry.update({"kind": "HDR static metadata", "eotf_flags": payload[1],
                              "static_metadata_flags": payload[2]})
                if len(payload) >= 4:
                    entry["desired_max_luminance"] = 50 * 2 ** (payload[3] / 32)
            result["cta_blocks"].append(entry)
            pos += 1 + size
        for pos in range(end, 110, 18):
            timing = detailed_timing(block[pos:pos + 18])
            if timing:
                result["timings"].append(timing)
    return result


def scan(data):
    pos = 0
    found = []
    while (pos := data.find(HEADER, pos)) != -1:
        if pos + 128 <= len(data):
            size = 128 * (1 + data[pos + 126])
            try:
                found.append({"offset": pos, "size": size, "edid": decode(data[pos:pos + size])})
            except ValueError as error:
                found.append({"offset": pos, "size": size, "error": str(error)})
        pos += 8
    return found
