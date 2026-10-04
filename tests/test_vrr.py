"""Capability absence/errors must not be misreported as a measured false bit."""

import ctypes as C
import unittest
from unittest.mock import Mock

from opendecksight.vrr import ObjectProperties, Property, connector_properties


class CapabilityTests(unittest.TestCase):
    def fixture(self, name=b"vrr_capable", value=0):
        ids = (C.c_uint32 * 1)(17)
        values = (C.c_uint64 * 1)(value)
        props = ObjectProperties(1, ids, values)
        prop = Property(prop_id=17, name=name)
        drm = Mock()
        drm.drmModeObjectGetProperties.return_value = C.pointer(props)
        drm.drmModeGetProperty.return_value = C.pointer(prop)
        return drm

    def test_false_capability_is_present_and_resources_are_freed(self):
        drm = self.fixture()
        self.assertEqual(connector_properties(drm, 10, 20), {"vrr_capable": 0})
        drm.drmModeFreeProperty.assert_called_once()
        drm.drmModeFreeObjectProperties.assert_called_once()

    def test_true_capability(self):
        self.assertEqual(connector_properties(self.fixture(value=1), 10, 20),
                         {"vrr_capable": 1})

    def test_absence_is_not_false_and_other_settings_are_omitted(self):
        self.assertEqual(connector_properties(self.fixture(name=b"DPMS"), 10, 20), {})

    def test_failed_metadata_read_is_an_error_and_frees_list(self):
        drm = self.fixture()
        drm.drmModeGetProperty.return_value = C.POINTER(Property)()
        with self.assertRaises(OSError):
            connector_properties(drm, 10, 20)
        drm.drmModeFreeObjectProperties.assert_called_once()
        drm.drmModeFreeProperty.assert_not_called()

    def test_failed_list_read_is_an_error(self):
        drm = self.fixture()
        drm.drmModeObjectGetProperties.return_value = C.POINTER(ObjectProperties)()
        with self.assertRaises(OSError):
            connector_properties(drm, 10, 20)


if __name__ == "__main__":
    unittest.main()
