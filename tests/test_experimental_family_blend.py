import unittest
from copy import deepcopy
from unittest.mock import patch
from experimental_family_blend import family_blend_experiment, evidence_strength, sensitivity_band
from scripts.experiment_family_weighting import report_inputs, build_report
from model_family_governance import governance_audit


class FamilyBlendTests(unittest.TestCase):
    def setUp(self):
        self.stocks={s['ticker']:s for s in report_inputs()}

    def exp(self,ticker='GOOG'):
        return family_blend_experiment(self.stocks[ticker])

    def test_pe_aggregation(self):
        r=self.exp()['family_representatives']['EARNINGS_MULTIPLE']
        self.assertEqual(r['raw_model_count'],2)
        self.assertAlmostEqual(r['family_mid'],(348.83*.35+303.33*.25)/.6)

    def test_invalid_not_restored(self):
        s=self.stocks['GOOG'];s['models_before_outlier']['normalized_fcf_dcf']['valid']=False
        s['blend']['models']['normalized_fcf_dcf'].update(valid=False,reason='invalid_input')
        self.assertNotIn('CASH_FLOW_INTRINSIC',family_blend_experiment(s)['family_representatives'])

    def test_non_numeric_excluded(self):
        s=self.stocks['GOOG'];s['models_before_outlier']['normalized_fcf_dcf']['mid']=None
        s['blend']['models']['normalized_fcf_dcf']['mid']=None
        self.assertEqual(family_blend_experiment(s)['family_count'],1)

    def test_a_base_weights(self):
        w=self.exp()['strategy_a_current_weight_aggregated']['family_weights']
        self.assertAlmostEqual(w['EARNINGS_MULTIPLE'],.6)
        self.assertAlmostEqual(w['CASH_FLOW_INTRINSIC'],.4)

    def test_b_equal(self):
        self.assertEqual(set(self.exp()['strategy_b_equal_family']['family_weights'].values()),{.5})

    def test_c_explicit_strength(self):
        w=self.exp()['strategy_c_evidence_adjusted']['family_weights']
        self.assertAlmostEqual(w['EARNINGS_MULTIPLE'],.51/(.51+.28))

    def test_correlation_not_mid(self):
        r=self.exp()['family_representatives']['EARNINGS_MULTIPLE']
        self.assertEqual(r['family_mid'],r['correlation_adjusted_family_mid'])
        self.assertEqual(r['effective_model_count'],1.25)
        self.assertEqual(r['dependency_penalty'],.375)
        self.assertEqual(r['evidence_strength'],.85)

    def test_conflict_preserves_minority(self):
        e=self.exp('MSFT')
        self.assertTrue(e['family_conflict_flag'])
        for key in ('strategy_a_current_weight_aggregated','strategy_b_equal_family','strategy_c_evidence_adjusted'):
            self.assertGreater(e[key]['family_weights']['CASH_FLOW_INTRINSIC'],0)

    def test_msft_restored(self):
        e=self.exp('MSFT')
        self.assertTrue(e['experimental_restored'])
        self.assertEqual(e['suppressed_family'],['CASH_FLOW_INTRINSIC'])
        self.assertEqual(e['family_representatives']['CASH_FLOW_INTRINSIC']['family_mid'],203.34)

    def test_production_fair_weights_outlier_unchanged(self):
        before=deepcopy(self.stocks)
        for ticker in self.stocks:self.exp(ticker)
        self.assertEqual(self.stocks,before)

    def test_single_family_no_diversification(self):
        for ticker in ('ORCL','NVDA','AMZN'):
            e=self.exp(ticker)
            self.assertEqual(e['family_count'],1)
            values=[e[k]['fair'] for k in ('strategy_a_current_weight_aggregated','strategy_b_equal_family','strategy_c_evidence_adjusted')]
            self.assertEqual(values,[values[0]]*3)

    def test_amzn_stable(self):
        self.assertTrue(self.exp('AMZN')['single_family_numeric_stability'])

    def test_growth_risk_cap_only(self):
        s=self.stocks['NVDA'];before=self.exp('NVDA')
        s['correlation_cross_family_governance']=governance_audit(s)
        s['correlation_cross_family_governance']['growth_overlap_risk']='HIGH'
        after=self.exp('NVDA')
        self.assertTrue(after['family_confidence_cap_recommended'])
        self.assertEqual(before['strategy_c_evidence_adjusted'],after['strategy_c_evidence_adjusted'])

    def test_benchmark_independent(self):
        a=build_report(list(self.stocks.values()),{'GOOG':1})
        b=build_report(list(self.stocks.values()),{'GOOG':100000})
        self.assertEqual(a['stocks'],b['stocks'])
        self.assertNotEqual(a['post_hoc_only'],b['post_hoc_only'])

    def test_missing_weights_abort(self):
        self.stocks['GOOG']['profile_assumptions']={}
        self.assertEqual(self.exp()['status'],'INCOMPLETE_CAPTURED_BASE_WEIGHTS')

    def test_cached_refused(self):
        self.stocks['GOOG']['source_status']='cached_last_reliable'
        self.assertEqual(self.exp()['status'],'INELIGIBLE_INPUT_STATE')

    def test_degraded_refused(self):
        self.stocks['GOOG']['calibration_eligibility']='INELIGIBLE'
        self.assertEqual(self.exp()['status'],'INELIGIBLE_INPUT_STATE')

    def test_no_io_or_peer_mutation(self):
        self.stocks['GOOG']['peer_comparable_result']={'mid':999}
        before=deepcopy(self.stocks)
        with patch('builtins.open',side_effect=AssertionError('unexpected IO')):
            self.exp()
        self.assertEqual(before,self.stocks)

    def test_strength_and_sensitivity_boundaries(self):
        self.assertEqual([evidence_strength(x) for x in (1,1.25,1.75)],[.7,.85,1.])
        self.assertEqual(sensitivity_band(-10),'LOW_SENSITIVITY')
        self.assertEqual(sensitivity_band(25),'MODERATE_SENSITIVITY')
        self.assertEqual(sensitivity_band(-25.01),'HIGH_SENSITIVITY')

    def test_five_stock_batch(self):
        report=build_report(list(self.stocks.values()))
        self.assertEqual(len(report['stocks']),5)
        self.assertTrue(all('experimental_family_blend' in s for s in report['stocks']))
