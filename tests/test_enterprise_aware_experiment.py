from copy import deepcopy
import csv
import io
import unittest
from unittest.mock import patch
from enterprise_aware_experiment import enterprise_experiment,difference_band,DIAGNOSTIC_FAMILY_MAP
from capital_structure_overlay import capital_overlay
from test_capital_structure_overlay import fixture


class EnterpriseExperimentTests(unittest.TestCase):
    def test_ebitda_formula(self):
        m=enterprise_experiment(fixture())['ev_ebitda_model']
        self.assertEqual((m['low'],m['mid'],m['high']),(12,18,24))
        self.assertEqual(m['enterprise_values'],{'low':200,'mid':260,'high':320})

    def test_revenue_formula(self):
        m=enterprise_experiment(fixture())['ev_revenue_model']
        self.assertEqual((m['low'],m['mid'],m['high']),(22,37,52))

    def test_net_debt_deducted_once(self):
        m=enterprise_experiment(fixture())['ev_ebitda_model']
        self.assertEqual(m['equity_values']['mid'],260-80)

    def test_net_cash_increases_equity(self):
        s=fixture();s['normalized_inputs']['cash']=120
        self.assertEqual(enterprise_experiment(s)['ev_ebitda_model']['mid'],28)

    def test_canonical_shares_used(self):
        s=fixture();s['normalized_inputs'].update(canonical_shares=20,shares_outstanding=999)
        self.assertEqual(enterprise_experiment(s)['ev_ebitda_model']['mid'],9)

    def test_negative_equity_retained(self):
        s=fixture();s['normalized_inputs']['debt']=500
        e=enterprise_experiment(s)
        self.assertLess(e['ev_ebitda_model']['mid'],0)
        self.assertTrue(e['ev_ebitda_model']['negative_equity_signal'])
        self.assertTrue(e['ev_ebitda_model']['valid'])
        self.assertEqual(e['production_readiness'],'NOT_READY')

    def test_missing_ebitda_only_blocks_ebitda(self):
        s=fixture();s['normalized_inputs'].pop('ebitda')
        e=enterprise_experiment(s)
        self.assertFalse(e['ev_ebitda_model']['valid'])
        self.assertTrue(e['ev_revenue_model']['valid'])

    def test_missing_revenue_only_blocks_revenue(self):
        s=fixture();s['normalized_inputs'].pop('revenue')
        e=enterprise_experiment(s)
        self.assertTrue(e['ev_ebitda_model']['valid'])
        self.assertFalse(e['ev_revenue_model']['valid'])

    def test_equal_family_representative(self):
        e=enterprise_experiment(fixture())
        self.assertEqual(e['enterprise_family']['mid'],(18+37)/2)
        self.assertEqual(e['enterprise_family']['low'],(12+22)/2)
        self.assertEqual(e['enterprise_family']['weights'],{'ev_ebitda':.5,'ev_revenue':.5})

    def test_single_method_low(self):
        s=fixture();s['normalized_inputs']['revenue']=None
        e=enterprise_experiment(s)
        self.assertEqual(e['enterprise_family_confidence'],'LOW')
        self.assertTrue(e['single_method_only'])
        self.assertEqual(e['enterprise_evidence_status'],'SINGLE_METHOD')
        self.assertEqual(e['production_readiness'],'NOT_READY')

    def test_method_spread(self):
        e=enterprise_experiment(fixture())
        self.assertAlmostEqual(e['method_spread_pct'],(37-18)/27.5*100)
        self.assertEqual(e['method_consistency'],'METHOD_DISAGREEMENT')
        self.assertIn('ENTERPRISE_METHOD_DISAGREEMENT',e['warnings'])

    def test_earnings_comparison(self):
        e=enterprise_experiment(fixture())
        self.assertAlmostEqual(e['difference_vs_earnings_pct'],(27.5/e['earnings_family_mid']-1)*100)
        self.assertEqual(e['difference_direction'],'DOWN')
        self.assertEqual(e['enterprise_evidence_status'],'SEVERE_CONFLICT')

    def test_all_production_state_unchanged(self):
        s=fixture();s.update(structural_governance={'severity':'MODERATE'},confidence='LOW',
            reliability_score=50,peer_comparable_result={'mid':999},last_reliable={'calculated_at':'original'},exit_zone={'trim_price':None})
        before=deepcopy(s);enterprise_experiment(s)
        self.assertEqual(s,before)

    def test_diagnostic_family_registration_only(self):
        from model_family_governance import MODEL_FAMILIES
        before=deepcopy(MODEL_FAMILIES);e=enterprise_experiment(fixture())
        self.assertEqual(e['diagnostic_family_map'],DIAGNOSTIC_FAMILY_MAP)
        self.assertEqual(MODEL_FAMILIES,before)
        self.assertEqual(e['production_active_families'],['EARNINGS_MULTIPLE'])
        self.assertEqual(e['experimental_independent_family_count'],2)
        self.assertEqual(e['experimental_observed_families'],['EARNINGS_MULTIPLE','ENTERPRISE_MULTIPLE'])
        self.assertFalse(e['production_included'])

    def test_no_benchmark_price_or_peer_inputs(self):
        s=fixture();before=enterprise_experiment(s)
        s.update(benchmark=1,analyst_target=999,price=123,peer_comparable_result={'mid':1})
        s['normalized_inputs'].update(price=1e99,analyst_target=999)
        self.assertEqual(before,enterprise_experiment(s))

    def test_currency_mismatch_blocks_both(self):
        s=fixture();s['normalized_inputs']['financial_currency']='EUR'
        e=enterprise_experiment(s)
        self.assertEqual(e['enterprise_family_confidence'],'UNAVAILABLE')
        self.assertFalse(e['ev_ebitda_model']['valid'])
        self.assertFalse(e['ev_revenue_model']['valid'])

    def test_missing_class_range_no_default(self):
        s=fixture();s['profile_assumptions'].pop('ev_ebitda_range')
        e=enterprise_experiment(s)
        self.assertFalse(e['ev_ebitda_model']['valid'])
        self.assertTrue(e['ev_revenue_model']['valid'])

    def test_strong_candidate_rule(self):
        s=fixture();s['normalized_inputs']['revenue']=60
        e=enterprise_experiment(s)
        self.assertEqual(e['enterprise_family_confidence'],'MEDIUM')
        self.assertEqual(e['production_readiness'],'STRONG_CANDIDATE')
        self.assertLessEqual(e['method_spread_pct'],20)

    def test_disagreement_not_ready(self):
        self.assertEqual(enterprise_experiment(fixture())['production_readiness'],'NOT_READY')

    def test_never_high_confidence(self):
        s=fixture();s['normalized_inputs']['revenue']=60
        self.assertEqual(enterprise_experiment(s)['enterprise_family_confidence'],'MEDIUM')

    def test_equal_weight_experiment(self):
        e=enterprise_experiment(fixture())
        self.assertEqual(e['earnings_enterprise_equal_weight_fair'],(e['earnings_family_mid']+27.5)/2)
        self.assertEqual(e['production_fair'],237.75)

    def test_cached_and_ineligible_refused(self):
        for changes in ({'source_status':'cached_last_reliable'},{'calibration_eligibility':'INELIGIBLE'}):
            s=fixture();s.update(changes)
            self.assertEqual(enterprise_experiment(s)['enterprise_evidence_status'],'UNAVAILABLE')

    def test_business_mix_only_from_existing_field(self):
        s=fixture();self.assertIsNone(enterprise_experiment(s)['business_mix_warning'])
        s['normalized_inputs']['business_mix_warning']='captured mixed business warning'
        self.assertEqual(enterprise_experiment(s)['business_mix_warning'],'captured mixed business warning')

    def test_no_io(self):
        s=fixture()
        with patch('builtins.open',side_effect=AssertionError('unexpected IO')):enterprise_experiment(s)

    def test_ticker_independent(self):
        s=fixture();before=enterprise_experiment(s);s['ticker']='UNKNOWN'
        self.assertEqual(before,enterprise_experiment(s))

    def test_difference_band_boundaries(self):
        self.assertEqual([difference_band(x) for x in (-10,-25,-50,-50.01,None)],
            ['CONSISTENT','MODERATE_DIFFERENCE','MATERIAL_DIFFERENCE','SEVERE_DIFFERENCE','UNAVAILABLE'])

    def test_no_normal_snapshot_or_last_reliable_contamination(self):
        from tests.test_last_reliable_valuation import analyze,NOW
        from analysis_service import build_snapshot_record
        from last_reliable_valuation import reliable_snapshot
        r=analyze('AMZN');before=build_snapshot_record('u',r);saved=reliable_snapshot(r,NOW)
        enterprise_experiment(fixture())
        after=build_snapshot_record('u',r)
        # Ignore the independently generated last_reliable timestamp only.
        before['raw'].pop('last_reliable');after['raw'].pop('last_reliable')
        self.assertEqual(before,after)
        self.assertNotIn('enterprise_aware_experiment',after['raw'])
        self.assertEqual(saved,reliable_snapshot(r,NOW))

    def test_admin_five_stock_no_database_write(self):
        import test_v45_snapshot_export as fixtures
        helper=fixtures.SnapshotExportTests();helper.setUp()
        try:
            helper.client.table.side_effect=AssertionError('No database access')
            report=helper.batch()
            self.assertEqual(len(report['stocks']),5)
            self.assertTrue(all('enterprise_aware_experiment' in s for s in report['stocks']))
            helper.client.table.assert_not_called()
        finally:helper.doCleanups()

    def test_csv_summary_namespace(self):
        from production_snapshot_admin import csv_payload
        s=fixture();s['enterprise_aware_experiment']=enterprise_experiment(s);s['models']=[{'model_name':'forward_pe'}]
        row=next(csv.DictReader(io.StringIO(csv_payload({'stocks':[s]}).decode('utf-8-sig'))))
        self.assertEqual(row['enterprise_aware_experiment.ev_ebitda_mid'],'18.0')
        self.assertEqual(row['enterprise_aware_experiment.production_readiness'],'NOT_READY')

    def test_consistent_low_burden_review_only(self):
        s=fixture();s['normalized_inputs'].update(cash=120,ebitda=100,revenue=300,ebit=100)
        self.assertEqual(enterprise_experiment(s)['production_readiness'],'REVIEW_CANDIDATE')

    def test_nonfinite_computation_not_valid(self):
        s=fixture();s['normalized_inputs']['ebitda']=1e308
        e=enterprise_experiment(s)
        self.assertFalse(e['ev_ebitda_model']['valid'])
        self.assertIsNone(e['ev_ebitda_model']['mid'])

    def test_twenty_percent_boundary(self):
        s=fixture();s['normalized_inputs']['revenue']=(22*10+80)/4.5
        e=enterprise_experiment(s)
        self.assertAlmostEqual(e['method_spread_pct'],20)
        self.assertEqual(e['method_consistency'],'CONSISTENT')
        self.assertEqual(e['enterprise_family_confidence'],'MEDIUM')

    def test_forty_percent_boundary(self):
        s=fixture();s['normalized_inputs']['revenue']=(27*10+80)/4.5
        e=enterprise_experiment(s)
        self.assertAlmostEqual(e['method_spread_pct'],40)
        self.assertEqual(e['method_consistency'],'MODERATE_DISAGREEMENT')
