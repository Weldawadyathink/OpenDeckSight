import unittest

from tests.test_optical_ab import fixture
from tools.analyze_optical_feedback_prefix import compare_prefix


def incomplete_fixture():
    flips,observed=fixture()
    flips=flips[:1040]
    for i,f in enumerate(flips):
        paced=f['phase']==1
        f['target_total']=(1980 if ((f['frame']-1)//60)%2 else 1964) if paced else 1956
        f['deadline_ns']=(flips[i-1]['event_ns']+f['target_total']*1220*1000000000//143180000-350000
                          if paced and f['frame']>1 else 0)
        f['submitted_ns']=f['deadline_ns']+200 if f['deadline_ns'] else f['event_ns']-100000
    return flips,observed[:682]


class FeedbackPrefixTests(unittest.TestCase):
    def test_exact_prefix_stays_failed_and_partial_block_is_visible(self):
        flips,observed=incomplete_fixture()
        r=compare_prefix(flips,observed)
        self.assertEqual(r['completion_status'],'aborted')
        self.assertFalse(r['progression_passed'])
        self.assertFalse(r['final_fixed_phase_available'])
        self.assertEqual(r['matched_prefix_edges'],682)
        self.assertEqual(r['completed_B_flips'],320)
        self.assertEqual(r['feedback_blocks'][-1]['completed_frames'],20)
        self.assertFalse(r['feedback_blocks'][-1]['complete'])
        self.assertLess(max(abs(p['source_residual_us']) for p in r['pairs']),.01)

    def test_no_extra_missing_or_reordered_edges_can_be_trimmed(self):
        flips,observed=incomplete_fixture()
        for changed in (observed[:-1],observed+[dict(observed[-1],time_us=99999999)],observed[::-1]):
            with self.assertRaises(ValueError):compare_prefix(flips,changed)
        flips[800]['ordinal']+=1
        with self.assertRaises(ValueError):compare_prefix(flips,observed)

    def test_aborted_B_cannot_change_clock_fit_or_hide_delay(self):
        flips,observed=incomplete_fixture()
        baseline=compare_prefix(flips,observed)
        observed[500]['time_us']+=300
        changed=compare_prefix(flips,observed)
        self.assertEqual(changed['model'],baseline['model'])
        self.assertAlmostEqual(changed['pairs'][500]['source_residual_us'],300,places=2)


if __name__=='__main__':unittest.main()
