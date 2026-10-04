"""The diagnostic must never send an applying atomic commit, even on failure."""

import ctypes as C
import errno
import unittest
from unittest.mock import Mock

from opendecksight.vrr_dry_run import MODE, request_test_only, require_native_mode


class DryRunTests(unittest.TestCase):
    def drm(self):
        d = Mock()
        d.drmModeAtomicAlloc.return_value = 77
        d.drmModeAtomicAddProperty.return_value = 1
        d.drmModeAtomicCommit.return_value = 0
        return d

    def test_every_request_is_test_only_with_no_additional_flags(self):
        for value in (0, 1, 2):
            d = self.drm()
            self.assertEqual(request_test_only(d, 9, 10, 11, value)['returncode'], 0)
            d.drmModeAtomicCommit.assert_called_once_with(9, 77, 0x0100, None)
            d.drmModeAtomicFree.assert_called_once_with(77)

    def test_rejection_is_recorded_without_retrying_as_real_commit(self):
        d = self.drm()
        def rejected(*args):
            C.set_errno(errno.EINVAL)
            return -1
        d.drmModeAtomicCommit.side_effect = rejected
        result = request_test_only(d, 9, 10, 11, 2)
        self.assertEqual(result['errno'], errno.EINVAL)
        d.drmModeAtomicCommit.assert_called_once_with(9, 77, 0x0100, None)
        d.drmModeAtomicFree.assert_called_once_with(77)

    def test_construction_error_does_not_submit_and_frees_request(self):
        d = self.drm()
        d.drmModeAtomicAddProperty.return_value = -1
        with self.assertRaises(OSError):
            request_test_only(d, 9, 10, 11, 1)
        d.drmModeAtomicCommit.assert_not_called()
        d.drmModeAtomicFree.assert_called_once_with(77)

    def test_allocation_error_does_not_submit(self):
        d = self.drm()
        d.drmModeAtomicAlloc.return_value = None
        with self.assertRaises(OSError):
            request_test_only(d, 9, 10, 11, 1)
        d.drmModeAtomicCommit.assert_not_called()

    def test_arbitrary_values_are_rejected_before_allocation(self):
        for value in (-1, 3, 1 << 64, '1', None, True):
            d = self.drm()
            with self.assertRaises(ValueError):
                request_test_only(d, 9, 10, 11, value)
            d.drmModeAtomicAlloc.assert_not_called()

    def test_native_mode_guard_rejects_each_changed_timing_field(self):
        fields = [143180, 1080, 1112, 1120, 1220, 0, 1920, 1928, 1930,
                  1956, 0, 60, 5, 72, b'1080x1920']
        require_native_mode(MODE.pack(*fields))
        for index in (*range(11), 12):
            changed = fields.copy()
            changed[index] += 1
            with self.subTest(index=index), self.assertRaises(ValueError):
                require_native_mode(MODE.pack(*changed))


if __name__ == '__main__':
    unittest.main()
