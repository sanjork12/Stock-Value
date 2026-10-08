from copy import deepcopy
import unittest
from peer_comparable import calculate_peer_comparable,similarity_scores,weighted_quantile
from test_peer_comparable import FixtureProvider,FIN,NOW
from test_v41_regression import AAPL_FIN
from valuation_engine import valuate


class WeightedComparabilityTests(unittest.TestCase):
    def calc(self,p=None,ticker='NVDA',cls='semiconductor_growth',f=None):
        return calculate_peer_comparable(ticker,f or FIN,cls,provider=p or FixtureProvider(),now=NOW)

    def test_margin_difference_weights_without_automatic_exclusion(self):
        p=FixtureProvider();p.metrics['AMD']['Operating Margin TTM']=-10
        r=self.calc(p)
        self.assertIn('AMD',r.peers_included)
        self.assertLess(r.peer_scores['AMD']['margin_similarity_score'],1)

    def test_growth_difference_weights_without_automatic_exclusion(self):
        p=FixtureProvider();p.metrics['MRVL']['Revenue Growth TTM YoY']=90
        r=self.calc(p)
        self.assertIn('MRVL',r.peers_included)
        self.assertLess(r.peer_scores['MRVL']['growth_similarity_score'],1)

    def test_weights_monotonic_for_each_difference(self):
        for axis in (1,3,5):
            weights=[]
            for delta in (0,10,100,1000):
                inputs=[10,10,20,20,1000,1000]
                inputs[axis]+=delta
                weights.append(similarity_scores(*inputs)['comparability_weight'])
            self.assertEqual(weights,sorted(weights,reverse=True))

    def test_weight_floor_excludes(self):
        p=FixtureProvider();p.metrics['AMD']['Revenue Growth TTM YoY']=10000
        r=self.calc(p)
        self.assertEqual(r.exclusion_reasons['AMD'],'comparability_weight_below_floor')
        self.assertFalse(r.valid)

    def test_effective_count_is_sum_after_outlier(self):
        p=FixtureProvider();p.metrics['AMD']['Operating Margin TTM']=50
        r=self.calc(p)
        self.assertAlmostEqual(r.effective_peer_count,sum(r.peer_scores[t]['comparability_weight'] for t in r.peers_included))
        self.assertEqual(r.raw_peer_count,3)

    def test_low_effective_count_unavailable_despite_three_raw(self):
        p=FixtureProvider()
        for t in ('AVGO','AMD','MRVL'):p.metrics[t]['Revenue Growth TTM YoY']=210
        r=self.calc(p)
        self.assertEqual(r.raw_peer_count,3)
        self.assertAlmostEqual(r.effective_peer_count,1.5)
        self.assertFalse(r.valid);self.assertIsNone(r.mid)

    def test_effective_two_to_two_point_five_low_confidence(self):
        p=FixtureProvider()
        for t in ('AVGO','AMD','MRVL'):p.metrics[t]['Operating Margin TTM']=60
        r=self.calc(p)
        self.assertTrue(r.valid)
        self.assertAlmostEqual(r.effective_peer_count,3/1.4)
        self.assertEqual(r.confidence,'LOW')

    def test_interpolated_weighted_median_and_equal_weight_stability(self):
        self.assertEqual(weighted_quantile([10,20,30],[1,1,1],.5),20)
        self.assertAlmostEqual(weighted_quantile([10,20,30],[1,1,8],.5),23.88888888888889)
        self.assertEqual(weighted_quantile([10,20,30],[1,1,1],.25),15)

    def test_amzn_disabled_without_requests(self):
        p=FixtureProvider();r=self.calc(p,'AMZN','mega_cap_tech')
        self.assertEqual(r.eligibility,'NOT_ELIGIBLE');self.assertFalse(r.applicable)
        self.assertIsNone(r.mid);self.assertEqual(p.calls,[])

    def test_orcl_equal_similarity_keeps_original_result(self):
        r=self.calc(ticker='ORCL',cls='high_growth_software')
        self.assertTrue(r.valid);self.assertEqual(r.mid,100)
        self.assertEqual(r.weighted_median,r.peer_median)
        self.assertEqual(r.effective_peer_count,5)

    def test_weighted_peer_diagnostic_cannot_change_internal_blend(self):
        r=self.calc(ticker='AAPL',cls='mega_cap_tech')
        before=valuate('AAPL',deepcopy(AAPL_FIN))
        after=valuate('AAPL',deepcopy(AAPL_FIN),peer_result=r,peer_mode='diagnostic')
        self.assertEqual(before,after)
        self.assertNotIn('peer_comparable',after.get('weights_used',{}))


if __name__=='__main__':unittest.main()
