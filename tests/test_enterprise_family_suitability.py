from copy import deepcopy
import json
import unittest
from enterprise_family_suitability import (suitability_audit,attach_report,audit_export,csv_export,policy_matrix,consistency,COMPONENT_MAX)
from enterprise_aware_experiment import enterprise_experiment
from tests.test_capital_structure_overlay import fixture as base_fixture


def fixture():
    s=base_fixture();s.update(source_status='live',calibration_eligibility='ELIGIBLE')
    s['live_blend']={'profile':{'valuation_class':'mega_cap_tech','profitability_state':'PROFITABLE'},
        'fair_value':237.75,'low':200,'mid':237.75,'high':280,'models':{},
        'reliability_score':70,'confidence':'MEDIUM','outliers':[],'buy_zones':[100],'exit_zones':[300]}
    s['normalized_inputs'].update(debt=10,canonical_shares_source='statement',earnings_growth=.1,revenue_growth=.1,
        operating_margin=.2,gross_margin=.6,normalized_capex=2,operating_cash_flow=30,
        acquisition_provenance={k:{'source_type':'DIRECT'} for k in ('ebitda','revenue','cash','debt')})
    s['enterprise_structural_metadata']={'heterogeneous_business_mix':False,'ebitda_economically_meaningful':True,
        'ebitda_stable':True,'revenue_interpretable':True,'scalable_operating_economics':True}
    s['profile_assumptions'].update(sales_multiple_range=(2.4,2.8))
    s['enterprise_aware_experiment']=enterprise_experiment(s)
    s['enterprise_aware_experiment']['method_spread_pct']=10 # controlled captured result for suitability tests
    return s


def audit(s):return suitability_audit(s,batch_eligibility='ELIGIBLE')


