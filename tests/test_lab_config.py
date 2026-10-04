import json
from pathlib import Path
import tempfile
import unittest

from opendecksight.lab_config import is_usb_partition, nmcli_arguments, parse_config


class LabConfigTests(unittest.TestCase):
    def config(self, **values):
        return json.dumps({"wifi": {"ssid": "Lab network", "password": "example-only", **values}})

    def test_unconfigured_image_needs_no_credentials(self):
        self.assertIsNone(parse_config('{"wifi": null}'))

    def test_special_characters_are_literal_arguments(self):
        ssid = '$(id);"\\\nLab'
        password = '`uname`;"\\\npassword'
        wifi = parse_config(self.config(ssid=ssid, password=password))
        args = nmcli_arguments(wifi)
        self.assertEqual(args[args.index("ssid") + 1], ssid)
        self.assertEqual(args[-1], password)
        self.assertEqual(args[:3], ["nmcli", "--offline", "connection"])

    def test_ssid_limit_is_bytes_not_characters(self):
        parse_config(self.config(ssid="é" * 16))
        with self.assertRaises(ValueError):
            parse_config(self.config(ssid="é" * 17))

    def test_psk_and_wpa3_validation(self):
        parse_config(self.config(password="a" * 64))
        parse_config(self.config(password="x", security="sae"))
        for password in ("short", "g" * 64, "é" * 32, "password\x00"):
            with self.subTest(password_length=len(password)), self.assertRaises(ValueError):
                parse_config(self.config(password=password))

    def test_open_network_has_no_psk(self):
        wifi = parse_config(self.config(password="", security="open"))
        self.assertNotIn("802-11-wireless-security.psk", nmcli_arguments(wifi))
        with self.assertRaises(ValueError):
            parse_config(self.config(security="open"))

    def test_invalid_data_does_not_echo_secrets(self):
        secret = "DO_NOT_ECHO_ME"
        for config in ('{"wifi": "' + secret, self.config(password=secret, hidden=secret),
                       self.config(password=secret, run=secret), self.config(ssid="\ud800")):
            with self.subTest(config_type=type(config)), self.assertRaises(ValueError) as error:
                parse_config(config)
            self.assertNotIn(secret, str(error.exception))

    def test_oversized_or_wrong_topology_rejected(self):
        for data in (' ' * 65537, '[]', '{}', '{"wifi":null,"command":"sh"}'):
            with self.assertRaises(ValueError):
                parse_config(data)

    def test_usb_ancestry_required_not_just_a_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'block').mkdir()
            for name, target in [('sda1', 'devices/usb1/1-2/block/sda/sda1'),
                                 ('nvme0n1p1', 'devices/pci/nvme/nvme0n1p1')]:
                (root / target).mkdir(parents=True)
                (root / 'block' / name).symlink_to(root / target)
            self.assertTrue(is_usb_partition('/dev/sda1', root / 'block'))
            self.assertFalse(is_usb_partition('/dev/nvme0n1p1', root / 'block'))
            self.assertFalse(is_usb_partition('/dev/missing', root / 'block'))
