import importlib.util
from pathlib import Path
import unittest


spec = importlib.util.spec_from_file_location(
    'ods_init', Path(__file__).resolve().parents[1] / 'lab/usb/ods_init.py')
init = importlib.util.module_from_spec(spec)
spec.loader.exec_module(init)


class LabInitTests(unittest.TestCase):
    def test_network_transitions_do_not_crash_pid_one(self):
        data = '[{"addr_info":[{}, {"local":"10.0.2.15"}, {"local":null}]}, {}]'
        self.assertEqual(init.network_addresses(data), ['10.0.2.15'])
        self.assertEqual(init.network_addresses('[]'), [])
