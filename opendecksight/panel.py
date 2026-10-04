"""Decode the EC's ANX command table into DSI/DCS events.

This documents emitted commands; it does not invent the behavior of proprietary
panel opcodes. Registers are interpreted in the first/stock bank's byte order.
"""

from .firmware import EC_BASES, EC_SIZE, PANEL_INIT_OFFSET, bios_image

DCS = {
    0x11: "exit sleep mode",
    0x29: "set display on",
    0x34: "set tear off",
    0x35: "set tear on",
    0x44: "set tear scanline",
    0x51: "set display brightness",
    0x53: "write control display",
}


def decode_table(ec, offset=PANEL_INIT_OFFSET, max_records=256):
    events = []
    fifo = bytearray()
    for index in range(max_records):
        start = offset + 5 * index
        record = ec[start:start + 5]
        if len(record) != 5:
            raise ValueError("truncated panel initialization table")
        register = record[0]
        word = int.from_bytes(record[1:], "big")
        event = {"ec_offset": hex(start), "record_index": index}
        if register == 0xFF:
            if fifo:
                events.append({**event, "kind": "unsubmitted payload", "hex": fifo.hex(" ")})
            events.append({**event, "kind": "end"})
            return events
        if register == 0x70:
            fifo.extend(word.to_bytes(4, "little"))
            continue
        if register == 0xAA:
            events.append({**event, "kind": "delay", "value": word, "unit": "table delay units (ms inferred)"})
            continue
        if register != 0x6C:
            events.append({**event, "kind": "other bridge register", "register": hex(register), "value": hex(word)})
            continue
        header = word.to_bytes(4, "little")
        dtype = header[0] & 0x3F
        event.update({"kind": "DSI packet", "header_hex": header.hex(" "), "data_type": hex(dtype),
                      "virtual_channel": header[0] >> 6})
        if dtype == 0x39:
            length = int.from_bytes(header[1:3], "little")
            if length == 0 or len(fifo) != (length + 3) // 4 * 4:
                raise ValueError(f"payload FIFO size does not match word count at {start:#x}")
            payload = bytes(fifo[:length])
            event["padding_hex"] = fifo[length:].hex(" ")
            fifo.clear()
        elif dtype in (0x05, 0x15):
            payload = header[1:2] if dtype == 0x05 else header[1:3]
        elif dtype == 0x07:
            event.update({"name": "compression mode", "data_hex": header[1:3].hex(" "),
                          "enable_bit": bool(header[1] & 1), "confidence": "standard packet type"})
            events.append(event)
            continue
        else:
            event.update({"name": "unrecognized packet type", "raw_fifo_hex": fifo.hex(" "),
                          "confidence": "unresolved / potentially invalid encoding"})
            fifo.clear()
            events.append(event)
            continue
        command = payload[0]
        event.update({"payload_hex": payload.hex(" "), "command": hex(command),
                      "name": DCS.get(command, "vendor-specific / unresolved command"),
                      "confidence": "standard command name" if command in DCS else "unresolved"})
        if command == 0x51:
            event["note"] = "Six-byte r04 initialization payload; parameters beyond the usual brightness field are unresolved."
        elif command == 0x53 and len(payload) >= 2:
            event["known_control_bits"] = {"brightness_control": bool(payload[1] & 0x20),
                                            "display_dimming": bool(payload[1] & 0x08),
                                            "backlight_control": bool(payload[1] & 0x04)}
            event["remaining_set_bits"] = hex(payload[1] & ~0x2C)
        elif command == 0x44 and len(payload) == 3:
            event["scanline"] = int.from_bytes(payload[1:], "big")
        elif command == 0x35 and len(payload) == 1:
            event["note"] = "No mode parameter supplied; uses short-write-without-parameter. Panel-specific acceptance is unverified."
        events.append(event)
    raise ValueError("panel table has no terminator within the record limit")


def inspect(image, bank=0):
    if bank not in (0, 1):
        raise ValueError("EC bank must be 0 or 1")
    data = bios_image(image)
    base = EC_BASES[bank]
    return {"bank": bank, "base": hex(base), "word_byte_order": "big (stock/first-bank interpretation)",
            "events": decode_table(data[base:base + EC_SIZE])}
