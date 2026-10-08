from copy import deepcopy
from types import SimpleNamespace
import json
import unittest
from unittest.mock import Mock, patch

import peer_diagnostic_admin as admin
from test_peer_review_report import PublicFixture, FIN


class PeerAdminTests(unittest.TestCase):
    def setUp(self):
        admin._LAST_RUN.clear()
        self.cloud=patch.object(admin,'is_cloud_runtime',return_value=True)
        self.cloud.start()
        self.addCleanup(self.cloud.stop)
        self.client=Mock()
        self.client.auth.get_user.return_value=SimpleNamespace(user=SimpleNamespace(id='u',email='admin@test.com'))
        self.secrets={'ADMIN_EMAIL':'admin@test.com','FINNHUB_API_KEY':'secret-private-key-123'}
        self.baseline={'fair_value':290.44,'financials':deepcopy(FIN),
                       'blend':{'blended_low':250,'blended_high':320},'confidence':'MEDIUM'}

    def run_report(self,tickers=None,provider=None,loader=None):
        return admin.run_cloud_peer_diagnostic(self.client,'u',self.secrets,tickers or admin.TICKERS,
            provider=provider or PublicFixture(),internal_loader=loader or (lambda _:self.baseline))

    def test_admin_and_cloud_required_before_requests(self):
        loader=Mock()
        self.client.auth.get_user.return_value.user.email='ordinary@test.com'
        with self.assertRaises(PermissionError):self.run_report(loader=loader)
        loader.assert_not_called()
        self.client.auth.get_user.return_value.user.email='admin@test.com'
        with patch.object(admin,'is_cloud_runtime',return_value=False):
            with self.assertRaises(PermissionError):self.run_report(loader=loader)
        loader.assert_not_called()

    def test_batch_and_downloads_are_public_only(self):
        provider=PublicFixture()
        original=deepcopy(self.baseline)
        report=self.run_report(provider=provider)
        self.assertEqual([r['ticker'] for r in report['comparison']],list(admin.TICKERS))
        self.assertEqual(report['mode'],'diagnostic')
        self.assertEqual(self.baseline,original)
        self.assertTrue(all(r['current_internal_fair']==290.44 for r in report['comparison']))
        self.assertEqual(set(p for p,_ in provider.calls),{'stock/profile2','stock/metric'})
        payload,csv=admin.download_payloads(report)
        self.assertEqual(len(json.loads(payload)['comparison']),5)
        for data in (payload.decode('utf-8'),csv.decode('utf-8-sig')):
            self.assertNotIn(self.secrets['FINNHUB_API_KEY'],data)
            self.assertNotIn('fixture-private-text',data)
        self.assertIn('Internal vs Benchmark %',csv.decode('utf-8-sig'))

    def test_benchmark_cannot_change_peer_calculation(self):
        first=self.run_report()
        admin._LAST_RUN.clear()
        with patch.object(admin,'BENCHMARKS',{t:999999 for t in admin.TICKERS}):second=self.run_report()
        for a,b in zip(first['peer_results'],second['peer_results']):
            for key in ('valid','low','mid','high','peers_included','selected_multiple','peer_median'):
                self.assertEqual(a[key],b[key])

    def test_less_than_three_peers_cannot_emit_price(self):
        p=PublicFixture();original=p.get_basic_financials
        p.get_basic_financials=lambda t:({'status':'NO_DATA','data':{}} if t=='MRVL' else original(t))
        report=self.run_report(['NVDA'],p)
        self.assertFalse(report['peer_results'][0]['valid'])
        self.assertIsNone(report['comparison'][0]['peer_mid'])

    def test_alphabet_alias_is_deduplicated(self):
        p=PublicFixture();report=self.run_report(['GOOG','GOOGL'],p)
        self.assertEqual(len(report['comparison']),1)
        self.assertEqual(len(p.calls),len(set(p.calls)))
        self.assertNotIn('GOOGL',[t for _,t in p.calls])

    def test_rate_limit_stops_requests_and_hides_price(self):
        p=PublicFixture()
        def limited(t):
            p.calls.append(('stock/profile2',t))
            return {'status':'RATE_LIMIT','data':{}}
        p.get_company_profile=limited
        report=self.run_report(provider=p)
        self.assertEqual(p.calls,[('stock/profile2','NVDA')])
        self.assertTrue(all(r['peer_mid'] is None for r in report['comparison']))

    def test_no_key_does_not_fetch_target(self):
        p=PublicFixture();p.configured=lambda:False
        loader=Mock(side_effect=AssertionError('No target request'))
        report=self.run_report(provider=p,loader=loader)
        loader.assert_not_called()
        self.assertTrue(all(r['diagnostic_status']=='NOT_CONFIGURED' for r in report['comparison']))

    def test_internal_capture_uses_normal_production_fundamentals(self):
        with patch('analysis_service.analyze_ticker') as analyze, patch('mag7_monitor.get_live_fundamentals') as load:
            admin._live_internal('NVDA')
            args=analyze.call_args.kwargs
            self.assertEqual(args['peer_mode'],'diagnostic')
            self.assertNotIn('market_reference_provider',args)
            args['fundamentals_loader']('NVDA')
            load.assert_called_once_with('NVDA')

    def test_pipeline_preserves_exact_exclusion_reasons(self):
        p=PublicFixture();original=p.get_basic_financials
        p.get_basic_financials=lambda t:({'status':'NO_DATA','data':{}} if t=='MRVL' else original(t))
        report=self.run_report(['NVDA'],p)
        trace=report['peer_results'][0]['pipeline_trace']
        self.assertEqual(trace['initial_candidates'],3)
        self.assertEqual(trace['after_data_availability'],2)
        self.assertEqual(next(x for x in trace['peers'] if x['ticker']=='MRVL')['exact_exclusion_reason'],'NO_DATA')
        self.assertEqual(report['internal_source_audit'][0]['production_analysis_internal_fair'],290.44)


if __name__=='__main__':unittest.main()
