from copy import deepcopy
from datetime import datetime,timezone
import json
import unittest
from unittest.mock import patch
import pandas as pd
import reporting_basis_resolution as r
import enterprise_evidence_closure as c
from test_enterprise_evidence_closure import stock as base_stock


def epoch(day):return datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp()

def quarters(value,metric='revenue'):
    return [{'value':value/4,'period_end':day,'frequency':'QUARTERLY','currency':'USD',
        'accounting_semantics':'Total Revenue' if metric=='revenue' else 'EBITDA','source':'test.quarterly_income_stmt.'+metric}
        for day in ('2024-06-30','2024-09-30','2024-12-31','2025-03-31')]

def fixture():
    s=base_stock();f=s['normalized_inputs'];f['enterprise_metric_basis']={};f['acquisition_metadata']={'acquired_at':'2025-04-01T12:00:00+00:00'}
    s['enterprise_evidence_closure']=c.close_stock(s,'ELIGIBLE')
    s['enterprise_evidence_closure']['coverage_component_delta']['metric_basis']['after']=0
    s['enterprise_evidence_closure']['coverage_after']=67.5
    series={}
    for key in ('ebitda','revenue'):
        series[key]=quarters(f[key],key)+[{'value':f[key]*.7,'period_end':'2024-12-31','frequency':'ANNUAL','currency':'USD',
            'accounting_semantics':'EBITDA' if key=='ebitda' else 'Total Revenue','source':'test.annual.'+key}]
    for key in ('cash','debt'):
        series[key]=[{'value':f[key],'period_end':'2025-03-31','frequency':'QUARTERLY','currency':'USD',
            'accounting_semantics':'Total Debt' if key=='debt' else 'Cash Cash Equivalents And Short Term Investments','source':'test.balance_sheet.'+key}]
    series['shares']=[{'value':f['canonical_shares'],'period_end':'2024-12-31','frequency':'ANNUAL','currency':'USD','accounting_semantics':'Diluted Average Shares','source':'test.annual.shares'}]
    f['canonical_shares_source']='impliedSharesOutstanding'
    s['reporting_basis_evidence_snapshot']={'ticker':'TEST','input_batch_id':'batch','fundamentals_acquisition_id':'acq',
        'retrieved_at':'2025-04-01T12:00:00+00:00','provider_fields':{'lastFiscalYearEnd':epoch('2024-12-31'),'mostRecentQuarter':epoch('2025-03-31')},
        'series':series,'observed_statement_paths':['ticker.quarterly_income_stmt','ticker.quarterly_balance_sheet']}
    return s

