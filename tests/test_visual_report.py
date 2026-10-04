import unittest
from opendecksight.visual_report import NATIVE_NS, summarize


def fixture(variable):
    events=[{'event':'phase','phase':0,'vrr_requested':variable,'frames':32}]
    timestamp=1000000000
    for frame in range(32):
        timestamp+=int((16700000+frame*7000) if variable else NATIVE_NS)
        # Deliberately irregular CPU submissions must not be called variable scanout.
        events.append({'event':'flip','phase':0,'frame':frame+1,
                       'event_ns':timestamp,'sequence':(0xfffffff0+frame)&0xffffffff,
                       'submitted_ns':timestamp-100000-frame*1700,
                       'deadline_ns':timestamp-200000})
    return events+[{'event':'restore','success':True}]


class VisualReportTests(unittest.TestCase):
    def test_irregular_submissions_do_not_masquerade_as_variable_events(self):
        r=summarize(fixture(False))
        self.assertEqual(r['phases']['0']['within_2us_of_native_fraction'],1)
        self.assertEqual(r['phases']['0']['inside_candidate_window_with_2us_tolerance_fraction'],0)
        self.assertTrue(r['restore_verified'])

    def test_variable_event_fixture_and_sequence_wrap(self):
        r=summarize(fixture(True))['phases']['0']
        self.assertEqual(r['within_2us_of_native_fraction'],0)
        self.assertEqual(r['inside_candidate_window_with_2us_tolerance_fraction'],1)
        self.assertTrue(r['complete'])

    def test_bad_event_sequence_is_not_silently_used(self):
        events=fixture(True)
        events[12]['sequence']=events[11]['sequence']
        with self.assertRaises(ValueError): summarize(events)

    def test_missing_restore_and_incomplete_run_are_reported(self):
        r=summarize(fixture(False)[:-3])
        self.assertFalse(r['restore_verified'])
        self.assertFalse(r['phases']['0']['complete'])


if __name__=='__main__': unittest.main()