class SuitabilityTests(unittest.TestCase):
    def setUp(self):self.s=fixture()
    def test_class_policy_covers_fourteen(self):self.assertEqual(len(policy_matrix()),14)
    def test_two_good_consistent(self):self.assertEqual(audit(self.s)['company_level']['aggregation_policy_assessment'],'EQUAL_WEIGHT_REASONABLE')
    def test_moderate_spread(self):
        self.s['enterprise_aware_experiment']['method_spread_pct']=30
        self.assertEqual(audit(self.s)['company_level']['suitability'],'CONDITIONAL')
    def test_material_spread(self):
        self.s['enterprise_aware_experiment']['method_spread_pct']=50
        self.assertNotEqual(audit(self.s)['company_level']['aggregation_policy_assessment'],'EQUAL_WEIGHT_REASONABLE')
    def test_spread_boundaries(self):self.assertEqual([consistency(v) for v in (20,40,41,None)],['CONSISTENT','MODERATE_DISAGREEMENT','MATERIAL_DISAGREEMENT','UNKNOWN'])
    def test_one_strong_one_weak(self):
        self.s['live_blend']['profile']['valuation_class']='mature_growth'
        self.assertEqual(audit(self.s)['company_level']['preferred_enterprise_method'],'EV_EBITDA')
    def test_both_weak(self):
        self.s['live_blend']['profile']['valuation_class']='cyclical_semiconductor'
        self.assertNotEqual(audit(self.s)['enterprise_family_production_candidate'],'YES')
    def test_consistency_not_accuracy_points(self):
        for method in ('ev_ebitda','ev_revenue'):self.assertEqual(audit(self.s)[method]['score_components']['consistency_support'],0)
    def test_high_growth(self):
        self.s['live_blend']['profile']['valuation_class']='semiconductor_growth';self.s['normalized_inputs']['revenue_growth']=.8
        a=audit(self.s);self.assertEqual(a['growth_regime_mismatch_flag'],'MATERIAL');self.assertNotEqual(a['ev_ebitda']['suitability'],'NOT_ELIGIBLE')
        self.assertNotEqual(a['enterprise_family_production_candidate'],'YES')
    def test_high_growth_class_possible_without_number(self):
        self.s['live_blend']['profile']['valuation_class']='high_growth_software'
        self.assertEqual(audit(self.s)['growth_regime_mismatch_flag'],'POSSIBLE')
    def test_score_total_and_maxima(self):
        for m in ('ev_ebitda','ev_revenue'):
            a=audit(self.s)[m];self.assertEqual(sum(a['score_components'].values()),a['score'])
            self.assertTrue(all(0<=v<=COMPONENT_MAX[k] for k,v in a['score_components'].items()))
    def test_missing_evidence_unknown(self):
        self.s.pop('enterprise_structural_metadata');a=audit(self.s)
        self.assertEqual(a['business_mix_warning'],'UNKNOWN');self.assertIn('ebitda_meaningfulness',a['ev_ebitda']['missing_evidence'])
        self.assertNotEqual(a['enterprise_family_production_candidate'],'YES')
    def test_explicit_mix_weakens_company(self):
        self.s['enterprise_structural_metadata']['heterogeneous_business_mix']=True
        self.assertNotEqual(audit(self.s)['company_level']['suitability'],'ACCEPTABLE')
    def test_mix_risk_blocks_company(self):
        self.s['enterprise_structural_metadata']['company_level_multiple_risk']=True
        self.assertEqual(audit(self.s)['company_level']['suitability'],'NOT_ELIGIBLE')
    def test_direct_proof_needed(self):
        self.s['normalized_inputs'].pop('acquisition_provenance')
        self.assertNotEqual(audit(self.s)['ev_ebitda']['production_candidate'],'YES')
    def test_batch_ineligible(self):
        a=suitability_audit(self.s,batch_eligibility='INELIGIBLE');self.assertEqual(a['audit_status'],'INELIGIBLE_INPUT_STATE')
        self.assertEqual(a['enterprise_family_production_candidate'],'NO')
    def test_missing_batch_ineligible(self):self.assertEqual(suitability_audit(self.s)['audit_status'],'INELIGIBLE_INPUT_STATE')
    def test_stock_ineligible(self):
        self.s['calibration_eligibility']='DEGRADED';self.assertEqual(audit(self.s)['audit_status'],'INELIGIBLE_INPUT_STATE')
    def test_cached_input_ineligible(self):
        self.s['source_status']='cached_last_reliable';self.assertEqual(audit(self.s)['enterprise_family_production_candidate'],'NO')
    def test_five_stock_export(self):
        stocks=[]
        for ticker in ('GOOG','MSFT','ORCL','NVDA','AMZN'):
            s=deepcopy(self.s);s['ticker']=ticker;stocks.append(s)
        report={'batch_id':'same','batch_calibration_eligibility':'ELIGIBLE','stocks':stocks}
        self.assertEqual(len(audit_export(report)['stocks']),5);self.assertEqual(len(csv_export(report).decode('utf-8-sig').splitlines()),6)
    def test_report_pure_and_only_namespace(self):
        report={'batch_id':'same','batch_calibration_eligibility':'ELIGIBLE','stocks':[self.s]};original=deepcopy(report)
        out=attach_report(report);self.assertEqual(report,original)
        out['stocks'][0].pop('enterprise_family_suitability');out.pop('enterprise_suitability_version');self.assertEqual(out,original)
    def test_no_ticker_rules(self):
        a=audit(self.s);self.s['ticker']='UNRELATED';self.assertEqual(a,audit(self.s))
    def test_no_calculation_or_io_imports(self):
        import inspect,enterprise_family_suitability as module
        source=inspect.getsource(module)
        for banned in ('import requests','import yfinance','import supabase','from valuation_engine','enterprise_experiment('):self.assertNotIn(banned,source)
    def test_no_secret_in_whitelisted_export(self):
        self.s['FINNHUB_API_KEY']='secret-test';self.s['tokens']='secret-test'
        self.assertNotIn('secret-test',json.dumps(audit_export({'stocks':[self.s]})))


    def test_unknown_class_no_candidate(self):
        self.s['live_blend']['profile']['valuation_class']='unknown_new_class'
        self.assertEqual(audit(self.s)['ev_ebitda']['production_candidate'],'NO')
    def test_missing_evidence_no_method_candidate(self):
        self.s.pop('enterprise_structural_metadata')
        self.assertEqual(audit(self.s)['ev_ebitda']['production_candidate'],'NO')
    def test_missing_class_range_blocks(self):
        self.s['profile_assumptions'].pop('ev_ebitda_range')
        self.assertEqual(audit(self.s)['ev_ebitda']['suitability'],'NOT_ELIGIBLE')
    def test_missing_cash_blocks(self):
        self.s['normalized_inputs'].pop('cash')
        self.assertEqual(audit(self.s)['ev_revenue']['suitability'],'NOT_ELIGIBLE')
    def test_nonmeaningful_ebitda_block(self):
        self.s['enterprise_structural_metadata']['ebitda_economically_meaningful']=False
        self.assertIn('ebitda_not_economically_meaningful',audit(self.s)['ev_ebitda']['hard_blocks'])
    def test_nonoperating_revenue_block(self):
        self.s['enterprise_structural_metadata']['non_operating_revenue']=True
        self.assertEqual(audit(self.s)['ev_revenue']['suitability'],'NOT_ELIGIBLE')
    def test_high_capex_conditional_revenue(self):
        self.s['normalized_inputs']['normalized_capex']=40
        a=audit(self.s);self.assertEqual(a['capital_intensity_assessment'],'VERY_HIGH')
        self.assertEqual(a['ev_revenue']['suitability'],'CONDITIONAL')
    def test_low_margin_conditional_revenue(self):
        self.s['normalized_inputs']['operating_margin']=.03
        self.assertEqual(audit(self.s)['ev_revenue']['suitability'],'CONDITIONAL')
    def test_sbc_ceiling(self):
        self.s['enterprise_structural_metadata']['sbc_distortion']=True
        self.assertEqual(audit(self.s)['ev_ebitda']['suitability'],'CONDITIONAL')
    def test_missing_method_not_candidate(self):
        self.s['enterprise_aware_experiment'].pop('ev_ebitda_model')
        self.assertEqual(audit(self.s)['ev_ebitda']['production_candidate'],'NO')
    def test_raw_v48_references_exact(self):
        a=audit(self.s)
        for key,value in a['v48_references'].items():self.assertEqual(value,self.s['enterprise_aware_experiment'].get(key))
    def test_production_fair_actual_path_not_scoring(self):
        a=audit(self.s);self.s['live_blend']['fair_value']=999999
        self.s['enterprise_aware_experiment'].update(production_fair=999999,difference_vs_earnings_pct=-99)
        b=audit(self.s)
        for m in ('ev_ebitda','ev_revenue','company_level'):self.assertEqual(a[m],b[m])
    def test_whole_captured_production_payload_unchanged(self):
        s=base_fixture();s['enterprise_aware_experiment']=enterprise_experiment(s)
        original=deepcopy(s);audit(s);self.assertEqual(s,original)
    def test_no_write_admin_batch_wiring(self):
        import sys
        from pathlib import Path
        from unittest.mock import patch
        with patch.object(sys,'path',[str(Path(__file__).parent)]+sys.path):
            from tests.test_v45_snapshot_export import SnapshotExportTests
        t=SnapshotExportTests();t.setUp()
        try:
            report=t.batch()
            self.assertEqual(len(report['stocks']),5)
            self.assertTrue(all('enterprise_family_suitability' in s for s in report['stocks']))
        finally:t.tearDown()