class ReportingTests(unittest.TestCase):
    def setUp(self):self.s=fixture()
    def resolve(self):return r.resolve_stock(self.s,'ELIGIBLE')
    def flow(self,key='revenue'):
        snap=r.evidence_view(self.s);return r.flow_resolution(key,self.s,snap,r.reporting_metadata(snap))
    def test_fiscal_epoch(self):self.assertEqual(r.epoch_date(epoch('2024-12-31')),'2024-12-31')
    def test_quarter_epoch(self):self.assertEqual(self.resolve()['provider_reporting_metadata']['provider_most_recent_quarter'],'2025-03-31')
    def test_retrieval_not_reporting(self):
        self.s['reporting_basis_evidence_snapshot']['provider_fields']={}
        self.assertIsNone(self.resolve()['provider_reporting_metadata']['provider_last_fiscal_year_end'])
    def test_missing_metadata(self):self.assertEqual(r.reporting_metadata({})['reporting_metadata_confidence'],'INSUFFICIENT')
    def test_invalid_epochs(self):
        for x in (None,-1,True,float('nan'),float('inf'),1e30,'invalid'):
            self.assertIsNone(r.epoch_date(x))
    def test_revenue_ttm(self):self.assertEqual(r.reconstruct_ttm(quarters(100))['value'],100)
    def test_ebitda_ttm(self):self.assertEqual(r.reconstruct_ttm(quarters(20,'ebitda'))['value'],20)
    def test_incomplete_quarters(self):self.assertIsNone(r.reconstruct_ttm(quarters(100)[:3])['value'])
    def test_duplicate_quarters(self):
        q=quarters(100);q.append(deepcopy(q[-1]));self.assertIn('DUPLICATE_QUARTER',r.reconstruct_ttm(q)['reason_codes'])
    def test_mixed_currency(self):
        q=quarters(100);q[0]['currency']='EUR';self.assertIsNone(r.reconstruct_ttm(q)['value'])
    def test_mixed_semantics(self):
        q=quarters(100);q[0]['accounting_semantics']='Adjusted Revenue';self.assertIsNone(r.reconstruct_ttm(q)['value'])
    def test_nonconsecutive(self):
        q=quarters(100);q[0]['period_end']='2023-01-01';self.assertIsNone(r.reconstruct_ttm(q)['value'])
    def test_strong_match_boundary(self):self.assertEqual(r.comparison(105,100,'TTM')['support'],'STRONG_TTM_MATCH')
    def test_moderate_match_boundary(self):self.assertEqual(r.comparison(110,100,'TTM')['support'],'MODERATE_TTM_MATCH')
    def test_no_match(self):self.assertEqual(r.comparison(111,100,'TTM')['support'],'NO_TTM_MATCH')
    def test_unique_ttm_high(self):self.assertEqual(self.flow()['selected_basis'],'TTM');self.assertEqual(self.flow()['confidence'],'HIGH')
    def test_fy_match_alone_insufficient(self):
        snap=self.s['reporting_basis_evidence_snapshot'];snap['provider_fields']={}
        snap['series']['revenue']=[{**snap['series']['revenue'][-1],'value':self.s['normalized_inputs']['revenue']}]
        self.assertEqual(self.flow()['selected_basis'],'CURRENT_PROVIDER_UNSPECIFIED')
    def test_metadata_supported_fy(self):
        snap=self.s['reporting_basis_evidence_snapshot'];snap['provider_fields']['mostRecentQuarter']=epoch('2024-12-31')
        snap['series']['revenue']=[{**snap['series']['revenue'][-1],'value':self.s['normalized_inputs']['revenue']}]
        self.assertEqual(self.flow()['selected_basis'],'LATEST_FY');self.assertEqual(self.flow()['confidence'],'MEDIUM')
    def test_ttm_fy_ambiguity(self):
        self.s['reporting_basis_evidence_snapshot']['series']['revenue'][-1]['value']=self.s['normalized_inputs']['revenue']
        self.assertEqual(self.flow()['selected_basis'],'AMBIGUOUS_TTM_VS_FY');self.assertIsNone(self.flow()['resolved_period_end'])
    def test_mismatch_unresolved(self):
        self.s['normalized_inputs']['revenue']*=2
        self.assertEqual(self.flow()['selected_basis'],'CURRENT_PROVIDER_UNSPECIFIED')
    def test_cash_near_compatible(self):
        x=self.resolve()['cash_resolution'];self.assertEqual(x['selected_basis'],'CURRENT_PROVIDER_CROSSVALIDATED_TO_LATEST_BS');self.assertIsNone(x['resolved_as_of'])
    def test_debt_near(self):self.assertEqual(self.resolve()['debt_resolution']['resolution_state'],'CURRENT_PROVIDER_NEAR_LATEST_BALANCE_SHEET')
    def test_debt_material_difference(self):
        self.s['normalized_inputs']['debt']*=2;x=self.resolve()['debt_resolution']
        self.assertEqual(x['resolution_state'],'CURRENT_PROVIDER_MATERIAL_DIFFERENCE');self.assertIsNone(x['resolved_as_of'])
    def test_cash_semantic_conflict(self):
        self.s['reporting_basis_evidence_snapshot']['series']['cash'][0]['accounting_semantics']='Cash And Cash Equivalents'
        self.assertEqual(self.resolve()['cash_resolution']['resolution_state'],'SEMANTICALLY_NOT_COMPARABLE')
    def test_current_vs_average_expected(self):self.assertEqual(self.resolve()['shares_resolution']['metric_basis_crosscheck'],'EXPECTED_DIFFERENT_BASIS')
    def test_implied_share_snapshot(self):
        s=self.resolve()['shares_resolution'];self.assertEqual(s['selected_basis'],'CURRENT_MARKET_IMPLIED')
        self.assertEqual(s['basis_as_of_type'],'ACQUISITION_TIME_MARKET_SNAPSHOT');self.assertIsNone(s['reporting_period'])
    def test_ttm_stock_standard(self):self.assertEqual(self.resolve()['enterprise_bridge_resolution']['enterprise_bridge_semantic_compatibility'],'MIXED_BUT_STANDARD')
    def test_fy_same_date_compatible(self):
        f=self.s['normalized_inputs'];f['enterprise_metric_basis']={'revenue':'FY','ebitda':'FY'}
        for key in ('ebitda','revenue'):f['acquisition_provenance'][key]['period']='2025-03-31'
        for key in ('cash','debt'):f['acquisition_provenance'][key]['source']=self.s['reporting_basis_evidence_snapshot']['series'][key][0]['source']
        self.assertEqual(self.resolve()['enterprise_bridge_resolution']['enterprise_bridge_semantic_compatibility'],'COMPATIBLE')
    def test_stale_balance_sheet(self):
        self.s['reporting_basis_evidence_snapshot']['series']['debt'][0]['period_end']='2023-01-01'
        self.assertEqual(self.resolve()['enterprise_bridge_resolution']['enterprise_bridge_timing_assessment'],'INCOMPATIBLE')
    def test_currency_unsafe(self):
        self.s['normalized_inputs']['quote_currency']='EUR';self.assertEqual(self.resolve()['enterprise_bridge_resolution']['enterprise_input_basis_compatibility'],'INCOMPATIBLE')
    def test_method_independence(self):
        self.s['reporting_basis_evidence_snapshot']['series']['ebitda']=[];self.s.pop('evidence_snapshot')
        b=self.resolve()['enterprise_bridge_resolution'];self.assertEqual(b['ev_ebitda_basis_compatibility'],'INSUFFICIENT_EVIDENCE')
        self.assertEqual(b['ev_revenue_basis_compatibility'],'MOSTLY_COMPATIBLE')
    def test_values_no_substitution(self):
        before=deepcopy(self.s);self.resolve();self.assertEqual(self.s,before)
    def test_no_benchmark_leakage(self):
        one=self.resolve();self.s.update(current_price=1e9,fair_value=-1,benchmark=1)
        two=self.resolve();self.assertEqual(one['revenue_resolution'],two['revenue_resolution']);self.assertEqual(one['enterprise_bridge_resolution'],two['enterprise_bridge_resolution'])
    def test_no_ticker_rule(self):
        first=self.resolve()['revenue_resolution'];self.s['ticker']='AMZN';self.s['reporting_basis_evidence_snapshot']['ticker']='AMZN';self.s['evidence_snapshot']['ticker']='AMZN'
        self.assertEqual(first,self.resolve()['revenue_resolution'])
    def test_coverage_not_yes(self):
        x=self.resolve();self.assertGreater(x['coverage_after'],x['coverage_before']);self.assertEqual(x['v49_after']['production_candidate'],'NO')
    def test_partial_coverage(self):
        self.s['reporting_basis_evidence_snapshot']['series']['ebitda']=[];self.s.pop('evidence_snapshot')
        self.assertEqual(self.resolve()['metric_basis_component_after'],5)
    def test_identity_preserved(self):
        x=self.resolve();self.assertEqual(x['input_batch_id'],'batch');self.assertEqual(x['fundamentals_acquisition_id'],'acq')
    def test_wrong_ticker_evidence_rejected(self):
        self.s['reporting_basis_evidence_snapshot']['ticker']='OTHER';self.s.pop('evidence_snapshot')
        self.assertEqual(self.flow()['selected_basis'],'CURRENT_PROVIDER_UNSPECIFIED')
    def test_wrong_batch_evidence_rejected(self):
        self.s['reporting_basis_evidence_snapshot']['input_batch_id']='OTHER';self.s.pop('evidence_snapshot')
        self.assertEqual(self.flow()['selected_basis'],'CURRENT_PROVIDER_UNSPECIFIED')
    def test_historical_id_separate(self):self.assertNotEqual(self.resolve()['historical_evidence_acquisition_id'],'acq')
    def test_zero_provider_calls(self):self.assertEqual(self.resolve()['telemetry']['added_provider_calls'],0)
    def test_registry_not_ttm(self):
        self.assertEqual(r.registry()['revenue']['period_semantics'],'UNKNOWN_UNLESS_PROVEN')
    def test_observer_whitelist(self):
        with r.observe_reporting('TEST') as o:r.observe_provider('ticker.get_info',{'lastFiscalYearEnd':epoch('2024-12-31'),'API_KEY':'PRIVATE','cookie':'PRIVATE'})
        self.assertNotIn('PRIVATE',json.dumps(o));self.assertEqual(o['provider_fields']['lastFiscalYearEnd'],epoch('2024-12-31'))
    def test_already_loaded_quarter_observation(self):
        frame=pd.DataFrame({'2025-03-31':[10]},index=['Total Revenue'])
        with r.observe_reporting('TEST') as o:r.observe_statement('income_stmt','ticker.quarterly_income_stmt',frame)
        self.assertEqual(o['series']['revenue'][0]['frequency'],'QUARTERLY')
    def test_unloaded_quarter_audit(self):
        a=r.reporting_metadata({})['quarterly_statement_availability'];self.assertTrue(all(v=='QUARTERLY_DATA_NOT_ALREADY_AVAILABLE' for v in a.values()))
    def test_new_namespace_only(self):
        report={'batch_id':'batch','batch_calibration_eligibility':'ELIGIBLE','stocks':[self.s]};before=deepcopy(report);out=r.resolve_report(report)
        self.assertEqual(report,before);out['stocks'][0].pop('reporting_basis_resolution');out.pop('reporting_basis_resolution_version');self.assertEqual(out,report)
    def test_five_stock_exports(self):
        report={'batch_id':'batch','batch_calibration_eligibility':'ELIGIBLE','stocks':[deepcopy(self.s) for _ in range(5)]};out=r.resolve_report(report)
        self.assertEqual(len(r.export_report(out)['stocks']),5);self.assertIn(b'EV/Revenue Basis Fit',r.export_csv(out))
    def test_metric_adapter_no_generic_flag(self):
        x=self.resolve()['v49_reporting_basis_adapter'];self.assertNotIn('enterprise_input_basis_compatible',x);self.assertTrue(x['ev_revenue_basis_compatible'])
    def test_missing_period_no_explicit_ttm_resolution(self):
        self.s['normalized_inputs']['enterprise_metric_basis']['revenue']='TTM';self.s['normalized_inputs']['acquisition_provenance']['revenue']={}
        self.s['reporting_basis_evidence_snapshot']['series']['revenue']=[];self.s.pop('evidence_snapshot')
        self.assertEqual(self.flow()['selected_basis'],'CURRENT_PROVIDER_UNSPECIFIED')
    def test_business_structure_unchanged(self):
        before=deepcopy(self.s['enterprise_evidence_closure']['business_structure_closure']);self.resolve()
        self.assertEqual(before,self.s['enterprise_evidence_closure']['business_structure_closure'])
    def test_ineligible_no_formal_conclusion(self):self.assertFalse(r.resolve_stock(self.s,'INELIGIBLE')['formal_conclusion_allowed'])
    def test_v51_required(self):
        self.s.pop('enterprise_evidence_closure');self.assertRaises(ValueError,r.resolve_stock,self.s)
    def test_unknown_currency_blocks_reconstruction(self):
        q=quarters(100);q[0]['currency']=None;self.assertIsNone(r.reconstruct_ttm(q)['value'])
    def test_missing_quarter_source(self):
        q=quarters(100);q[0]['source']=None;self.assertIsNone(r.reconstruct_ttm(q)['value'])
    def test_duplicate_fy_reference_unresolved(self):
        snap=self.s['reporting_basis_evidence_snapshot'];fy=snap['series']['revenue'][-1]
        snap['series']['revenue']=[fy,{**fy,'value':fy['value']*2}]
        self.assertEqual(self.flow()['selected_basis'],'CURRENT_PROVIDER_UNSPECIFIED')
    def test_duplicate_bs_reference_conflict(self):
        rows=self.s['reporting_basis_evidence_snapshot']['series']['debt'];rows.append({**rows[0],'value':rows[0]['value']*2})
        self.assertIn('CONFLICTING_LATEST_BALANCE_SHEET_REFERENCES',self.resolve()['debt_resolution']['unresolved_reasons'])
    def test_direct_fy_source_identity(self):
        row=self.s['reporting_basis_evidence_snapshot']['series']['revenue'][-1];row['value']=self.s['normalized_inputs']['revenue']
        self.s['normalized_inputs']['acquisition_provenance']['revenue']['source']=row['source']
        self.assertEqual(self.flow()['selected_basis'],'LATEST_FY');self.assertEqual(self.flow()['confidence'],'HIGH')
    def test_metadata_export_whitelist(self):
        self.s['reporting_basis_evidence_snapshot']['provider_fields']['API_KEY']='PRIVATE'
        self.assertNotIn('PRIVATE',json.dumps(self.resolve()))
    def test_missing_share_time_stays_unknown(self):
        self.s['reporting_basis_evidence_snapshot'].pop('retrieved_at');self.s['normalized_inputs']['acquisition_metadata']={}
        s=self.resolve()['shares_resolution'];self.assertIsNone(s['basis_as_of']);self.assertIsNone(s['reporting_period'])
    def test_ttm_period_start_from_explicit_source(self):
        q=quarters(100);q[0]['period_start']='2024-04-01'
        self.assertEqual(r.reconstruct_ttm(q)['period_start'],'2024-04-01')

if __name__=='__main__':unittest.main()
