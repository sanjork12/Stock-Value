import csv
import io
import unittest
from copy import deepcopy
from unittest.mock import patch
from independent_evidence_governance import independent_evidence_audit
from experimental_family_blend import family_blend_experiment
from scripts.experiment_family_weighting import report_inputs
from model_family_governance import governance_audit
from production_snapshot_admin import csv_payload


class IndependentEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.stocks={s['ticker']:s for s in report_inputs()}

    def audit(self,ticker='MSFT'):
        return independent_evidence_audit(self.stocks[ticker])

    def test_numeric_outlier_observed(self):
        g=self.audit()
        self.assertEqual((g['active_family_count'],g['observed_family_count'],g['independent_family_count']),(1,2,2))
        self.assertEqual(g['observed_effective_independent_model_count'],2.25)
        self.assertEqual(g['effective_independent_model_count'],1.25)

    def test_not_applicable_not_observed(self):
        self.assertEqual(self.audit('ORCL')['observed_family_count'],1)

    def test_same_family_outlier(self):
        s=self.stocks['AMZN'];s['blend']['included'].remove('growth_adjusted_pe')
        s['blend']['models']['growth_adjusted_pe'].update(valid=False,outlier=True,reason='outlier_vs_other_models')
        g=self.audit('AMZN')
        self.assertEqual(g['family_suppression_status'],'SAME_FAMILY_MODEL_SUPPRESSED')
        self.assertEqual(g['suppressed_families'],[])

    def test_msft_suppression(self):
        self.assertEqual(self.audit()['family_suppression_status'],'INDEPENDENT_FAMILY_SUPPRESSED')

    def test_msft_materiality(self):
        g=self.audit()
        self.assertEqual(g['suppression_materiality'],'HIGH')
        self.assertAlmostEqual(g['production_vs_conflict_preserving_difference_pct'],(657.05/496.2376265822785-1)*100)
        self.assertEqual(g['production_fair_dependency'],'SUPPRESSED_CROSS_FAMILY_CONFLICT')
        self.assertEqual(g['structural_valuation_readiness'],'CROSS_FAMILY_CONFLICT_SUPPRESSED')

    def test_goog_two_active_conflict_retained(self):
        g=self.audit('GOOG')
        self.assertEqual(g['family_suppression_status'],'NONE')
        self.assertEqual(g['active_family_count'],2)
        self.assertEqual(g['production_fair_dependency'],'DIVERSIFIED')
        self.assertEqual(g['structural_valuation_readiness'],'ACCEPTABLE_WITH_CONFLICT')
        self.assertFalse(g['cross_family_conflict_preservation_required'])

    def test_orcl_invalid_not_suppressed(self):
        self.assertEqual(self.audit('ORCL')['family_suppression_status'],'NONE')

    def test_nvda_invalid_not_suppressed(self):
        self.assertEqual(self.audit('NVDA')['family_suppression_status'],'NONE')

    def test_amzn_capex_not_suppressed(self):
        g=self.audit('AMZN')
        self.assertEqual(g['family_suppression_status'],'NONE')
        self.assertIn('CAPEX_DISTORTION_REMOVES_INDEPENDENT_CASH_FLOW_CONFIRMATION',g['structural_gaps'])
        self.assertEqual(g['numeric_stability'],'NUMERICALLY_STABLE_BUT_CONCENTRATED')

    def test_correlated_dominance(self):
        for ticker in ('MSFT','ORCL','NVDA','AMZN'):
            self.assertTrue(self.audit(ticker)['correlated_family_dominance'])
        self.assertFalse(self.audit('GOOG')['correlated_family_dominance'])

    def test_all_production_fields_unchanged(self):
        for s in self.stocks.values():
            s.update(reliability_score=50,confidence='LOW',buy_zones=[1,2],exit_zones=[3,4],peer_comparable_result={'mid':999})
        before=deepcopy(self.stocks)
        for ticker in self.stocks:self.audit(ticker)
        self.assertEqual(before,self.stocks)

    def test_strategy_c_stays_experimental(self):
        s=self.stocks['MSFT'];s['experimental_family_blend']=family_blend_experiment(s)
        before=deepcopy(s)
        self.assertTrue(self.audit()['strategy_c_as_sensitivity_probe'])
        self.assertEqual(before,s)
        self.assertNotEqual(s['blend']['fair'],s['experimental_family_blend']['strategy_c_evidence_adjusted']['fair'])

    def test_benchmark_not_used(self):
        before=self.audit()
        self.stocks['MSFT']['benchmark']=1e99
        self.assertEqual(before,self.audit())

    def test_no_io(self):
        with patch('builtins.open',side_effect=AssertionError('unexpected IO')):
            self.audit()

    def test_null_signal_excluded(self):
        s=self.stocks['MSFT']
        for collection in (s['blend']['models'],s['models_before_outlier']):collection['normalized_fcf_dcf']['mid']=None
        self.assertEqual(self.audit()['observed_family_count'],1)
        self.assertEqual(self.audit()['family_suppression_status'],'NONE')

    def test_execution_failure_excluded(self):
        s=self.stocks['MSFT'];s['models_before_outlier']['normalized_fcf_dcf']['executed']=False
        self.assertEqual(self.audit()['observed_family_count'],1)

    def test_capital_gap_actual_evidence(self):
        self.assertEqual(self.audit('ORCL')['structural_gaps'],[])
        self.stocks['ORCL']['normalized_inputs']={'cash':1,'debt':5,'market_cap':10}
        g=self.audit('ORCL')
        self.assertIn('CAPITAL_STRUCTURE_WITHOUT_INDEPENDENT_VALUATION_FAMILY',g['structural_gaps'])
        self.assertEqual(g['structural_valuation_readiness'],'CONCENTRATED_WITH_STRUCTURAL_GAP')

    def test_forecast_gap_actual_evidence(self):
        s=self.stocks['NVDA'];s['normalized_inputs']={'forward_eps':10,'trailing_eps':2}
        for name in ('forward_pe','growth_adjusted_pe'):s['blend']['models'][name]['inputs']={'forward_eps':10}
        self.assertIn('FORECAST_GROWTH_WITHOUT_INDEPENDENT_CASH_FLOW_CONFIRMATION',self.audit('NVDA')['structural_gaps'])

    def test_ticker_independent(self):
        before=self.audit();self.stocks['MSFT']['ticker']='UNKNOWN'
        self.assertEqual(before,self.audit())

    def test_missing_probe_no_fabricated_materiality(self):
        self.stocks['MSFT']['profile_assumptions']={}
        self.assertEqual(self.audit()['suppression_materiality'],'UNAVAILABLE')

    def test_cached_and_degraded_refused(self):
        self.stocks['MSFT']['source_status']='cached_last_reliable'
        self.assertEqual(self.audit()['status'],'INELIGIBLE_INPUT_STATE')
        self.stocks['MSFT'].update(source_status='live',calibration_eligibility='INELIGIBLE')
        self.assertEqual(self.audit()['status'],'INELIGIBLE_INPUT_STATE')

    def test_zero_evidence_no_positive_classification(self):
        s={'ticker':'EMPTY','blend':{'models':{},'included':[]}}
        g=independent_evidence_audit(s)
        self.assertEqual(g['independent_evidence_status'],'INSUFFICIENT')
        self.assertIsNone(g['structural_valuation_readiness'])

    def test_csv_namespace(self):
        s=self.stocks['MSFT'];s['independent_evidence_governance']=self.audit()
        s['models']=[{'model_name':'forward_pe'}]
        row=next(csv.DictReader(io.StringIO(csv_payload({'stocks':[s]}).decode('utf-8-sig'))))
        self.assertEqual(row['independent_evidence_governance.family_suppression_status'],'INDEPENDENT_FAMILY_SUPPRESSED')

    def test_materiality_boundaries(self):
        s=self.stocks['MSFT']
        for delta,expected in ((-10,'LOW'),(10.01,'MODERATE'),(25,'MODERATE'),(-25.01,'HIGH')):
            s['experimental_family_blend']={'production_fair':100+delta,'strategy_c_evidence_adjusted':{'fair':100}}
            self.assertEqual(self.audit()['suppression_materiality'],expected)

    def test_multiple_families_suppressed(self):
        s=self.stocks['MSFT']
        m={'mid':100,'valid':True,'executed':True,'applicable':True}
        s['models_before_outlier']['ev_ebitda']=deepcopy(m)
        s['blend']['models']['ev_ebitda']={**m,'valid':False,'outlier':True,'reason':'outlier_vs_other_models'}
        s['profile_assumptions']['weights']['ev_ebitda']=.1
        self.assertEqual(self.audit()['family_suppression_status'],'MULTIPLE_FAMILIES_SUPPRESSED')
