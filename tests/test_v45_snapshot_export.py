from copy import deepcopy
from types import SimpleNamespace
import json
import unittest
from unittest.mock import Mock,patch

import production_snapshot_admin as admin
from analysis_service import analyze_ticker
from scripts.verify_peer_isolation import history,internal_snapshot
from test_peer_diagnostic_isolation import FINANCIALS
from valuation_calibration_audit import audit_analysis,sensitivity
from scripts.audit_valuation_classes import build_audit


class SnapshotExportTests(unittest.TestCase):
    def setUp(self):
        admin._LAST_RUN.clear()
        self.client=Mock()
        self.client.auth.get_user.return_value=SimpleNamespace(user=SimpleNamespace(id='u',email='admin@test.com'))
        self.secrets={'ADMIN_EMAIL':'admin@test.com','FINNHUB_API_KEY':'private-finnhub-value',
                      'supabase':{'key':'private-supabase-value'}}
        self.financials=deepcopy(FINANCIALS)
        self.cloud=patch.object(admin,'is_cloud_runtime',return_value=True)
        self.cloud.start();self.addCleanup(self.cloud.stop)

    def capture(self,ticker='GOOG',**kwargs):
        return admin.capture_analysis(ticker,history_loader=history,
            fundamentals_loader=lambda t:self.financials[t],**kwargs)

    def batch(self):
        return admin.run_batch(self.client,'u',self.secrets,history_loader=history,
            fundamentals_loader=lambda t:self.financials[t])

    def test_admin_and_cloud_required(self):
        self.client.auth.get_user.return_value.user.email='ordinary@test.com'
        with self.assertRaises(PermissionError):self.batch()
        self.client.auth.get_user.return_value.user.email='admin@test.com'
        with patch.object(admin,'is_cloud_runtime',return_value=False):
            with self.assertRaises(PermissionError):self.batch()

    def test_same_production_financials_and_valuation(self):
        before=deepcopy(self.financials)
        with patch('analysis_service._attach_peer_diagnostics',side_effect=lambda r,*a,**k:r):
            production=analyze_ticker('GOOG',history_loader=history,
                fundamentals_loader=lambda t:self.financials[t],peer_mode='diagnostic')
        captured=self.capture()
        self.assertEqual(captured['normalized_inputs'],production['financials'])
        for key,value in production['financials'].items():self.assertEqual(captured['financials'][key],value)
        self.assertEqual(captured['fair_value'],production['fair_value'])
        self.assertEqual(captured['live_blend'],production['blend'])
        self.assertEqual(self.financials,before)
        self.assertFalse(captured['peer_in_blend'])

    def test_models_and_outlier_capture_complete(self):
        captured=self.capture()
        self.assertEqual(set(captured['blend']['models']),set(captured['live_blend']['models']))
        self.assertEqual(set(captured['models_before_outlier']),set(captured['models_after_outlier']))
        for model in captured['models']:
            for field in ('base_weight','normalized_weight','contribution_to_blended_mid','inputs_used','assumptions_used','growth_provenance','capital_structure'):
                self.assertIn(field,model)
        self.assertTrue(captured['blend']['contribution_sum_matches'])

    def test_five_stock_single_batch_and_no_writes(self):
        self.client.table.side_effect=AssertionError('Database access prohibited')
        with patch('analysis_service.fetch_historical_snapshot',side_effect=AssertionError('No snapshots')):
            report=self.batch()
        self.assertEqual([s['ticker'] for s in report['stocks']],list(admin.TICKERS))
        self.assertTrue(all(s['capture_status']=='COMPLETE' for s in report['stocks']))
        self.assertEqual(len({s['batch_id'] for s in report['stocks']}),1)
        self.assertTrue(all(s['analysis_generated_at'] for s in report['stocks']))
        self.client.table.assert_not_called()

    def test_secret_keys_and_values_redacted(self):
        self.financials['GOOG'].update(api_key='private-finnhub-value',cookie='private-cookie',
                                     warnings=['private-supabase-value'])
        report=self.batch();payload=json.dumps(report)
        for secret in ('private-finnhub-value','private-supabase-value','private-cookie'):
            self.assertNotIn(secret,payload)
            self.assertNotIn(secret,admin.csv_payload(report).decode('utf-8-sig'))
        self.assertNotIn('api_key',report['stocks'][0]['financials'])

    def test_snapshot_capture_does_not_resolve_last_reliable_on_its_own(self):
        with patch('last_reliable_valuation.resolve_live_result',side_effect=AssertionError('No fallback writes')):
            captured=self.capture()
        self.assertEqual(captured['source_status'],'live')

    def test_readonly_display_never_changes_snapshot_or_calculated_at(self):
        snapshot={'raw':{'last_reliable':{'calculated_at':'original-time','source_status':'live'}}}
        before=deepcopy(snapshot)
        captured=self.capture()
        live={'ticker':'GOOG','fair_value':None,'valuation_mode':'UNAVAILABLE','financials':captured['normalized_inputs']}
        admin.readonly_display(live,lambda:snapshot)
        self.assertEqual(snapshot,before)
        self.assertNotIn('source_status',live)

    def test_contributions_sum(self):
        for ticker in admin.TICKERS:
            captured=self.capture(ticker)
            fair=captured['blend']['mid']
            if fair is not None:
                self.assertAlmostEqual(sum(m['contribution_to_blended_mid'] for m in captured['models']),fair)

    def test_audit_replays_exported_capture(self):
        captured=self.capture()
        before=deepcopy(captured)
        audit=audit_analysis('GOOG',captured)
        self.assertEqual(audit['status'],'CAPTURE_REPLAY_MATCH')
        self.assertTrue(audit['waterfall_matches'])
        self.assertEqual(captured,before)

    def test_sensitivity_is_side_effect_free(self):
        captured=self.capture();before=deepcopy(captured)
        specs=deepcopy(admin.engine.CLASS_SPECS);runners=dict(admin.engine.MODEL_RUNNERS)
        audit_analysis('GOOG',captured)
        self.assertEqual(captured,before)
        self.assertEqual(admin.engine.CLASS_SPECS,specs)
        self.assertEqual(admin.engine.MODEL_RUNNERS,runners)

    def test_benchmark_never_changes_audit(self):
        captured=self.capture()
        a=build_audit({'GOOG':captured},benchmarks={})
        b=build_audit({'GOOG':captured},benchmarks={'GOOG':999999})
        self.assertEqual(a['stocks'],b['stocks'])

    def test_cached_display_inputs_cannot_be_calibrated_as_live(self):
        captured=self.capture();captured['source_status']='cached_last_reliable'
        self.assertEqual(audit_analysis('GOOG',captured)['status'],'NEEDS_ORIGINAL_RELIABLE_INPUTS')


if __name__=='__main__':unittest.main()
