"""Open implementation of the observed r04 brightness protocol.

Preview is the default. Live writes are experimental, Linux/x86-64/Jupiter-only,
and require the CLI's explicit --apply-mmio option. See docs/brightness.md.
"""

from contextlib import contextmanager
import ctypes
import json
import mmap
import os
from pathlib import Path
import platform
import signal
import sys
import time

from .edid import decode

PHYSICAL_BASE = 0xFE700000
MAP_SIZE = 4096
COMMAND = 0xBA4
TARGET = 0xBA5
REGISTER = 0xBA6
DATA = 0xBA7
POLL_SECONDS = 0.2


def brightness_value(raw, maximum):
    if not (isinstance(raw, int) and isinstance(maximum, int)):
        raise ValueError("brightness and maximum must be integers")
    if not 0 <= raw <= 0xFFFFFFFF or not 1 <= maximum <= 0xFFFFFFFF:
        raise ValueError("brightness must be uint32; maximum must be a positive uint32")
    return 0x280 + (min(raw, maximum) * 0x680 + maximum // 2) // maximum


def packets(raw, maximum):
    value = brightness_value(raw, maximum)
    return ((0x70, bytes((0x51, value >> 8, value & 255, 0))),
            (0x6C, bytes((0x39, 3, 0, 0))))


def preview(raw, maximum):
    return {"raw": raw, "maximum": maximum, "panel_value": brightness_value(raw, maximum),
            "physical_base": hex(PHYSICAL_BASE),
            "writes": [{"register": hex(reg), "data_hex": data.hex(" ")}
                       for reg, data in packets(raw, maximum)]}


class Mailbox:
    """Transport-independent protocol; a fake register backend is used in tests."""

    def __init__(self, io, clock=time.monotonic, sleep=time.sleep, timeout=0.2):
        self.io, self.clock, self.sleep, self.timeout = io, clock, sleep, timeout

    def wait_idle(self):
        deadline = self.clock() + self.timeout
        while self.io.read8(COMMAND) & 0x80:
            if self.clock() >= deadline:
                raise TimeoutError("EC mailbox remained busy for 200 ms")
            self.sleep(0.001)

    def write_register(self, register, data):
        if register not in (0x70, 0x6C) or len(data) != 4:
            raise ValueError("brightness transport expects a four-byte payload or header")
        self.wait_idle()
        self.io.write8(TARGET, 0xC0)
        self.io.write8(REGISTER, register)
        self.io.write32(DATA, int.from_bytes(data, "little"))
        self.io.write8(COMMAND, 0x84)
        self.wait_idle()

    def set_brightness(self, raw, maximum):
        for register, data in packets(raw, maximum):
            self.write_register(register, data)


class MemoryRegisters:
    def __init__(self, mapping):
        self.mapping = mapping

    def read8(self, offset):
        return ctypes.c_uint8.from_buffer(self.mapping, offset).value

    def write8(self, offset, value):
        ctypes.c_uint8.from_buffer(self.mapping, offset).value = value

    def write32(self, offset, value):
        # The original makes an unaligned little-endian 32-bit MMIO store.
        # This backend is deliberately restricted to Linux x86-64.
        ctypes.c_uint32.from_buffer(self.mapping, offset).value = value


def find_backlight():
    matches = sorted(Path("/sys/class/drm").glob("card*-eDP-1/amdgpu_bl*/brightness"))
    if len(matches) != 1:
        raise RuntimeError(f"expected one eDP backlight, found {len(matches)}")
    return matches[0]


def read_brightness(path):
    raw = int(path.read_text().strip())
    maximum = int(path.with_name("max_brightness").read_text().strip())
    brightness_value(raw, maximum)  # Reject invalid data instead of silently guessing.
    return raw, maximum


def validate_device(source):
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise RuntimeError("live MMIO requires Linux x86-64")
    if os.geteuid() != 0:
        raise RuntimeError("live MMIO requires root")
    dmi = Path("/sys/class/dmi/id")
    if (dmi / "board_vendor").read_text().strip() != "Valve":
        raise RuntimeError("not a Valve device")
    if (dmi / "board_name").read_text().strip() != "Jupiter":
        raise RuntimeError("only LCD Steam Deck (Jupiter) is supported")
    if not (dmi / "bios_version").read_text().strip().startswith("F7A"):
        raise RuntimeError("not an F7A BIOS")
    # Use the connector associated with this exact discovered backlight.
    panel = decode((source.parent.parent / "edid").read_bytes())
    if (panel["vendor"], panel["product"]) != ("DSO", 0x5001):
        raise RuntimeError("connected panel does not identify as DeckSight DSO:5001")
    for executable in Path("/proc").glob("[0-9]*/exe"):
        try:
            name = executable.readlink().name.removesuffix(" (deleted)")
        except (FileNotFoundError, ProcessLookupError):
            continue
        if name == "decksight-brightnessctrl":
            raise RuntimeError("the original brightness daemon is running; stop it before live testing")


@contextmanager
def live_mailbox(source):
    validate_device(source)
    import fcntl
    flags = os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW
    lock_fd = os.open("/run/opendecksight-brightness.lock", flags, 0o600)
    try:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("another OpenDeckSight controller holds the mailbox lock") from None
        memory_fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC | os.O_CLOEXEC)
        try:
            with mmap.mmap(memory_fd, MAP_SIZE, flags=mmap.MAP_SHARED,
                           prot=mmap.PROT_READ | mmap.PROT_WRITE, offset=PHYSICAL_BASE) as mapping:
                yield Mailbox(MemoryRegisters(mapping))
        finally:
            os.close(memory_fd)
    finally:
        os.close(lock_fd)


