"""PID 1 for a disposable RAM-root lab; no installed OS is mounted or started."""

import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time

from opendecksight.lab_config import is_usb_partition, nmcli_arguments, parse_config

LOG = Path("/run/ods")
USB_UUID = "0D51-AB01"


def log(message):
    line = "[ODS] " + message + "\n"
    with (LOG / "boot.log").open("a") as stream:
        stream.write(line)
    for console in ("/dev/tty1", "/dev/ttyS0"):
        fd = None
        try:
            fd = os.open(console, os.O_WRONLY | os.O_NOCTTY | os.O_NONBLOCK)
            os.write(fd, line.encode())
        except OSError:
            pass
        finally:
            if fd is not None:
                os.close(fd)


def run(args, timeout=30):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def network_addresses(data):
    # iproute2 may emit an addr_info entry without `local` during transitions.
    return [address['local'] for dev in json.loads(data)
            for address in dev.get('addr_info', []) if address.get('local')]


def import_wifi():
    """Only the expected FAT volume on USB may supply configuration data."""
    mountpoint = Path("/run/ods-boot")
    mountpoint.mkdir(exist_ok=True)
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        result = run(["blkid", "-t", "UUID=" + USB_UUID, "-o", "device"])
        devices = [x for x in result.stdout.splitlines() if is_usb_partition(x)]
        if len(devices) > 1:
            log("Multiple lab USB volumes found; refusing ambiguous Wi-Fi configuration.")
            return
        if devices:
            mounted = run(["mount", "-t", "vfat", "-o", "ro,nosuid,nodev,noexec",
                           devices[0], str(mountpoint)])
            if mounted.returncode:
                log("Could not mount the lab USB read-only; Ethernet remains available.")
                return
            try:
                path = mountpoint / "wifi.json"
                if not path.exists():
                    log("No wifi.json; Ethernet remains available.")
                    return
                with path.open("rb") as stream:
                    wifi = parse_config(stream.read(65537))
                if wifi is None:
                    log("Wi-Fi is not configured; Ethernet remains available.")
                    return
                result = run(nmcli_arguments(wifi))
                if result.returncode:
                    # nmcli diagnostics can include configuration values: do not log them.
                    log("Wi-Fi profile generation failed; check wifi.json.")
                    return
                target = Path("/run/NetworkManager/system-connections/ods-wifi.nmconnection")
                fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w") as stream:
                    stream.write(result.stdout)
                log("Wi-Fi profile imported into RAM.")
            except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
                log("Invalid or unreadable wifi.json; Ethernet remains available.")
            finally:
                run(["umount", str(mountpoint)])
            return
        time.sleep(1)
    log("No lab USB configuration volume found; Ethernet remains available.")


def main():
    os.umask(0o077)
    for path in [LOG, Path("/run/ssh"), Path("/run/sshd"), Path("/run/dbus"),
                 Path("/run/NetworkManager/system-connections")]:
        path.mkdir(parents=True, exist_ok=True)
    # NetworkManager and D-Bus use dedicated accounts; parent dirs must be traversable.
    for path in ["/run/dbus", "/run/NetworkManager"]:
        os.chmod(path, 0o755)
    socket.sethostname(b"opendecksight-lab")
    log("RAM-root baseline. No display experiment will start automatically.")
    log("SSH permits passwordless root login on this lab network.")
    for args in [
        ["/usr/lib/systemd/systemd-udevd", "--daemon"],
        ["udevadm", "trigger", "--action=add"],
        ["udevadm", "settle", "--timeout=20"],
    ]:
        try:
            result = run(args, timeout=25)
            if result.returncode:
                log(args[0] + " returned an error; see device inventory after boot.")
        except subprocess.SubprocessError:
            log(args[0] + " timed out; continuing to remote access setup.")
    import_wifi()
    machine_id = Path("/etc/machine-id")
    if machine_id.exists() and not machine_id.read_text().strip():
        machine_id.unlink()
    run(["dbus-uuidgen", "--ensure=/etc/machine-id"])
    if machine_id.exists():
        machine_id.chmod(0o644)
    run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "",
         "-f", "/run/ssh/ssh_host_ed25519_key"])
    check = run(["/usr/sbin/sshd", "-t", "-f", "/etc/ssh/sshd_config"])
    if check.returncode:
        log("SSH configuration failed validation; see /run/ods/sshd-check.log.")
        (LOG / "sshd-check.log").write_text(check.stderr)

    services = {
        "dbus": ["dbus-daemon", "--system", "--nofork", "--nopidfile"],
        # D-Bus activates wpa_supplicant on demand via its packaged Exec entry.
        # Starting a second copy here races NetworkManager's activation request.
        "network": ["NetworkManager", "--no-daemon"],
        "ssh": ["/usr/sbin/sshd", "-D", "-e", "-f", "/etc/ssh/sshd_config"],
    }
    processes = {}
    last_start = {}
    log("Starting networking and SSH. Host keys are new for each RAM-only boot.")
    last_ips = None
    signal.signal(signal.SIGTERM, lambda *_: log("PID 1 remains running; use ods-poweroff to shut down."))
    while True:
        for name, args in services.items():
            child = processes.get(name)
            if child is not None and child.poll() is None:
                continue
            if time.monotonic() - last_start.get(name, -10) < 5:
                continue
            if child is not None:
                log(name + " exited; restarting (details in /run/ods/" + name + ".log).")
            with (LOG / (name + ".log")).open("a") as output:
                processes[name] = subprocess.Popen(args, stdout=output, stderr=output)
            last_start[name] = time.monotonic()
        # Reap orphaned children adopted by PID 1 without stealing managed statuses.
        managed = {child.pid for child in processes.values()}
        for entry in Path("/proc").iterdir():
            if entry.name.isdigit() and int(entry.name) not in managed:
                try:
                    os.waitpid(int(entry.name), os.WNOHANG)
                except (ChildProcessError, ProcessLookupError):
                    pass
        try:
            ips = run(["ip", "-j", "address", "show", "scope", "global"]).stdout
            addresses = network_addresses(ips)
            if addresses != last_ips:
                if addresses:
                    log("Network addresses: " + ", ".join(addresses))
                    log("Connect with ssh root@<address> (no password).")
                last_ips = addresses
        except (ValueError, TypeError, KeyError, subprocess.SubprocessError):
            pass
        time.sleep(2)


if __name__ == "__main__":
    main()
