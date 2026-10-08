from copy import deepcopy
import json
import unittest
from unittest.mock import patch
import pandas as pd
import enterprise_evidence_closure as c
from test_enterprise_evidence import fixture, complete


def stock():
    s=complete(fixture());f=s['normalized_inputs']
    f['enterprise_metric_basis'].update(ebitda='TTM',revenue='TTM')
    for k in ('ebitda','revenue'):
        f['acquisition_provenance'][k]['period']='2024-12-31'
    s['analysis_generated_at']='2025-01-01T00:00:00Z'
    return s


def segments():
    return [{'label':'A','segment_type':'OPERATING_SEGMENT','revenue_share':.5,'operating_margin':.1,'growth':.1,'economic_model':'commerce','period':'2024-12-31','source':'reported operating segments'},
            {'label':'B','segment_type':'OPERATING_SEGMENT','revenue_share':.5,'operating_margin':.5,'growth':.6,'economic_model':'subscription','period':'2024-12-31','source':'reported operating segments'}]


class ClosureTests(unittest.TestCase):
    def setUp(self):self.s=stock()
    def basis(self):return c.metric_basis(self.s)
    def test_retrieval_not_reporting_date(self):
        p=self.s['normalized_inputs']['acquisition_provenance']['ebitda'];p.clear();p['acquired_at']='2025-01-01'
        self.s['normalized_inputs']['enterprise_metric_basis'].pop('ebitda')
        r=self.basis()['metrics']['ebitda'];self.assertIsNone(r['reporting_as_of']);self.assertIsNone(r['reporting_period'])
    def test_ttm(self):self.assertEqual(self.basis()['metrics']['ebitda']['metric_basis'],'TTM')
    def test_unspecified(self):
        self.s['normalized_inputs']['enterprise_metric_basis'].pop('ebitda')
        self.assertEqual(self.basis()['metrics']['ebitda']['metric_basis'],'PROVIDER_CURRENT_UNSPECIFIED')
    def test_dates_preserved(self):self.assertEqual(self.basis()['metrics']['cash']['reporting_as_of'],'2024-12-31')
    def test_cash_and_debt_crosscheck(self):
        for key in ('cash','debt'):
            r=self.basis()['metrics'][key];r['reporting_period']='2024-12-31'
            reference={'value':r['value'],'period':'2024-12-31','basis':'LATEST_BALANCE_SHEET','currency':'USD'}
            self.assertEqual(c.crosscheck(r,reference),'CONSISTENT')
            reference['value']=r['value']*2 if r['value'] else 5
            self.assertIn(c.crosscheck(r,reference),('MATERIAL_DIFFERENCE','INSUFFICIENT_EVIDENCE'))
    def test_current_vs_average(self):
        self.s['normalized_inputs']['canonical_shares_basis']='FY_DILUTED_AVG'
        self.assertEqual(self.basis()['metrics']['canonical_shares']['share_basis_semantics'],'FY_AVERAGE')
    def test_mixed_standard(self):self.assertEqual(self.basis()['enterprise_bridge_semantic_compatibility'],'MIXED_BUT_STANDARD')
    def test_currency_mismatch(self):
        self.s['normalized_inputs']['quote_currency']='EUR';self.assertEqual(self.basis()['enterprise_input_basis_compatibility'],'INCOMPATIBLE')
    def test_gap_boundaries(self):
        for days,expected in ((120,'GOOD'),(121,'ACCEPTABLE'),(270,'ACCEPTABLE'),(271,'STALE_RISK'),(550,'STALE_RISK'),(551,'INCOMPATIBLE')):
            self.assertEqual(c.timing(days),expected)
    def test_stale_date(self):
        self.s['analysis_generated_at']='2026-01-01';self.assertEqual(self.basis()['enterprise_bridge_timing_assessment'],'STALE_RISK')
    def test_no_value_replacement(self):
        original=deepcopy(self.s);self.basis();self.assertEqual(self.s,original)
    def test_near_fy_not_fy(self):
        f=self.s['normalized_inputs'];f['enterprise_metric_basis'].pop('ebitda')
        self.s['metric_basis_evidence_snapshot']={'ticker':'TEST','series':{'ebitda':[{'value':f['ebitda'],'period':'2024-12-31','basis':'FY','source':'statement.EBITDA'}]}}
        r=self.basis()['metrics']['ebitda'];self.assertEqual(r['metric_basis'],'CURRENT_PROVIDER_VALUE_NEAR_LATEST_FY');self.assertNotEqual(r['metric_basis'],'FY')
    def test_period_mismatch_not_numeric_comparison(self):
        r=self.basis()['metrics']['ebitda'];self.assertEqual(c.crosscheck(r,{'value':r['value'],'period':'2024-12-31','basis':'FY'}),'NOT_COMPARABLE')
    def test_ticker_name_not_evidence(self):
        for ticker in ('AMZN','GOOG','NVDA','MSFT','ORCL'):
            self.s['ticker']=ticker;self.s['company_name']='Cloud Subscription Commerce'
            self.assertEqual(c.business_structure(self.s)['business_mix'],'INSUFFICIENT_EVIDENCE')
    def test_geographic_excluded(self):
        self.s['operating_segments']=segments()
        for r in self.s['operating_segments']:r['segment_type']='GEOGRAPHIC_SEGMENT'
        b=c.business_structure(self.s);self.assertEqual(b['business_mix'],'INSUFFICIENT_EVIDENCE');self.assertEqual(len(b['excluded_segments']),2)
    def test_operating_accepted(self):
        self.s['operating_segments']=segments();b=c.business_structure(self.s)
        self.assertEqual(b['business_mix'],'HIGHLY_HETEROGENEOUS');self.assertEqual(b['material_segment_count'],2)
        self.assertAlmostEqual(b['margin_dispersion'],.4);self.assertAlmostEqual(b['growth_dispersion'],.5)
    def test_ten_percent_boundary(self):
        self.s['operating_segments']=segments();self.s['operating_segments'][0]['revenue_share']=.09;self.s['operating_segments'][1]['revenue_share']=.91
        self.assertEqual(c.business_structure(self.s)['material_segment_count'],1)
    def test_pending_cannot_score(self):
        self.s['governed_business_structure_metadata']={'ticker':'TEST','review_status':'PENDING_REVIEW','business_mix':'HIGHLY_HETEROGENEOUS'}
        self.assertEqual(c.build_v49_business_structure_adapter(c.business_structure(self.s)),{})
    def test_reviewed_requires_governance(self):
        self.s['governed_business_structure_metadata']={'ticker':'TEST','review_status':'REVIEWED','business_mix':'HIGHLY_HETEROGENEOUS'}
        self.assertEqual(c.business_structure(self.s)['metadata_review_status'],'PENDING_REVIEW')
    def test_conflicting_ticker(self):
        self.s['governed_business_structure_metadata']={'ticker':'OTHER','review_status':'REVIEWED'}
        self.assertEqual(c.business_structure(self.s)['metadata_review_status'],'CONFLICTING')
    def test_reviewed_adapter(self):
        self.s['operating_segments']=segments();a=c.build_v49_business_structure_adapter(c.business_structure(self.s));self.assertTrue(a['company_level_multiple_risk'])
    def test_unknown_basis_omitted(self):
        self.s['normalized_inputs']['enterprise_metric_basis']={};a=c.build_v49_metric_basis_adapter(self.basis());self.assertNotIn('enterprise_input_basis_compatible',a)
    def test_same_input_identity(self):
        result=c.close_stock(self.s,'ELIGIBLE');self.assertEqual(result['input_batch_id'],'batch');self.assertEqual(result['fundamentals_acquisition_id'],'acq')
    def test_cross_ticker_capture_ignored(self):
        self.s.pop('evidence_snapshot')
        self.s['metric_basis_evidence_snapshot']={'ticker':'OTHER','series':{'ebitda':[{'value':22,'period':'2024-12-31','basis':'FY'}]}}
        self.assertIsNone(self.basis()['metrics']['ebitda']['reference'])
    def test_stock_immutable(self):
        original=deepcopy(self.s);r=c.close_stock(self.s,'ELIGIBLE');self.assertEqual(self.s,original);self.assertTrue(r['production_invariants']['original_stock_unchanged'])
    def test_coverage_not_candidate(self):
        self.s['operating_segments']=segments();r=c.close_stock(self.s,'ELIGIBLE');self.assertEqual(r['v49_after']['production_candidate'],'NO');self.assertEqual(r['v49_after']['readiness'],'DIAGNOSTIC_ONLY')
    def test_coverage_gain_can_reduce_suitability(self):
        self.s['operating_segments']=segments();r=c.close_stock(self.s,'ELIGIBLE');self.assertGreaterEqual(r['coverage_delta'],0)
        self.assertEqual(r['v49_after']['company_level']['production_candidate'],'NO')
    def test_batch_export_and_immutability(self):
        report={'batch_id':'batch','batch_calibration_eligibility':'ELIGIBLE','stocks':[deepcopy(self.s) for _ in range(5)]};before=deepcopy(report)
        r=c.close_report(report);self.assertEqual(report,before);self.assertEqual(len(c.export_report(r)['stocks']),5);self.assertIn(b'Coverage After',c.export_csv(r))
    def test_no_secret_fields_exported(self):
        self.s['FINNHUB_API_KEY']='secret-marker';r=c.close_report({'stocks':[self.s]});self.assertNotIn('secret-marker',json.dumps(c.export_report(r)))
    def test_independent_evidence_ids(self):
        self.s['operating_segments']=segments();a=c.close_stock(self.s);b=c.close_stock(self.s)
        self.assertNotEqual(a['business_structure_closure']['business_structure_evidence_id'],b['business_structure_closure']['business_structure_evidence_id'])
        self.assertNotEqual(a['fundamentals_acquisition_id'],a['business_structure_closure']['business_structure_evidence_id'])
    def test_zero_calls(self):
        r=c.close_stock(self.s);self.assertEqual(r['telemetry']['added_provider_calls'],0);self.assertFalse(r['production_integration_performed'])
    def test_capture_existing_statement(self):
        frame=pd.DataFrame({'2024-12-31':[12]},index=['Total Debt'])
        with c.observe_basis('TEST') as observed:c.observe_statement('balance_sheet','ticker.balance_sheet',frame)
        self.assertEqual(observed['series']['debt'][0]['value'],12)
    def test_observer_does_not_request(self):
        with c.observe_basis('TEST') as observed:c.observe_statement('balance_sheet','test',None)
        self.assertEqual(observed['series'],{})
    def test_ineligible_identity_blocks(self):
        self.s['input_batch_id']='other';self.assertFalse(c.close_stock(self.s,'ELIGIBLE')['formal_conclusion_allowed'])
    def test_v50_required(self):
        self.s.pop('enterprise_structural_evidence');self.assertRaises(ValueError,c.close_stock,self.s)
    def test_four_homogeneous_not_very_high(self):
        self.s['operating_segments']=[{**segments()[0],'revenue_share':.25,'label':str(i)} for i in range(4)]
        self.assertEqual(c.business_structure(self.s)['segment_complexity'],'LOW')
    def test_reviewed_governed_metadata(self):
        self.s['governed_business_structure_metadata']={'ticker':'TEST','effective_date':'2024-12-31',
            'source_type':'INTERNAL_REVIEWED_NOTE','source_note':'Reviewed operating segment disclosure, note 2',
            'review_status':'REVIEWED','reviewed_by':'reviewer','confidence':'HIGH','business_models':['commerce','subscription'],
            'segment_complexity':'HIGH','heterogeneous_business_mix':True,'company_level_multiple_risk':True}
        self.assertTrue(c.build_v49_business_structure_adapter(c.business_structure(self.s))['heterogeneous_business_mix'])
        self.s['analysis_generated_at']='2027-01-01'
        self.assertEqual(c.business_structure(self.s)['metadata_review_status'],'STALE')
    def test_missing_assumed_zero_not_evidence(self):
        self.s['normalized_inputs']['acquisition_provenance']['cash']['source']='existing_missing_assumed_zero'
        self.s['normalized_inputs']['cash']=0
        self.assertIsNone(self.basis()['metrics']['cash']['value'])
        self.assertEqual(self.s['normalized_inputs']['cash'],0)
    def test_incomplete_segment_shares_not_supported(self):
        self.s['operating_segments']=[segments()[0]]
        self.assertEqual(c.business_structure(self.s)['source_status'],'INSUFFICIENT_EVIDENCE')
    def test_future_retrieval_never_changes_timing(self):
        before=self.basis()
        for p in self.s['normalized_inputs']['acquisition_provenance'].values():p['acquired_at']='2099-01-01'
        self.assertEqual(before['as_of_gap_days'],self.basis()['as_of_gap_days'])
    def test_reference_only_partial_closure_not_formal_compatibility(self):
        f=self.s['normalized_inputs'];f['enterprise_metric_basis']={}
        rows={}
        for key in ('ebitda','revenue','cash','debt'):
            f['acquisition_provenance'][key]={}
            rows[key]=[{'value':f[key],'period':'2024-12-31','basis':'FY' if key in ('ebitda','revenue') else 'LATEST_BALANCE_SHEET','source':'test.statement.'+key}]
        self.s['metric_basis_evidence_snapshot']={'ticker':'TEST','series':rows}
        b=self.basis();self.assertEqual(b['enterprise_input_basis_compatibility'],'MIXED_BASIS')
        self.assertEqual(b['enterprise_bridge_semantic_compatibility'],'MOSTLY_COMPATIBLE')
        self.assertNotIn('enterprise_input_basis_compatible',c.build_v49_metric_basis_adapter(b))
        self.assertIsNone(b['metrics']['cash']['reporting_as_of'])

if __name__=='__main__':unittest.main()
