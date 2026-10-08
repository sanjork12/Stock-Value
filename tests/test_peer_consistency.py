from copy import deepcopy
import unittest
from peer_consistency import cross_multiple_consistency
from scripts.report_peer_comparable import build_report
from test_peer_review_report import PublicFixture,FIN
from test_v41_regression import AAPL_FIN
from peer_comparable import PeerComparableResult
from valuation_engine import valuate


def peer(mids,**changes):
    result={'eligibility':'ELIGIBLE','valid':bool(mids),'confidence':'MEDIUM','effective_peer_count':3,
        'mid':mids[0] if mids else None,'selected_multiple':'M0',
        'post_data_audit':{'attempts':[{'Multiple':f'M{i}','Status':'VALID','peer_low':v*.8,'peer_mid':v,
            'peer_high':v*1.2,'confidence':'MEDIUM','raw_peer_count':4,'effective_peer_count':3,
            'weighted_dispersion':.2} for i,v in enumerate(mids)]}}
    result.update(changes)
    return result


class ConsistencyTests(unittest.TestCase):
    def test_single(self):
        result=cross_multiple_consistency(peer([100]))
        self.assertEqual(result['consistency_status'],'SINGLE_METHOD_ONLY')
        self.assertEqual(result['peer_production_eligibility'],'DIAGNOSTIC_ONLY')

    def test_close(self):
        result=cross_multiple_consistency(peer([100,110]))
        self.assertEqual(result['consistency_status'],'CONSISTENT')
        self.assertEqual(result['peer_production_eligibility'],'REVIEW_ELIGIBLE')

    def test_moderate(self):
        self.assertEqual(cross_multiple_consistency(peer([85,115]))['consistency_status'],'MODERATE_DISAGREEMENT')

    def test_large(self):
        self.assertEqual(cross_multiple_consistency(peer([70,130]))['consistency_status'],'MULTIPLE_DISAGREEMENT')

    def test_zero(self):
        result=cross_multiple_consistency(peer([]))
        self.assertEqual(result['consistency_status'],'UNAVAILABLE')
        self.assertIsNone(result['cross_multiple_spread_pct'])

    def test_ineligible_short_circuits_even_with_stale_methods(self):
        result=cross_multiple_consistency(peer([100,110],eligibility='NOT_ELIGIBLE'))
        self.assertEqual(result['consistency_status'],'NOT_APPLICABLE')
        self.assertEqual(result['multiple_results'],[])

    def test_primary_not_mutated(self):
        source=peer([100,110]);before=deepcopy(source)
        cross_multiple_consistency(source)
        self.assertEqual(source,before)

    def test_observed_cloud_orcl_and_msft(self):
        for mids in ([225.76,198.13,92.29],[406.43,257.01]):
            result=cross_multiple_consistency(peer(mids))
            self.assertEqual(result['consistency_status'],'MULTIPLE_DISAGREEMENT')
            self.assertEqual(result['peer_production_eligibility'],'DIAGNOSTIC_ONLY')
        orcl=cross_multiple_consistency(peer([225.76,198.13,92.29]))
        self.assertAlmostEqual(orcl['cross_multiple_spread_pct'],(225.76-92.29)/198.13*100)
        msft=cross_multiple_consistency(peer([406.43,257.01]))
        self.assertAlmostEqual(msft['max_pairwise_difference_pct'],149.42/331.72*100)

    def test_exact_thresholds(self):
        self.assertEqual(cross_multiple_consistency(peer([90,110]))['consistency_status'],'CONSISTENT')
        self.assertEqual(cross_multiple_consistency(peer([80,120]))['consistency_status'],'MODERATE_DISAGREEMENT')

    def test_low_primary_or_effective_count_blocks_review(self):
        for change in ({'confidence':'LOW'},{'effective_peer_count':2.49}):
            result=cross_multiple_consistency(peer([100,110],**change))
            self.assertEqual(result['peer_production_eligibility'],'DIAGNOSTIC_ONLY')

    def test_invalid_attempts_and_duplicates_not_counted(self):
        source=peer([100,110]);attempts=source['post_data_audit']['attempts']
        attempts[1]['Status']='TARGET_INPUT_UNSAFE'
        attempts.append(deepcopy(attempts[0]))
        self.assertEqual(cross_multiple_consistency(source)['valid_multiple_count'],1)

    def test_review_state_never_enters_internal_blend(self):
        model=PeerComparableResult('AAPL','mega_cap_tech',valid=True,low=1,mid=2,high=3)
        governance=cross_multiple_consistency(peer([100,110]))
        self.assertEqual(governance['peer_production_eligibility'],'REVIEW_ELIGIBLE')
        before=valuate('AAPL',deepcopy(AAPL_FIN))
        self.assertEqual(before,valuate('AAPL',deepcopy(AAPL_FIN),peer_result=model,peer_mode='diagnostic'))

    def test_benchmark_independent_report_and_all_methods_exported(self):
        a=build_report(provider=PublicFixture(),financial_loader=lambda _:deepcopy(FIN))
        b=build_report(provider=PublicFixture(),financial_loader=lambda _:deepcopy(FIN),
            references={'ORCL':{'external_benchmark':999999}})
        for x,y in zip(a['peer_results'],b['peer_results']):
            for key in ('consistency_status','cross_multiple_spread_pct','peer_production_eligibility','multiple_results'):
                self.assertEqual(x[key],y[key])
        orcl=next(d for d in a['peer_results'] if d['target_ticker']=='ORCL')
        self.assertEqual(orcl['multiple_results'][0]['multiple'],orcl['primary_peer_multiple'])
        self.assertIn('weighted_dispersion',orcl['multiple_results'][0])


if __name__=='__main__':unittest.main()
