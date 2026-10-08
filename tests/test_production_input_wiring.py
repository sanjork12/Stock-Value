from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
from pathlib import Path

import fundamental_acquisition as a
import production_snapshot_admin as admin
from production_input_wiring import snapshot_fundamentals,build_trace,summary
from mag7_monitor import get_live_fundamentals
from analysis_service import analyze_ticker
from test_quality_acquisition import Healthy,incomplete
import test_v45_snapshot_export as snapshot_tests
from scripts.verify_peer_isolation import history


class WiringTests(unittest.TestCase):
    def setUp(self):
        self.cache=a.RawAcquisitionCache()
        self.cache_patch=patch.object(a,'RAW_CACHE',self.cache);self.cache_patch.start();self.addCleanup(self.cache_patch.stop)
        self.factory=Mock(side_effect=lambda ticker:Healthy(ticker))
        self.yahoo=patch('mag7_monitor._yfinance',return_value=SimpleNamespace(Ticker=self.factory))
        self.yahoo.start();self.addCleanup(self.yahoo.stop)
        self.options=patch.object(a,'flags',return_value=a.Flags());self.options.start();self.addCleanup(self.options.stop)
    def capture(self):
        with a.acquisition_batch('test-batch',force_refresh=True):
            return admin.capture_analysis('NVDA',history_loader=history,fundamentals_loader=snapshot_fundamentals)
    def test_canonical_entrypoint(self):
        with patch('mag7_monitor.get_live_fundamentals',return_value={}) as load:
            snapshot_fundamentals('NVDA');load.assert_called_once_with('NVDA',force_refresh=True)
    def test_no_outer_normalized_cache_in_ui(self):
        source=Path('streamlit_app.py').read_text(encoding='utf-8')
        self.assertIn('fundamentals_loader=snapshot_fundamentals, display_resolver=v45_display_readonly',source)
    def test_disabled_canonical_does_not_silently_use_legacy(self):
        with patch.object(a,'flags',return_value=a.Flags(quality_cache=False)):
            with self.assertRaises(RuntimeError):snapshot_fundamentals('NVDA')
        self.factory.assert_not_called()
    def test_recovery_payload_is_downstream_payload(self):
        self.factory.side_effect=[Healthy('NVDA',incomplete()),Healthy('NVDA')]
        s=self.capture();trace=s['production_input_trace']
        self.assertTrue(trace['fresh_recovery_used']);self.assertEqual(trace['acquisition_health'],'HEALTHY')
        self.assertTrue(trace['accepted_recovery_payload_is_downstream_payload'])
        self.assertEqual(trace['forward_eps']['raw_source'],'yahoo.fresh_get_info.forwardEps')
        self.assertEqual(self.factory.call_count,2)
    def test_end_to_end_batch_identity(self):
        trace=self.capture()['production_input_trace'];self.assertEqual(trace['divergence'],'NONE')
        self.assertEqual({v['input_batch_id'] for v in trace['stage_identities'].values()},{'test-batch'})
        self.assertEqual(len({v['fundamentals_acquisition_id'] for v in trace['stage_identities'].values()}),1)
    def test_single_acquisition(self):
        with a.acquisition_batch('same',force_refresh=True):
            x=snapshot_fundamentals('NVDA');y=snapshot_fundamentals('NVDA')
        self.assertEqual(x,y);self.factory.assert_called_once_with('NVDA')
    def test_old_cache_cannot_supply_new_batch(self):
        with a.acquisition_batch('old'):x=snapshot_fundamentals('NVDA')
        with a.acquisition_batch('new'):y=snapshot_fundamentals('NVDA')
        self.assertNotEqual(x['fundamentals_acquisition_id'],y['fundamentals_acquisition_id'])
        self.assertEqual(y['input_batch_id'],'new');self.assertEqual(self.factory.call_count,2)
    def test_stale_identity_detected(self):
        s=self.capture();f=s['normalized_inputs'];old=deepcopy(f);old['fundamentals_acquisition_id']='old'
        trace=build_trace('NVDA',f,old,f,batch_id='test-batch')
        self.assertEqual(trace['divergence'],'BATCH_ACQUISITION_DIVERGENCE');self.assertEqual(trace['acceptance_status'],'FAIL')
    def test_stale_batch_detected(self):
        f=self.capture()['normalized_inputs']
        self.assertEqual(build_trace('NVDA',f,f,f,batch_id='other')['divergence'],'BATCH_ACQUISITION_DIVERGENCE')
    def test_unknown_identity_not_fabricated(self):
        self.assertEqual(build_trace('NVDA',{},{},{})['divergence'],'UNOBSERVED')
    def test_healthy_raw_but_lost_calibration_value_fails(self):
        f=self.capture()['normalized_inputs'];bad=deepcopy(f);bad['forward_eps']=None
        trace=build_trace('NVDA',f,f,bad)
        self.assertEqual(trace['acceptance_status'],'FAIL');self.assertIn('forward_eps',trace['value_divergent_fields'])
    def test_trace_no_raw_dict_or_credentials(self):
        raw=Healthy().raw;raw.update(token='PRIVATE',cookie='PRIVATE',FINNHUB_API_KEY='PRIVATE')
        self.factory.side_effect=lambda ticker:Healthy(ticker,raw)
        import json
        payload=json.dumps(self.capture()['production_input_trace'])
        self.assertNotIn('PRIVATE',payload);self.assertNotIn('token',payload)
    def test_healthy_fixed_inputs_valuation_identical(self):
        with a.acquisition_batch('fixed'):f=snapshot_fundamentals('NVDA')
        before=deepcopy(f)
        actual=admin.capture_analysis('NVDA',history_loader=history,fundamentals_loader=lambda t:f)
        with patch('analysis_service._attach_peer_diagnostics',side_effect=lambda r,*args,**kw:r):
            normal=analyze_ticker('NVDA',history_loader=history,fundamentals_loader=lambda t:f,peer_mode='diagnostic')
        self.assertEqual(actual['live_blend'],normal['blend']);self.assertEqual(actual['normalized_inputs'],normal['financials'])
        self.assertEqual(f,before)
    def test_new_run_new_batch_and_no_database_writes(self):
        t=snapshot_tests.SnapshotExportTests();t.setUp();t.client.table.side_effect=AssertionError('No writes/reads')
        try:
            first=admin.run_batch(t.client,'u',t.secrets,history_loader=history,fundamentals_loader=snapshot_fundamentals)
            admin._LAST_RUN.clear()
            second=admin.run_batch(t.client,'u',t.secrets,history_loader=history,fundamentals_loader=snapshot_fundamentals)
            self.assertNotEqual(first['batch_id'],second['batch_id'])
            self.assertEqual(self.factory.call_count,10)
            for s in second['stocks']:
                trace=s['production_input_trace'];self.assertEqual(trace['input_batch_id'],second['batch_id'])
                self.assertEqual(trace['divergence'],'NONE');self.assertEqual(trace['acceptance_status'],'PASS')
            t.client.table.assert_not_called()
        finally:t.tearDown()
    def test_button_clears_old_session_before_run(self):
        source=Path('production_snapshot_admin.py').read_text(encoding='utf-8')
        handler=source[source.index('    if run_v45 or run_v46:'):source.index('    saved=st.session_state')]
        self.assertLess(handler.index("pop('_v45_export_result'"),handler.index('report=run_batch'))
    def test_trace_summary_compact(self):
        row=summary(self.capture());self.assertEqual(row['valuation_forward_eps'],5)
        self.assertEqual(row['calibration_forward_eps'],5);self.assertLess(len(row),20)


def field_test(field,stage):
    def test(self):
        trace=self.capture()['production_input_trace'];expected=5 if field=='forward_eps' else 'USD'
        self.assertEqual(trace[field][stage],expected)
    return test
for field in ('forward_eps','quote_currency','financial_currency'):
    for stage in ('raw','normalized','valuation_input','calibration_input'):
        setattr(WiringTests,'test_field_'+field+'_'+stage,field_test(field,stage))

if __name__=='__main__':unittest.main()
