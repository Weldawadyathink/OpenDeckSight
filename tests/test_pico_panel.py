import unittest
from tools.analyze_pico_panel import edges, intervals


class OpticalPanelTimingTests(unittest.TestCase):
    def test_asymmetric_duty_does_not_change_same_edge_period(self):
        # 10 ms period with 4 ms bright / 6 ms dark. Comparing opposite
        # edge types must not turn duty asymmetry into period variation.
        wave=([30]*600+[650]*400)*5
        found=edges(wave,100_000)
        adjacent,repeated=intervals(found)
        self.assertEqual(len(found),9)
        self.assertTrue(all(abs(v['us']-10_000)<1e-6 for v in repeated))
        self.assertTrue(all(min(abs(v['us']-t) for t in (4000,6000))<10 for v in adjacent))

    def test_bright_modulation_inside_hysteresis_is_not_new_content(self):
        wave=[650]*100+[300]*100+[650]*100+[350]*100+[650]*100
        self.assertEqual(edges(wave,100_000),[])

    def test_different_bursts_have_no_invented_interval(self):
        first=edges([30]*100+[650]*100,100_000)
        second=edges([650]*100+[30]*100,100_000)
        self.assertEqual(intervals(first),([],[]))
        self.assertEqual(intervals(second),([],[]))

    def test_initial_brightness_is_not_an_edge(self):
        self.assertEqual(edges([650]*200,100_000),[])
        self.assertEqual(edges([30]*200,100_000),[])

    def test_midpoint_interpolation_on_a_ramp(self):
        wave=[0]*100+list(range(0,1001,100))+[1000]*100
        found=edges(wave,100_000,middle_v=500*3.3/4095,high_v=.7)
        self.assertEqual(len(found),1)
        self.assertAlmostEqual(found[0]['time_us'],1050)

    def test_bad_thresholds(self):
        with self.assertRaises(ValueError):
            edges([0]*200,100_000,low_v=.3,middle_v=.2,high_v=.4)


if __name__=='__main__':
    unittest.main()
