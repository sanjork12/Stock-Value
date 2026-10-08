from copy import deepcopy
import csv
import io
import json
import unittest
from unittest.mock import patch,Mock
import production_snapshot_admin as admin
from enterprise_aware_experiment import enterprise_summary,enterprise_experiment
from test_capital_structure_overlay import fixture


def old_batch():
    stocks=[]
    for ticker in admin.TICKERS:
        s=fixture();s['ticker']=ticker
        # Synthetic public test inputs only, never runtime Cloud placeholders.
        s.update(production_analysis_fair=s['blend']['fair'],capture_status='COMPLETE',
            batch_id='original-batch',batch_generated_at='original-time',models=[{'model_name':'forward_pe'}])
        stocks.append(s)
    return {'batch_id':'original-batch','batch_generated_at':'original-time','generated_at':'original-time','stocks':stocks}


class EnterpriseAdminWiringTests(unittest.TestCase):
    def test_reproduces_legacy_all_none_summary(self):
        for stock in old_batch()['stocks']:
            summary=enterprise_summary(stock)
            for key in ('production_fair','earnings_family_mid','enterprise_family_confidence',
                'enterprise_evidence_status','production_readiness'):
                self.assertIsNone(summary[key])

    def test_repairs_five_stock_legacy_batch(self):
        report=admin.prepare_enterprise_report(old_batch())
        self.assertEqual(len(report['enterprise_experiment_wiring']['repaired_tickers']),5)
        for stock in report['stocks']:
            e=stock['enterprise_aware_experiment']
            self.assertIsNotNone(e['production_fair'])
            self.assertIsNotNone(e['earnings_family_mid'])
            self.assertIsNotNone(e['enterprise_family_mid'])
            self.assertIsInstance(e['enterprise_evidence_status'],str)
            self.assertIsInstance(e['production_readiness'],str)

    def test_snapshot_inputs_and_ranges_wired(self):
        for stock in admin.prepare_enterprise_report(old_batch())['stocks']:
            e=stock['enterprise_aware_experiment'];f=stock['normalized_inputs']
            for key in ('cash','debt','ebitda','revenue','canonical_shares'):
                self.assertEqual(e['input_snapshot'][key],f[key])
            for key in ('ev_ebitda_range','sales_multiple_range'):
                self.assertEqual(tuple(e['input_snapshot'][key]),tuple(stock['profile_assumptions'][key]))
            self.assertEqual(e['wiring']['batch_id'],'original-batch')
            self.assertEqual(e['wiring']['financials_path'],'normalized_inputs')

    def test_null_empty_and_placeholder_repaired(self):
        for placeholder in (None,{}, {'production_fair':None,'enterprise_family_confidence':None}):
            report=old_batch();report['stocks'][0]['enterprise_aware_experiment']=placeholder
            e=admin.prepare_enterprise_report(report)['stocks'][0]['enterprise_aware_experiment']
            self.assertIsNotNone(e['production_fair'])
            self.assertNotEqual(e['enterprise_evidence_status'],None)

    def test_complete_results_not_recomputed(self):
        report=old_batch()
        for stock in report['stocks']:stock['enterprise_aware_experiment']=enterprise_experiment(stock)
        before=deepcopy(report)
        with patch.object(admin,'enterprise_experiment',side_effect=AssertionError('No recompute')):
            out=admin.prepare_enterprise_report(report)
        for old,new in zip(before['stocks'],out['stocks']):
            for key,value in old['enterprise_aware_experiment'].items():self.assertEqual(new['enterprise_aware_experiment'][key],value)

    def test_no_fetch_no_write_no_production_mutation(self):
        report=old_batch();before=deepcopy(report)
        with (patch.object(admin,'capture_analysis',side_effect=AssertionError('No fetch')),
              patch.object(admin.analysis_service,'analyze_ticker',side_effect=AssertionError('No production rerun'))):
            out=admin.prepare_enterprise_report(report)
        self.assertEqual(report,before)
        for original,prepared in zip(before['stocks'],out['stocks']):
            prepared.pop('enterprise_aware_experiment')
            self.assertEqual(original,prepared)
        self.assertEqual(out['generated_at'],before['generated_at'])
        self.assertFalse(out['enterprise_experiment_wiring']['input_fetch_performed'])

    def test_missing_ebitda_only_blocks_one_method(self):
        report=old_batch();report['stocks'][0]['normalized_inputs']['ebitda']=None
        e=admin.prepare_enterprise_report(report)['stocks'][0]['enterprise_aware_experiment']
        self.assertFalse(e['ev_ebitda_model']['valid'])
        self.assertTrue(e['ev_revenue_model']['valid'])
        self.assertIsNotNone(e['production_fair'])
        self.assertIsNotNone(e['enterprise_family_mid'])
        self.assertEqual(e['enterprise_family_confidence'],'LOW')

    def test_totally_missing_data_has_status_not_blank_placeholder(self):
        report={'stocks':[{'ticker':'EMPTY'}]}
        e=admin.prepare_enterprise_report(report)['stocks'][0]['enterprise_aware_experiment']
        self.assertEqual(e['enterprise_evidence_status'],'UNAVAILABLE')
        self.assertEqual(e['production_readiness'],'NOT_READY')
        self.assertTrue(e['applicability']['model_reasons']['ev_ebitda'])

    def test_ui_json_csv_same_namespace(self):
        raw=old_batch();prepared=admin.prepare_enterprise_report(raw)
        exported=json.loads(admin.snapshot_json(prepared))
        rows=list(csv.DictReader(io.StringIO(admin.csv_payload(raw).decode('utf-8-sig'))))
        for stock,row,j in zip(prepared['stocks'],rows,exported['stocks']):
            summary=enterprise_summary(stock)
            self.assertEqual(float(row['enterprise_aware_experiment.production_fair']),summary['production_fair'])
            self.assertEqual(float(row['enterprise_aware_experiment.enterprise_family_mid']),summary['enterprise_family_mid'])
            self.assertEqual(j['enterprise_aware_experiment']['production_readiness'],summary['production_readiness'])

    def test_fresh_batch_calls_experiment_after_snapshot_ready(self):
        import test_v45_snapshot_export as fixtures
        helper=fixtures.SnapshotExportTests();helper.setUp()
        seen=[];original=admin.enterprise_experiment
        def observer(stock):
            self.assertIn('live_blend',stock)
            self.assertIn('normalized_inputs',stock)
            self.assertIn('profile_assumptions',stock)
            self.assertEqual(stock['capture_status'],'COMPLETE')
            seen.append(stock['ticker'])
            return original(stock)
        try:
            helper.client.table.side_effect=AssertionError('No database access')
            with patch.object(admin,'enterprise_experiment',side_effect=observer):report=helper.batch()
            self.assertEqual(seen,list(admin.TICKERS))
            for stock in report['stocks']:
                e=stock['enterprise_aware_experiment']
                self.assertEqual(e['production_fair'],stock['production_analysis_fair'])
                self.assertEqual(e['input_snapshot']['canonical_shares'],stock['normalized_inputs'].get('canonical_shares'))
            helper.client.table.assert_not_called()
        finally:helper.doCleanups()