def hard_test(vclass=None,field=None,value=None,method='ev_ebitda'):
    def test(self):
        if vclass:self.s['live_blend']['profile']['valuation_class']=vclass
        if field:self.s['normalized_inputs'][field]=value
        self.assertEqual(audit(self.s)[method]['suitability'],'NOT_ELIGIBLE')
    return test
for name,kw in {
    'bank_ebitda':dict(vclass='bank'),'bank_revenue':dict(vclass='bank',method='ev_revenue'),
    'nonpositive_ebitda':dict(field='ebitda',value=0),'missing_ebitda':dict(field='ebitda'),
    'missing_revenue':dict(field='revenue',method='ev_revenue'),'negative_revenue':dict(field='revenue',value=-2,method='ev_revenue'),
    'currency_mismatch':dict(field='financial_currency',value='EUR'),'currency_missing':dict(field='quote_currency'),
    'shares_missing':dict(field='canonical_shares'),'specialized':dict(vclass='unsupported_specialized'),
    'crypto':dict(vclass='crypto_treasury'),'space':dict(vclass='space_optionality'),'auto':dict(vclass='auto_optionality'),
    'preprofit_negative_ebitda':dict(vclass='pre_profit_growth',field='ebitda',value=-1),
}.items():setattr(SuitabilityTests,'test_hard_'+name,hard_test(**kw))


def isolation_test(field):
    def test(self):
        before=deepcopy(self.s);audit(self.s);self.assertEqual(self.s,before)
        self.s[field]={'arbitrary':'changed'};a=audit(self.s);b=audit(before)
        for method in ('ev_ebitda','ev_revenue','company_level'):self.assertEqual(a[method],b[method])
    return test
for field in ('production_fair','current_price','benchmark','peer_comparable_result','last_reliable',
              'structural_governance','independent_evidence_governance','reliability','weights','outliers','buy_zones','exit_zones','provider_health'):
    setattr(SuitabilityTests,'test_isolated_'+field,isolation_test(field))

if __name__=='__main__':unittest.main()
