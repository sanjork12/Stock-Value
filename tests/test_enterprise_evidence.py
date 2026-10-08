from copy import deepcopy
import inspect
import json
import math
import unittest
from unittest.mock import patch
import pandas as pd

import enterprise_evidence as e
from enterprise_evidence_policy import POLICY,COVERAGE_WEIGHTS
from enterprise_family_suitability import suitability_audit,COMPONENT_MAX,score_state
from test_enterprise_family_suitability import fixture as v49_fixture
import test_v45_snapshot_export as snapshot_tests


def observations(values,source='test.direct',periods=None):
    return [{'period':p,'value':v,'source':source,'basis':'FY','currency':'USD','derivation':'DIRECT_STATEMENT_LINE'}
        for p,v in zip(periods or ['2022-12-31','2023-12-31','2024-12-31'],values)]


def fixture():
    s=v49_fixture();s['ticker']='TEST';s['input_batch_id']='batch';s['fundamentals_acquisition_id']='acq'
    f=s['normalized_inputs'];f.update(input_batch_id='batch',fundamentals_acquisition_id='acq',operating_income=20,
        canonical_shares_basis='CURRENT_SHARE_COUNT',enterprise_metric_basis={'ebitda':'QUOTE_SUMMARY_TTM','revenue':'QUOTE_SUMMARY_TTM','cash':'LATEST_BALANCE_SHEET','debt':'LATEST_BALANCE_SHEET'})
    for k in ('ebitda','revenue','cash','debt','canonical_shares'):
        f['acquisition_provenance'][k]={'source':'test.direct.'+k,'source_type':'DIRECT','currency':'USD','as_of_date':'2024-12-31'}
    s['enterprise_structural_metadata']={'heterogeneous_business_mix':False}
    captured={'ticker':'TEST','historical_evidence_acquisition_id':'history-acq','statement_observations':2,'series':{
        'ebitda':observations([20,21,22]),'operating_income':observations([20,21,22]),
        'revenue':observations([100,105,110]),'operating_margin':observations([.2,.2,.2]),
        'capex':observations([-2,-2.1,-2.2]),'operating_cash_flow':observations([30,31.5,33]),
        'free_cash_flow':observations([28,29.4,30.8]),'sbc':observations([2,2.1,2.2]),
        'eps':observations([4,4.2,4.4]),'unusual_items':observations([0,0,0])}}
    s['evidence_snapshot']=e.evidence_snapshot(s,captured)
    s['enterprise_family_suitability']=suitability_audit(s,batch_eligibility='ELIGIBLE')
    return s


def build(s):return e.build_structural_evidence(s,batch_eligibility='ELIGIBLE')
def complete(s):return e.complete_stock(s,batch_eligibility='ELIGIBLE')

def replace_history(s,key,values):
    s['evidence_snapshot']['series'][key]=e.annual_stats(observations(values))


