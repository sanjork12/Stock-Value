from copy import deepcopy
import unittest
from unittest.mock import Mock,patch

from model_family_governance import governance_audit,MODEL_FAMILIES,dependency_pair
from scripts.audit_cross_family_governance import observed_baseline,build_report
from scripts.verify_peer_isolation import history
from test_peer_diagnostic_isolation import FINANCIALS
from analysis_service import analyze_ticker
import production_snapshot_admin as admin


def stock():return deepcopy(observed_baseline()[0])


class FamilyGovernanceTests(unittest.TestCase):
    def test_model_family_by_id_not_ticker(self):
        self.assertEqual(MODEL_FAMILIES['forward_pe'],MODEL_FAMILIES['growth_adjusted_pe'])
        self.assertNotEqual(MODEL_FAMILIES['forward_pe'],MODEL_FAMILIES['normalized_fcf_dcf'])
        a=stock();b=deepcopy(a);b['ticker']='OTHER'
        self.assertEqual(governance_audit(a),governance_audit(b))

    def test_pe_pair_high_dependency(self):
        models=stock()['blend']['models']
        pair=dependency_pair('forward_pe','growth_adjusted_pe',models)
        self.assertAlmostEqual(pair['dependency_overlap_score'],6/7)
        self.assertEqual(pair['model_pair_governance_status'],'HIGH_DEPENDENCY')
        self.assertIn('EPS_BASIS',pair['shared_core_drivers'])

    def test_pe_dcf_low_and_dcf_ev_moderate(self):
        models=stock()['blend']['models'];models['ev_ebitda']={}
        self.assertEqual(dependency_pair('forward_pe','normalized_fcf_dcf',models)['model_pair_governance_status'],'LOW_DEPENDENCY')
        self.assertEqual(dependency_pair('normalized_fcf_dcf','ev_ebitda',models)['model_pair_governance_status'],'MODERATE_DEPENDENCY')

    def test_effective_count_distinguishes_two_family_and_pe_pair(self):
        data=observed_baseline()
        goog,msft=(governance_audit(s) for s in data[:2])
        self.assertEqual(goog['effective_independent_model_count'],2.25)
        self.assertEqual(msft['model_count_included'],2)
        self.assertEqual(msft['effective_independent_model_count'],1.25)

    def test_cross_family_uses_one_representative_per_family(self):
        result=governance_audit(stock())
        pe=(348.83+303.33)/2
        expected=(pe-139.72)/((pe+139.72)/2)*100
        self.assertAlmostEqual(result['cross_family_spread_pct'],expected)
        self.assertEqual(result['family_representatives']['EARNINGS_MULTIPLE']['family_mid_median'],pe)

    def test_msft_outlier_visible_and_suppressed(self):
        source=observed_baseline()[1];before=deepcopy(source)
        result=governance_audit(source)
        self.assertEqual(result['cross_family_status'],'CROSS_FAMILY_DISAGREEMENT')
        self.assertIn('CASH_FLOW_INTRINSIC',result['executed_families'])
        self.assertEqual(result['outlier_governance_flags'],['CROSS_FAMILY_SIGNAL_SUPPRESSED'])
        self.assertEqual(result['family_concentration_status'],'HIGH_FAMILY_CONCENTRATION')
        self.assertEqual(source,before)

    def test_no_preoutlier_payload_still_retains_outlier_numeric(self):
        source=observed_baseline()[1];source.pop('models_before_outlier')
        self.assertIn('CASH_FLOW_INTRINSIC',governance_audit(source)['executed_families'])

    def test_nonoutlier_invalid_result_not_successful_signal(self):
        source=observed_baseline()[1]
        source['models_before_outlier']['normalized_fcf_dcf'].update(valid=False,reason='DCF_LOW_RELIABILITY')
        source['blend']['models']['normalized_fcf_dcf'].update(outlier=False,reason='DCF_LOW_RELIABILITY')
        result=governance_audit(source)
        self.assertEqual(result['cross_family_status'],'SINGLE_FAMILY_ONLY')
        self.assertEqual(result['outlier_governance_flags'],[])

    def test_unexecuted_dcf_not_family_evidence(self):
        result=governance_audit(observed_baseline()[2])
        self.assertEqual(result['cross_family_status'],'SINGLE_FAMILY_ONLY')
        self.assertEqual(result['executed_families'],['EARNINGS_MULTIPLE'])

    def test_orcl_positive_net_debt_pe_only_flag(self):
        source=observed_baseline()[2]
        source['financials']={'cash':10,'debt':110,'market_cap':1000}
        result=governance_audit(source)
        self.assertEqual(result['capital_structure']['net_debt'],100)
        self.assertEqual(result['capital_structure']['net_debt_to_market_cap'],.1)
        self.assertEqual(result['capital_structure_flags'],['CAPITAL_STRUCTURE_NOT_REPRESENTED_IN_ACTIVE_MODELS'])

    def test_unknown_capital_inputs_not_invented(self):
        result=governance_audit(observed_baseline()[2])
        self.assertIsNone(result['capital_structure']['net_debt'])
        self.assertEqual(result['capital_structure_flags'],[])

    def test_step_up_plus_shared_growth_is_high(self):
        source=observed_baseline()[3];source['financials']={'forward_eps':16,'trailing_eps':8}
        for name in ('forward_pe','growth_adjusted_pe'):
            source['blend']['models'][name]['inputs']['forward_eps']=16
        result=governance_audit(source)
        self.assertEqual(result['forward_to_trailing_eps_ratio'],2)
        self.assertEqual(result['growth_overlap_risk'],'HIGH')

    def test_proxy_pair_does_not_claim_shared_forward_eps_high(self):
        source=observed_baseline()[3];source['financials']={'forward_eps':16,'trailing_eps':8}
        for name in ('forward_pe','growth_adjusted_pe'):
            source['blend']['models'][name]['inputs'].update(forward_eps=16,uses_proxy=True)
        self.assertEqual(governance_audit(source)['growth_overlap_risk'],'MODERATE')

    def test_growth_model_alone_not_high(self):
        source=stock();source['blend']['included']=['growth_adjusted_pe']
        source['financials']={'forward_eps':16,'trailing_eps':8}
        self.assertEqual(governance_audit(source)['growth_overlap_risk'],'MODERATE')

    def test_missing_eps_ratio_unknown_not_assumed_high(self):
        result=governance_audit(observed_baseline()[3])
        self.assertIsNone(result['forward_to_trailing_eps_ratio'])
        self.assertEqual(result['growth_overlap_risk'],'MODERATE')

    def test_amzn_stable_but_not_independent_anchor(self):
        result=governance_audit(observed_baseline()[4])
        self.assertEqual(result['governance_summary'],'NUMERICALLY_STABLE_BUT_CONCENTRATED')
        self.assertEqual(result['governance_classification'],'SINGLE_FAMILY_ONLY')

    def test_threshold_boundaries(self):
        for a,b,expected in ((90,110,'CONSISTENT'),(80,120,'MODERATE_DISAGREEMENT'),(70,130,'CROSS_FAMILY_DISAGREEMENT')):
            source=stock()
            for container in (source['blend']['models'],source['models_before_outlier']):
                container['forward_pe']['mid']=a;container['growth_adjusted_pe']['mid']=a
                container['normalized_fcf_dcf']['mid']=b
            self.assertEqual(governance_audit(source)['cross_family_status'],expected)

    def test_benchmark_does_not_affect_governance(self):
        a=stock();b=deepcopy(a);b.update(external_benchmark=999999,price=999999)
        self.assertEqual(governance_audit(a),governance_audit(b))

    def test_no_production_values_weights_outlier_or_peer_changes(self):
        with patch('analysis_service._attach_peer_diagnostics',side_effect=lambda r,*a,**k:r):
            production=analyze_ticker('MSFT',history_loader=history,fundamentals_loader=lambda _:deepcopy(FINANCIALS['MSFT']),peer_mode='diagnostic')
        before=deepcopy(production['blend'])
        result=governance_audit(production)
        self.assertEqual(production['blend'],before)
        self.assertNotIn('peer_comparable',production['blend']['included'])
        self.assertEqual(result['model_count_included'],len(before['included']))

    def test_capture_csv_integration_and_no_database_writes(self):
        captured=admin.capture_analysis('GOOG',history_loader=history,fundamentals_loader=lambda _:deepcopy(FINANCIALS['GOOG']))
        before=deepcopy(captured)
        captured['correlation_cross_family_governance']=governance_audit(captured)
        payload=admin.csv_payload({'stocks':[captured]}).decode('utf-8-sig')
        self.assertIn('cross_family_status',payload)
        self.assertIn('effective_independent_model_count',payload)
        self.assertEqual(captured['live_blend'],before['live_blend'])

    def test_cached_live_mismatch_is_not_cross_family_evidence(self):
        source=stock();source['source_status']='cached_last_reliable'
        result=governance_audit(source)
        self.assertEqual(result['governance_classification'],'INSUFFICIENT_EVIDENCE')


if __name__=='__main__':unittest.main()
