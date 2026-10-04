import unittest
from unittest.mock import patch
from opendecksight.msa_control import read_control


class MsaControlTests(unittest.TestCase):
    def test_only_fixed_read_address_and_one_byte(self):
        with patch('opendecksight.msa_control.os.pread', return_value=b'\x10') as read:
            self.assertFalse(read_control(5)['ignore_msa_enabled'])
            read.assert_called_once_with(5, 1, 0x107)
        with patch('opendecksight.msa_control.os.pread', return_value=b'\x90'):
            self.assertTrue(read_control(5)['ignore_msa_enabled'])

    def test_short_read_is_not_reported_as_disabled(self):
        with patch('opendecksight.msa_control.os.pread', return_value=b''):
            with self.assertRaises(ValueError): read_control(5)


if __name__=='__main__': unittest.main()