class Controller:
    def __init__(self, transport):
        self.transport = transport
        self.previous = None
        self.last_tick = None

    def tick(self, raw, maximum, now):
        resume_gap = self.last_tick is not None and now - self.last_tick > 0.4
        self.last_tick = now
        request = (raw, maximum)
        if request == self.previous and not resume_gap:
            return False
        # If a forced refresh fails, the next iteration must still retry it.
        self.previous = None
        self.transport.set_brightness(raw, maximum)
        self.previous = request
        return True


def boot_time():
    clock = getattr(time, "CLOCK_BOOTTIME", time.CLOCK_MONOTONIC)
    return time.clock_gettime(clock)


class PreviewTransport:
    def set_brightness(self, raw, maximum):
        print(json.dumps(preview(raw, maximum)), flush=True)


def run_loop(source, transport):
    controller = Controller(transport)
    last_error = None
    while True:
        try:
            controller.tick(*read_brightness(source), boot_time())
            last_error = None
        except (OSError, ValueError) as error:
            message = str(error)
            if message != last_error:
                print(f"brightness update failed; will retry: {message}", file=sys.stderr, flush=True)
                last_error = message
        time.sleep(POLL_SECONDS)


def run(args):
    if (args.raw is None) != (args.maximum is None):
        raise ValueError("supply --raw and --max together")
    if args.watch and args.raw is not None:
        raise ValueError("--watch reads the OS setting; omit --raw and --max")
    if args.apply_mmio and args.backlight:
        raise ValueError("live mode uses auto-discovered hardware, not --backlight overrides")
    if args.raw is not None and args.backlight:
        raise ValueError("use explicit values or a backlight file, not both")
    source = args.backlight
    if source is None and (args.raw is None or args.apply_mmio):
        source = find_backlight()
    raw, maximum = ((args.raw, args.maximum) if args.raw is not None else read_brightness(source))
    brightness_value(raw, maximum)

    def stop(signum, frame):
        raise KeyboardInterrupt

    previous_signal = signal.signal(signal.SIGTERM, stop)
    try:
        if args.apply_mmio:
            with live_mailbox(source) as transport:
                if args.watch:
                    run_loop(source, transport)
                else:
                    transport.set_brightness(raw, maximum)
                    print(json.dumps({"status": "EC mailbox completed; panel acknowledgement unavailable",
                                      **preview(raw, maximum)}))
        elif args.watch:
            run_loop(source, PreviewTransport())
        else:
            print(json.dumps({"mode": "preview; no device writes", **preview(raw, maximum)}, indent=2))
    except KeyboardInterrupt:
        pass
    finally:
        signal.signal(signal.SIGTERM, previous_signal)