class EvidenceTests(unittest.TestCase):
    def setUp(self):self.s=fixture()
    def test_missing_is_not_false(self):
        self.s['enterprise_structural_metadata']={};r=build(self.s)['business_mix']
        self.assertEqual(r['status'],'INSUFFICIENT_EVIDENCE');self.assertNotEqual(r['value'],False)
    def test_missing_is_not_zero(self):
        self.assertEqual(e.safe_ratio(None,5),(None,'MISSING_NUMERATOR'))
        self.assertIsNone(e.annual_stats(observations([None,None,None]))['mean'])
        self.s['normalized_inputs']['cash']=0
        self.s['normalized_inputs']['acquisition_provenance']['cash']['source']='existing_missing_assumed_zero'
        result=build(self.s)
        self.assertEqual(self.s['normalized_inputs']['cash'],0)
        self.assertIsNone(result['current_input_references']['cash']['evidence_value'])
        self.assertEqual(result['current_input_references']['cash']['value'],0)
        self.assertEqual(result['capital_structure_relevance']['value'],'UNKNOWN')
    def test_three_periods_required(self):
        replace_history(self.s,'ebitda',[20,21]);self.assertEqual(build(self.s)['ebitda_stability']['value'],'INSUFFICIENT_EVIDENCE')
    def test_nonpositive_ebitda(self):
        self.s['normalized_inputs']['ebitda']=0;self.assertEqual(build(self.s)['ebitda_meaningfulness']['value'],'NOT_MEANINGFUL')
    def test_cv(self):
        r=e.annual_stats(observations([10,20,30]));self.assertAlmostEqual(r['coefficient_of_variation'],math.sqrt(200/3)/20)
    def test_cagr(self):self.assertAlmostEqual(e.annual_stats(observations([100,110,121]))['cagr'],.1)
    def test_operating_margin_slope(self):
        r=e.annual_stats(observations([.1,.15,.2]));self.assertAlmostEqual(r['trend_slope'],.05)
        self.assertEqual(e.margin_regime(r)['value'],'EXPANDING')
    def test_margin_spread(self):self.assertAlmostEqual(e.annual_stats(observations([.1,.15,.2]))['spread'],.1)
    def test_capex_revenue(self):self.assertAlmostEqual(build(self.s)['capital_intensity']['ratios']['capex_to_revenue']['value'],.02)
    def test_capex_ocf(self):self.assertAlmostEqual(build(self.s)['capital_intensity']['ratios']['capex_to_ocf']['value'],2.2/33)
    def test_fcf_ocf(self):self.assertAlmostEqual(build(self.s)['capital_intensity']['ratios']['fcf_to_ocf']['value'],30.8/33)
    def test_da_approximation_label(self):self.assertEqual(build(self.s)['depreciation_amortization_distortion']['source_kind'],'DERIVED_APPROXIMATION')
    def test_direct_da(self):
        replace_history(self.s,'depreciation_and_amortization',[1,1.1,1.2])
        self.assertEqual(build(self.s)['depreciation_amortization_distortion']['source_kind'],'DIRECT_STATEMENT_LINE')
    def test_sbc_missing_unknown(self):
        replace_history(self.s,'sbc',[]);self.assertEqual(build(self.s)['sbc_distortion']['value'],'UNKNOWN')
    def test_geographic_not_business(self):
        self.s['enterprise_structural_metadata']={};self.s['structural_segments']={'basis':'GEOGRAPHIC','source':'test','complete':True,'segments':[{'revenue':70},{'revenue':30}]}
        self.assertEqual(build(self.s)['business_mix']['value'],'INSUFFICIENT_EVIDENCE')
    def test_explicit_operating_segments(self):
        self.s['enterprise_structural_metadata']={};self.s['structural_segments']={'basis':'OPERATING_SEGMENTS','source':'test.operating','complete':True,'period':'FY2024',
            'segments':[{'name':'A','revenue':70,'operating_margin':.4,'economic_model':'subscription'}, {'name':'B','revenue':30,'operating_margin':.02,'economic_model':'retail'}]}
        self.assertEqual(build(self.s)['business_mix']['value'],'HETEROGENEOUS')
        self.assertEqual(build(self.s)['segment_complexity']['value'],'HIGH')
    def test_incomplete_segments_not_homogeneous(self):
        self.s['enterprise_structural_metadata']={};self.s['structural_segments']={'basis':'OPERATING_SEGMENTS','source':'test','segments':[{'revenue':100}]}
        self.assertEqual(build(self.s)['business_mix']['value'],'INSUFFICIENT_EVIDENCE')
    def test_basis_mismatch(self):
        self.s['normalized_inputs']['enterprise_metric_basis']['revenue']='FY'
        self.assertEqual(build(self.s)['enterprise_input_basis_compatibility']['value'],'MIXED_BASIS')
    def test_currency_mismatch(self):
        self.s['normalized_inputs']['financial_currency']='EUR'
        self.assertEqual(build(self.s)['enterprise_input_basis_compatibility']['value'],'INCOMPATIBLE')
    def test_period_warning(self):
        r=e.annual_stats(observations([1,2,3],periods=['2024-03-31','2024-06-30','2024-09-30']))
        self.assertIn('PERIOD_ALIGNMENT_WARNING',r['warnings']);self.assertEqual(r['observation_count'],0)
    def test_fiscal_label_not_mixed_with_date(self):
        r=e.annual_stats(observations([1,2,3],periods=['FY2022','2023-12-31','2024-12-31']))
        self.assertIn('PERIOD_ALIGNMENT_WARNING',r['warnings']);self.assertEqual(len(r['raw_series']),3)
    def test_ttm_not_annual(self):
        obs=observations([1,2,3]);obs[0]['basis']='TTM'
        self.assertEqual(e.annual_stats(obs)['observation_count'],2)
    def test_missing_growth_not_zero(self):
        r=e.annual_stats(observations([0,2,3]));self.assertIsNone(r['yoy_changes'][0]['value'])
        self.assertEqual(r['yoy_changes'][0]['reason'],'INVALID_DENOMINATOR')
    def test_outliers_not_silently_removed(self):
        r=e.annual_stats(observations([1,100,2]));self.assertEqual(r['observation_count'],3);self.assertTrue(r['anomalies'])
    def test_duplicate_periods_explained(self):
        r=e.annual_stats(observations([1,2,3],periods=['FY2022','FY2022','FY2023']))
        self.assertEqual(r['observation_count'],1);self.assertTrue(r['excluded_observations'])
    def test_mean_zero_cv_unknown(self):self.assertIsNone(e.annual_stats(observations([-1,0,1]))['coefficient_of_variation'])
    def test_sign_changes(self):self.assertEqual(e.annual_stats(observations([-1,2,-3]))['sign_changes'],2)
    def test_ticker_alone_not_business_mix(self):
        self.s['enterprise_structural_metadata']={};a=build(self.s)['business_mix'];self.s['ticker']='AMZN'
        self.assertEqual(a,build(self.s)['business_mix'])
    def test_ticker_alone_not_growth(self):
        a=build(self.s)['growth_regime'];self.s['ticker']='NVDA';self.assertEqual(a,build(self.s)['growth_regime'])
    def test_unreviewed_curated_blocks_candidate_yes(self):
        self.s['enterprise_structural_metadata']={};self.s['curated_structural_metadata']={'heterogeneous_business_mix':False,
            'source_type':'CURATED_STRUCTURAL_METADATA','source_note':'Synthetic test fixture, not Cloud evidence',
            'as_of':'2024-12-31','effective_date':'2024-12-31','review_status':'REQUIRES_HUMAN_REVIEW','reviewed':False,'confidence':'LOW'}
        r=complete(self.s);self.assertEqual(r['v49_after']['production_candidate'],'NO')
        self.assertIn('UNREVIEWED_CURATED_METADATA',r['v49_evidence_delta']['candidate_ceilings'])
    def test_stability_replaces_unknown(self):
        r=complete(self.s);self.assertTrue(r['v49_evidence_adapter']['values']['ebitda_stable'])
        self.assertGreater(r['v49_after']['ev_ebitda']['score'],r['v49_before']['ev_ebitda']['score'])
    def test_instability_can_lower_score(self):
        self.s['enterprise_structural_metadata'].update(ebitda_stable=True,ebitda_economically_meaningful=True,revenue_interpretable=True)
        self.s['enterprise_family_suitability']=suitability_audit(self.s,batch_eligibility='ELIGIBLE')
        replace_history(self.s,'ebitda',[1,100,2]);r=complete(self.s)
        self.assertFalse(r['v49_evidence_adapter']['values']['ebitda_stable'])
        self.assertLess(r['v49_after']['ev_ebitda']['score'],r['v49_before']['ev_ebitda']['score'])
    def test_heterogeneity_lowers_company(self):
        before=complete(self.s);self.s['enterprise_structural_metadata']['heterogeneous_business_mix']=True
        after=complete(self.s)
        self.assertNotEqual(after['v49_after']['company_level']['aggregation_policy_assessment'],'EQUAL_WEIGHT_REASONABLE')
        self.assertNotEqual(before['v49_after']['company_level']['suitability'],after['v49_after']['company_level']['suitability'])
    def test_missing_mix_remains_omitted(self):
        self.s['enterprise_structural_metadata']={};adapter=e.build_v49_evidence_adapter(build(self.s))['values']
        self.assertNotIn('heterogeneous_business_mix',adapter);self.assertNotIn('business_mix_warning',adapter)
    def test_margin_adapter(self):self.assertEqual(e.build_v49_evidence_adapter(build(self.s))['values']['margin_regime'],'STABLE_MODERATE_MARGIN')
    def test_revenue_adapter(self):self.assertTrue(e.build_v49_evidence_adapter(build(self.s))['values']['revenue_interpretable'])
    def test_delta_explained(self):
        r=complete(self.s)['v49_evidence_delta']['methods']['ev_ebitda'];self.assertTrue(r['drivers'])
        self.assertEqual(sum(v['delta'] for v in r['component_changes'].values()),r['delta'])
    def test_v49_weights_unchanged(self):self.assertEqual(COMPONENT_MAX,{'class_fit':25,'input_quality':20,'economic_interpretability':20,'business_mix_fit':15,'growth_regime_fit':10,'consistency_support':10})
    def test_v49_thresholds_unchanged(self):self.assertEqual([score_state(v) for v in (85,70,50,30,29)],['PREFERRED','ACCEPTABLE','CONDITIONAL','NOT_PREFERRED','NOT_ELIGIBLE'])
    def test_same_batch_identity(self):
        r=build(self.s);self.assertEqual(r['input_batch_id'],'batch');self.assertEqual(r['fundamentals_acquisition_id'],'acq')
    def test_separate_history_identity(self):self.assertEqual(build(self.s)['historical_evidence_acquisition_id'],'history-acq')
    def test_identity_mismatch_ineligible(self):
        self.s['input_batch_id']='unrelated';self.assertEqual(build(self.s)['audit_status'],'V5_INPUT_STATE_INELIGIBLE')
    def test_calibration_ineligible(self):
        r=e.build_structural_evidence(self.s,batch_eligibility='INELIGIBLE');self.assertFalse(r['formal_completion_conclusion_allowed'])
    def test_cached_last_reliable_does_not_unlock(self):
        self.s['source_status']='cached_last_reliable';self.assertEqual(build(self.s)['audit_status'],'V5_INPUT_STATE_INELIGIBLE')
    def test_observer_uses_existing_frame_no_calls(self):
        frame=pd.DataFrame({'2024-12-31':[100,20,22,999]},index=['Total Revenue','Operating Income','EBITDA','SECRET'])
        from financial_forensics_observer import observe_statement
        with e.observe_enterprise_statements('TEST') as captured:observe_statement('income_stmt','ticker.income_stmt',frame)
        self.assertIn('ebitda',captured['series']);self.assertNotIn('SECRET',json.dumps(captured))
        self.assertEqual(captured['statement_observations'],1)
    def test_observer_context_resets(self):
        with e.observe_enterprise_statements('A') as first:pass
        with e.observe_enterprise_statements('B') as second:pass
        self.assertNotEqual(first['historical_evidence_acquisition_id'],second['historical_evidence_acquisition_id'])
        self.assertEqual(second['series'],{})
    def test_wrong_ticker_history_rejected(self):
        snapshot=e.evidence_snapshot(self.s,{'ticker':'OTHER','series':{'ebitda':observations([10,20,30])}})
        self.assertEqual(snapshot['series']['ebitda']['observation_count'],0)
        self.assertIn('HISTORICAL_TICKER_MISMATCH',snapshot['warnings'])
    def test_no_network_or_storage_dependencies(self):
        source=inspect.getsource(e)
        for forbidden in ('import yfinance','import requests','import supabase','get_live_fundamentals(','RAW_CACHE.get('):self.assertNotIn(forbidden,source)
    def test_coverage_only_completeness(self):
        r=build(self.s);self.assertEqual(sum(COVERAGE_WEIGHTS.values()),100)
        self.assertAlmostEqual(r['evidence_coverage_score'],sum(r['evidence_coverage']['components'].values()))
    def test_every_record_has_provenance(self):
        for key,value in build(self.s).items():
            if isinstance(value,dict) and 'value' in value:
                for field in ('value','status','confidence','source_fields','source_periods','derivation','reason_codes','missing_inputs'):self.assertIn(field,value,key)
    def test_report_export(self):
        report=e.complete_report({'batch_id':'batch','input_batch_id':'batch','batch_calibration_eligibility':'ELIGIBLE','stocks':[self.s]})
        self.assertEqual(e.export_report(report)['stocks'][0]['enterprise_structural_evidence']['input_batch_id'],'batch')
        self.assertEqual(len(e.export_csv(report).decode('utf-8-sig').splitlines()),2)
    def test_no_production_integration_even_if_candidate_yes(self):
        r=complete(self.s);self.assertFalse(r['production_integration_performed']);self.assertFalse(r['enterprise_structural_evidence']['production_integration_performed'])
    def test_complete_input_not_mutated(self):
        original=deepcopy(self.s);r=complete(self.s);self.assertEqual(original,self.s)
        additions=('enterprise_structural_evidence','v49_evidence_adapter','v49_before','v49_after','v49_evidence_delta','production_integration_performed')
        for key in additions:r.pop(key)
        self.assertEqual(r,original)
    def test_five_stock_batch_no_db_no_refetch(self):
        t=snapshot_tests.SnapshotExportTests();t.setUp()
        try:
            t.client.table.side_effect=AssertionError('No database reads/writes')
            report=t.batch();original=deepcopy(report)
            with patch('mag7_monitor.get_live_fundamentals',side_effect=AssertionError('No re-fetch')):
                completed=e.complete_report(report)
            self.assertEqual(len(completed['stocks']),5);self.assertEqual(report,original)
            self.assertEqual({s['enterprise_structural_evidence']['telemetry']['logical_calls'] for s in completed['stocks']},{0})
            t.client.table.assert_not_called()
        finally:t.tearDown()


    def test_no_high_meaningfulness_from_positive_ebitda_alone(self):
        self.s['evidence_snapshot']['series']['ebitda']=e.annual_stats([])
        self.assertNotEqual(build(self.s)['ebitda_meaningfulness']['value'],'HIGH')
    def test_missing_asof_is_not_reporting_date(self):
        for r in self.s['normalized_inputs']['acquisition_provenance'].values():r.pop('as_of_date',None);r['acquired_at']='2024-12-31'
        self.assertNotEqual(build(self.s)['enterprise_input_basis_compatibility']['value'],'COMPATIBLE')
    def test_ambiguous_basis_remains_unknown(self):
        self.s['normalized_inputs']['enterprise_metric_basis']['ebitda']='QUOTE_SUMMARY_TTM_OR_PROVIDER_CURRENT'
        self.assertEqual(build(self.s)['enterprise_input_basis_compatibility']['value'],'UNKNOWN')
    def test_unrecognized_basis_not_compatible(self):
        self.s['normalized_inputs']['enterprise_metric_basis']['ebitda']='TEST_UNGOVERNED_BASIS'
        self.assertEqual(build(self.s)['enterprise_input_basis_compatibility']['value'],'UNKNOWN')
    def test_asof_gap_mixed_basis(self):
        self.s['normalized_inputs']['acquisition_provenance']['ebitda']['as_of_date']='2020-12-31'
        self.assertEqual(build(self.s)['enterprise_input_basis_compatibility']['value'],'MIXED_BASIS')
    def test_large_da_qualifies_interpretation(self):
        replace_history(self.s,'ebitda',[50,52.5,55]);r=build(self.s)
        self.assertEqual(r['depreciation_amortization_distortion']['value'],'HIGH')
        self.assertEqual(r['ebitda_meaningfulness']['value'],'LOW')
    def test_large_sbc_is_not_missing(self):
        replace_history(self.s,'sbc',[30,31.5,33]);r=build(self.s)
        self.assertEqual(r['sbc_distortion']['value'],'VERY_HIGH');self.assertEqual(r['accounting_distortion']['value'],'HIGH')
    def test_missing_accounting_not_clean(self):
        replace_history(self.s,'sbc',[]);replace_history(self.s,'unusual_items',[])
        self.assertEqual(build(self.s)['accounting_distortion']['value'],'UNKNOWN')
    def test_high_optionality_not_primary_yes(self):
        self.s['live_blend']['profile']['optionality_level']='high'
        self.assertEqual(build(self.s)['operating_fundamentals_primary_value_driver']['value'],'PARTIAL')
    def test_crypto_not_operating_anchor(self):
        self.s['live_blend']['profile']['valuation_class']='crypto_treasury'
        self.assertEqual(build(self.s)['operating_fundamentals_primary_value_driver']['value'],'NO')
    def test_revenue_discontinuity_retained_as_evidence(self):
        replace_history(self.s,'revenue',[100,500,110]);r=build(self.s)
        self.assertEqual(r['revenue_interpretability']['value'],'LOW')
        self.assertEqual(r['growth_regime']['value'],'DISTORTED')
    def test_legacy_normalized_history_is_preserved(self):
        self.s.pop('evidence_snapshot');self.s['normalized_inputs']['historical_margins']=[{'period':'FY2024','revenue':100,'operating_income':20,'operating_margin':.2}]
        r=complete(self.s);self.assertIn('evidence_snapshot',r)
        self.assertEqual(r['evidence_snapshot']['series']['revenue']['observation_count'],1)
    def test_invalid_identity_after_is_not_formal(self):
        self.s['fundamentals_acquisition_id']='other'
        r=complete(self.s);self.assertEqual(r['v49_after']['audit_status'],'INELIGIBLE_INPUT_STATE')
        self.assertEqual(r['v49_after']['production_candidate'],'NO')
    def test_current_price_actual_normalized_path_ignored(self):
        r=build(self.s);self.s['normalized_inputs']['current_price']=999999
        self.assertEqual(build(self.s),r)
    def test_benchmark_inside_metadata_ignored(self):
        r=build(self.s);self.s['enterprise_structural_metadata']['analyst_target']=999999
        self.assertEqual(build(self.s),r)
    def test_observer_failure_does_not_fail_financial_loading(self):
        with e.observe_enterprise_statements('TEST') as captured:
            with patch.object(e,'_observe_statement_values',side_effect=ValueError('SECRET')):
                e.observe_statement_values('income_stmt','ticker.income_stmt',object())
        self.assertEqual(captured['observation_errors'],[{'stage':'income_stmt','category':'ValueError'}])
        self.assertNotIn('SECRET',json.dumps(captured))
    def test_production_capture_collects_history_without_extra_acquisition(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        import fundamental_acquisition as acquisition
        import production_snapshot_admin as admin
        from production_input_wiring import snapshot_fundamentals
        from test_quality_acquisition import Healthy
        from scripts.verify_peer_isolation import history
        def factory(ticker):
            yahoo=Healthy(ticker)
            for row,values in {'Total Revenue':[20e9,19e9,18e9],'Operating Income':[4e9,3.8e9,3.6e9],'EBITDA':[5e9,4.75e9,4.5e9]}.items():yahoo.income_stmt.loc[row]=values
            yahoo.cashflow.loc['Stock Based Compensation']=[.4e9,.38e9,.36e9]
            return yahoo
        factory_mock=Mock(side_effect=factory)
        t=snapshot_tests.SnapshotExportTests();t.setUp()
        try:
            t.client.table.side_effect=AssertionError('No database')
            with patch('mag7_monitor._yfinance',return_value=SimpleNamespace(Ticker=factory_mock)),patch.object(acquisition,'RAW_CACHE',acquisition.RawAcquisitionCache()),patch.object(acquisition,'flags',return_value=acquisition.Flags()):
                report=admin.run_batch(t.client,'u',t.secrets,history_loader=history,fundamentals_loader=snapshot_fundamentals)
                self.assertEqual(factory_mock.call_count,5)
                completed=e.complete_report(report);self.assertEqual(factory_mock.call_count,5)
            for before,after in zip(report['stocks'],completed['stocks']):
                self.assertEqual(after['evidence_snapshot']['series']['ebitda']['observation_count'],3)
                self.assertEqual(after['evidence_snapshot']['series']['sbc']['observation_count'],3)
                self.assertEqual(before['production_input_trace'],after['production_input_trace'])
                self.assertEqual(before['live_blend'],after['live_blend'])
            t.client.table.assert_not_called()
        finally:t.tearDown()

    def test_segment_evidence_not_masked_by_simple_metadata(self):
        self.s['structural_segments']={'basis':'OPERATING_SEGMENTS','source':'test.direct','period':'FY2024','complete':True,
            'segments':[{'revenue':70,'operating_margin':.5},{'revenue':30,'operating_margin':.01}]}
        result=build(self.s)['business_mix']
        self.assertEqual(result['value'],'HETEROGENEOUS')
        self.assertIn('EXPLICIT_METADATA_SEGMENT_CONFLICT',result['reason_codes'])
    def test_curated_governance_preserved(self):
        metadata={'heterogeneous_business_mix':True,'source_type':'CURATED_STRUCTURAL_METADATA','source_note':'public evidence test',
            'effective_date':'2024-12-31','as_of':'2024-12-31','review_status':'REQUIRES_HUMAN_REVIEW','reviewed':False,'confidence':'LOW'}
        self.s['curated_structural_metadata']=metadata
        result=build(self.s)['business_mix']['metadata_governance']
        self.assertEqual(result['source_note'],metadata['source_note']);self.assertIs(result['reviewed'],False)
    def test_v49_without_v5_preserves_legacy_margin_proxy(self):
        from enterprise_family_suitability import evidence
        self.s['enterprise_structural_metadata'].update(ebitda_stable=False,margin_regime='STABLE_MODERATE_MARGIN')
        self.assertTrue(evidence(self.s,'mega_cap_tech')['stable'])
        self.s['enterprise_structural_metadata']['_evidence_policy_version']='v5.0'
        self.assertFalse(evidence(self.s,'mega_cap_tech')['stable'])
    def test_nonfinite_ratio_is_not_exported(self):
        self.assertEqual(e.safe_ratio(1e308,1e-308),(None,'NONFINITE_RATIO'))

def isolated_test(field):
    def test(self):
        original=build(self.s);self.s[field]={'value':999999};self.assertEqual(build(self.s),original)
    return test
for name in ('current_price','analyst_target','benchmark','production_fair','peer_fair','last_reliable',
    'reliability','weights','outliers','buy_zones','exit_zones','capital_structure_overlay','enterprise_aware_experiment'):
    setattr(EvidenceTests,'test_isolated_'+name,isolated_test(name))

if __name__=='__main__':unittest.main()
