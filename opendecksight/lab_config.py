"""Data-only Wi-Fi configuration for the disposable USB lab environment."""

import json
from pathlib import Path
import re


def parse_config(data):
    if len(data) > 65536:
        raise ValueError("Wi-Fi configuration is too large")
    try:
        config = json.loads(data)
    except (ValueError, UnicodeError):
        raise ValueError("Wi-Fi configuration is not valid JSON") from None
    if not isinstance(config, dict) or set(config) != {"wifi"}:
        raise ValueError("Expected a single wifi object")
    wifi = config["wifi"]
    if wifi is None:
        return None
    if not isinstance(wifi, dict) or not {"ssid"} <= wifi.keys():
        raise ValueError("Wi-Fi needs an ssid")
    if wifi.keys() - {"ssid", "password", "security", "hidden"}:
        raise ValueError("Unknown Wi-Fi configuration field")
    ssid = wifi["ssid"]
    password = wifi.get("password", "")
    security = wifi.get("security", "wpa-psk")
    hidden = wifi.get("hidden", False)
    try:
        ssid_bytes = ssid.encode() if isinstance(ssid, str) else b""
        password_bytes = password.encode() if isinstance(password, str) else b""
    except UnicodeError:
        raise ValueError("Wi-Fi text must be valid UTF-8") from None
    if not isinstance(ssid, str) or not 1 <= len(ssid_bytes) <= 32 or "\x00" in ssid:
        raise ValueError("SSID must contain 1 to 32 UTF-8 bytes without NUL")
    if not isinstance(password, str) or "\x00" in password:
        raise ValueError("Invalid Wi-Fi password")
    if type(hidden) is not bool:
        raise ValueError("hidden must be true or false")
    if security not in ("wpa-psk", "sae", "open"):
        raise ValueError("security must be wpa-psk, sae or open")
    if security == "wpa-psk" and not (
        8 <= len(password_bytes) <= 63 or re.fullmatch(r"[0-9a-fA-F]{64}", password)
    ):
        raise ValueError("WPA password must be 8–63 UTF-8 bytes or a 64-digit hex PSK")
    if security == "sae" and not 1 <= len(password_bytes) <= 63:
        raise ValueError("SAE password must be 1–63 UTF-8 bytes")
    if security == "open" and password:
        raise ValueError("An open network must not specify a password")
    return {"ssid": ssid, "password": password, "security": security, "hidden": hidden}


def nmcli_arguments(wifi):
    """Use argv, never a shell or a hand-escaped NetworkManager keyfile."""
    args = ["nmcli", "--offline", "connection", "add", "type", "wifi",
            "con-name", "ods-wifi", "ssid", wifi["ssid"],
            "connection.autoconnect", "yes", "802-11-wireless.hidden",
            "yes" if wifi["hidden"] else "no",
            # Fedora's stable-ssid default changes when this RAM-root boot
            # regenerates machine identity. Keep the lab's network identity
            # tied to the physical adapter so DHCP can reuse its lease.
            "802-11-wireless.cloned-mac-address", "permanent",
            "ipv4.dhcp-client-id", "mac", "ipv4.method", "auto",
            "ipv6.method", "auto"]
    if wifi["security"] != "open":
        args += ["802-11-wireless-security.key-mgmt", wifi["security"],
                 "802-11-wireless-security.psk", wifi["password"]]
    return args


def is_usb_partition(device, sysfs=Path("/sys/class/block")):
    """Require USB ancestry, independently of its filesystem label/UUID."""
    path = sysfs / Path(device).name
    if not path.exists():
        return False
    return re.search(r"/usb[0-9]+/", str(path.resolve())) is not None
