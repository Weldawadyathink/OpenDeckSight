#!/usr/bin/env python3
"""Write wifi.json on an already-created lab USB; never format a device."""

import argparse
import getpass
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from opendecksight.lab_config import parse_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="mounted ODSBOOT directory")
    parser.add_argument("--security", choices=("wpa-psk", "sae", "open"), default="wpa-psk")
    parser.add_argument("--hidden", action="store_true")
    args = parser.parse_args()
    if not (args.directory / "ODS-LAB.txt").is_file():
        parser.error("This directory does not contain the lab USB marker ODS-LAB.txt")
    ssid = input("Wi-Fi network name: ")
    password = "" if args.security == "open" else getpass.getpass("Wi-Fi password: ")
    config = {"wifi": {"ssid": ssid, "password": password,
                       "security": args.security, "hidden": args.hidden}}
    encoded = json.dumps(config, indent=2) + "\n"
    try:
        parse_config(encoded)
    except ValueError as error:
        parser.error(str(error))
    target = args.directory / "wifi.json"
    # FAT does not enforce Unix permissions; this file intentionally stays editable.
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(encoded)
    print("Saved wifi.json. Credentials were not added to the image or repository.")


if __name__ == "__main__":
    main()
