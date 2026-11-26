import unittest
from opendecksight.optical_alignment import align,marker,qualify_edges,source_edges


def fixture():
    flips=[{'frame':i,'marker_lit':bool(marker(i)),
            'event_ns':500000000000+round(i*1e9/60)} for i in range(1080)]
    expected=source_edges(flips)
    observed=[{'state':e['state'],'time_us':123456+1.000020*e['source_us']+210*e['state']}
              for e in expected]
    return expected,observed


class AlignmentTests(unittest.TestCase):
    def test_known_clock_and_polarity_bias(self):
        expected,observed=fixture()
        result=align(expected,observed)
        self.assertAlmostEqual(result['model']['scale_error_ppm'],20,places=5)
        self.assertAlmostEqual(result['model']['offset_us'],123456,places=5)
        self.assertAlmostEqual(result['model']['rising_relative_to_falling_us'],210,places=5)
        self.assertLess(max(abs(p['residual_us']) for p in result['pairs']),1e-6)

    def test_holdout_deviation_is_not_fit_away(self):
        expected,observed=fixture()
        index=next(i for i,p in enumerate(expected) if p['frame']==800)
        observed[index]['time_us']+=120
        result=align(expected,observed)
        self.assertAlmostEqual(result['model']['scale_error_ppm'],20,places=5)
        self.assertAlmostEqual(result['pairs'][index]['residual_us'],120,places=5)

    def test_missing_extra_and_shifted_edges_rejected(self):
        expected,observed=fixture()
        missing=observed[:200]+observed[202:]
        extra=observed[:200]+[dict(observed[200],time_us=observed[200]['time_us']-1000)]+observed[200:]
        shifted=[dict(p,time_us=p['time_us']+(5000 if i>=400 else 0)) for i,p in enumerate(observed)]
        for case in (missing,extra,shifted):
            with self.subTest(count=len(case)),self.assertRaises(ValueError):align(expected,case)

    def test_outside_edges_preserved(self):
        expected,observed=fixture()
        before={'state':0,'time_us':1}
        after={'state':1,'time_us':observed[-1]['time_us']+10000}
        result=align(expected,[before]+observed+[after])
        self.assertEqual(result['outside_edges'],[before,after])

    def test_settling_records_raw_crossings_and_span(self):
        raw=[{'state':s,'time_us':t} for s,t in [(1,1000),(0,1010),(1,1060),(0,17000)]]
        qualified,groups=qualify_edges(raw)
        self.assertEqual([p['time_us'] for p in qualified],[1060,17000])
        self.assertEqual(qualified[0]['settling_span_us'],60)
        self.assertEqual(groups[0]['crossings'],raw[:3])

    def test_short_pulse_preserved_but_not_counted_as_frame(self):
        raw=[{'state':s,'time_us':t} for s,t in [(1,1000),(0,1050),(1,17000)]]
        qualified,groups=qualify_edges(raw)
        self.assertEqual(len(qualified),1)
        self.assertFalse(groups[0]['net_transition'])
        self.assertEqual(groups[0]['crossings'],raw[:2])


if __name__=='__main__':unittest.main()
