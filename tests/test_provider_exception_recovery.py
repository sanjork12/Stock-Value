from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock,patch
import unittest
from yfinance.exceptions import YFRateLimitError,YFException
from requests.exceptions import Timeout,ConnectionError
import fundamental_acquisition as a
from provider_recovery import BatchProviderRateLimitState,classify_exception
from test_quality_acquisition import Healthy,normalize
from production_input_wiring import snapshot_fundamentals
import production_snapshot_admin as admin
from scripts.verify_peer_isolation import history

class Failed(Healthy):
    def __init__(self,ticker='NVDA',exc=None):
        super().__init__(ticker);self.exc=exc or YFRateLimitError();self.info_reads=0;self.calls=0
    def get_info(self):self.calls+=1;raise self.exc
    @property
    def info(self):self.info_reads+=1;raise AssertionError('Hidden alias read')

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.provider=Mock();self.provider.get_company_profile.return_value={'status':'NOT_CONFIGURED'}
        self.sleep=Mock();self.state=BatchProviderRateLimitState(sleep_fn=self.sleep,clock_fn=lambda:'fixed-clock')
    def run_acquire(self,first=None,fresh=None,ticker='NVDA'):
        factory=Mock(side_effect=[first or Failed(ticker),fresh or Healthy(ticker)])
        result=a.acquire(ticker,factory,provider=self.provider,rate_limit_state=self.state)
        self.assertLessEqual(result[2]['provider_attempts']['yahoo_get_info_total'],2)
        return result,factory
    def test_rate_limit_recovers_once(self):
        first=Failed();(info,_,m),factory=self.run_acquire(first)
        self.assertEqual(m['primary_exception_category'],'TRANSIENT_RATE_LIMIT');self.assertEqual(m['primary_health']['overall_state'],'UNAVAILABLE')
        self.assertEqual(m['fresh_recovery_result'],'RECOVERED_HEALTHY');self.assertTrue(m['recovery_payload_accepted'])
        self.assertEqual(info['forwardEps'],5);self.assertEqual(factory.call_count,2);self.assertEqual(first.info_reads,0)
    def test_real_shape_missing_eps_and_currency_retries(self):
        (_,_,m),_=self.run_acquire()
        self.assertEqual(m['provider_recovery_decision']['trigger_type'],'PRIMARY_PROVIDER_EXCEPTION')
        self.assertIn('forward_eps',m['provider_recovery_decision']['critical_missing_fields'])
        self.assertIn('financial_currency',m['provider_recovery_decision']['critical_missing_fields'])
        self.assertTrue(m['fresh_recovery_attempted'])
    def test_timeout_recovers(self):
        (_,_,m),_=self.run_acquire(Failed(exc=Timeout('timeout')))
        self.assertEqual(m['primary_exception_category'],'TRANSIENT_TIMEOUT');self.assertTrue(m['fresh_recovery_used'])
    def test_network_recovers(self):
        (_,_,m),_=self.run_acquire(Failed(exc=ConnectionError('disconnected')))
        self.assertEqual(m['primary_exception_category'],'TRANSIENT_NETWORK');self.assertTrue(m['fresh_recovery_used'])
    def test_programming_no_retry(self):
        (_,_,m),f=self.run_acquire(Failed(exc=TypeError('bad code')))
        self.assertEqual(f.call_count,1);self.assertFalse(m['fresh_recovery_attempted']);self.assertEqual(m['provider_recovery_decision']['reason'],'NON_TRANSIENT_EXCEPTION')
    def test_unknown_no_retry(self):
        (_,_,m),f=self.run_acquire(Failed(exc=RuntimeError('unknown')))
        self.assertEqual(m['primary_exception_category'],'UNKNOWN_EXCEPTION');self.assertEqual(f.call_count,1)
    def test_taxonomy_not_substring(self):
        self.assertEqual(classify_exception(RuntimeError('YFRateLimitError Timeout')),'UNKNOWN_EXCEPTION')
        self.assertEqual(classify_exception(YFException('bad')),'NON_TRANSIENT_PROVIDER_ERROR')
    def test_double_rate_limit_stops(self):
        (_,_,m),f=self.run_acquire(fresh=Failed())
        self.assertEqual(f.call_count,2);self.assertEqual(m['fresh_recovery_result'],'RECOVERY_RATE_LIMITED')
        self.assertFalse(m['fresh_recovery_used']);self.assertEqual(self.state.recovery_rate_limit_count,1)
    def test_partial_improvement_accepted(self):
        raw={'symbol':'NVDA','currentPrice':100,'marketCap':1e11,'sharesOutstanding':1e9,'currency':'USD','forwardEps':5}
        (_,_,m),_=self.run_acquire(fresh=Healthy(raw=raw))
        self.assertEqual(m['fresh_recovery_result'],'RECOVERED_PARTIAL');self.assertTrue(m['fresh_recovery_used'])
    def test_equal_composed_quality_rejected(self):
        raw={'symbol':'NVDA','currentPrice':100,'marketCap':1e11,'sharesOutstanding':1e9,'currency':'USD'}
        (_,_,m),_=self.run_acquire(fresh=Healthy(raw=raw))
        self.assertEqual(m['fresh_recovery_result'],'REJECT_NO_HEALTH_IMPROVEMENT');self.assertFalse(m['recovery_payload_accepted'])
    def test_wrong_ticker_rejected(self):
        (_,_,m),_=self.run_acquire(fresh=Healthy('MSFT'))
        self.assertEqual(m['recovery_acceptance_reason'],'TICKER_IDENTITY_MISMATCH')
    def test_missing_payload_explicit(self):
        fresh=Healthy();fresh.get_info=lambda:None
        (_,_,m),_=self.run_acquire(fresh=fresh)
        self.assertEqual(m['fresh_recovery_result'],'RECOVERY_INVALID_PAYLOAD')
    def test_healthy_no_cooldown(self):
        (_,_,m),f=self.run_acquire(Healthy())
        self.sleep.assert_not_called();self.assertEqual(f.call_count,1);self.assertEqual(m['fresh_recovery_reason'],['RECOVERY_NOT_NEEDED'])
    def test_first_limit_marks_state(self):
        self.run_acquire();self.assertEqual(self.state.first_observed_ticker,'NVDA');self.assertEqual(self.state.first_observed_at,'fixed-clock')
    def test_recovery_short_cooldown(self):
        self.run_acquire();self.sleep.assert_called_once_with(2)
    def test_later_ticker_cooldown_not_skipped(self):
        self.run_acquire();(_,_,m),f=self.run_acquire(Healthy('MSFT'),ticker='MSFT')
        self.assertEqual(self.sleep.call_args.args,(3,));self.assertEqual(f.call_count,1);self.assertTrue(m['batch_cooldown_applied'])
    def test_context_resets(self):
        with a.acquisition_batch('one',sleep_fn=self.sleep) as one:one['provider_rate_limit_state'].observe('GOOG')
        with a.acquisition_batch('two',sleep_fn=self.sleep) as two:self.assertFalse(two['provider_rate_limit_state'].yahoo_rate_limit_observed)
    def test_nested_context_restores(self):
        with a.acquisition_batch('one',sleep_fn=self.sleep) as one:
            with a.acquisition_batch('two',sleep_fn=self.sleep) as two:two['provider_rate_limit_state'].observe('NVDA')
            self.assertIs(a._SCOPE.get(),one);self.assertFalse(one['provider_rate_limit_state'].yahoo_rate_limit_observed)
    def test_attempt_budget_blocks_third(self):
        self.run_acquire()
        with self.assertRaises(RuntimeError):self.run_acquire()
    def test_five_stock_simulation(self):
        factories={};results={}
        for ticker in ('GOOG','MSFT','ORCL','NVDA','AMZN'):
            first=Failed(ticker) if ticker in ('GOOG','MSFT','NVDA') else Healthy(ticker)
            fresh=Failed(ticker) if ticker=='MSFT' else Healthy(ticker)
            (info,_,m),f=self.run_acquire(first,fresh,ticker)
            factories[ticker]=f;results[ticker]=m
            self.assertEqual(info.get('symbol',ticker),ticker)
        self.assertEqual(sum(f.call_count for f in factories.values()),8)
        self.assertEqual(self.state.cooldown_events,7);self.assertEqual(self.state.primary_rate_limit_count,3)
        self.assertEqual(self.state.recovery_rate_limit_count,1);self.assertEqual(self.state.recovery_successes,2)
    def test_all_five_limited_max_ten(self):
        total=0
        for t in ('GOOG','MSFT','ORCL','NVDA','AMZN'):
            (_,_,m),f=self.run_acquire(Failed(t),Failed(t),t);total+=m['provider_attempts']['yahoo_get_info_total']
        self.assertEqual(total,10)
    def test_healthy_cache_preserved(self):
        cache=a.RawAcquisitionCache();factory=Mock(side_effect=[Healthy(),Failed(),Failed()])
        with a.acquisition_batch('a',sleep_fn=self.sleep):first=cache.get('NVDA',factory=factory,normalize=normalize,provider=self.provider)
        with a.acquisition_batch('b',sleep_fn=self.sleep):bad=cache.get('NVDA',factory=factory,normalize=normalize,provider=self.provider,force_refresh=True)
        with a.acquisition_batch('c',sleep_fn=self.sleep):again=cache.get('NVDA',factory=factory,normalize=normalize,provider=self.provider)
        self.assertEqual(again['forward_eps'],first['forward_eps']);self.assertFalse(bad['acquisition_metadata']['cache_write_performed'])
        self.assertLessEqual(bad['acquisition_metadata']['cache_ttl'],60)
        self.assertEqual(again['acquisition_metadata']['provider_attempts']['yahoo_get_info_total'],0)
        self.assertFalse(again['acquisition_metadata']['fresh_recovery_attempted'])
    def test_degraded_cache_ttl(self):
        with a.acquisition_batch('ttl',sleep_fn=self.sleep):
            r=a.RawAcquisitionCache().get('NVDA',factory=lambda t:Failed(t),normalize=normalize,provider=self.provider)
        self.assertLessEqual(r['acquisition_metadata']['cache_ttl'],60)
    def test_recovery_no_eps_derivation_or_currency_inference(self):
        raw=Healthy().raw
        for k in ('forwardEps','financialCurrency'):raw.pop(k)
        raw['targetMeanPrice']=900;raw['forwardPE']=20
        (info,_,m),_=self.run_acquire(fresh=Healthy(raw=raw))
        self.assertNotIn('forwardEps',info);self.assertNotIn('financialCurrency',info)
    def test_accepted_reaches_valuation_calibration(self):
        factory=Mock(side_effect=[Failed(),Healthy()]);cache=a.RawAcquisitionCache()
        with patch.object(a,'RAW_CACHE',cache),patch('mag7_monitor._yfinance',return_value=SimpleNamespace(Ticker=factory)),patch.object(a,'flags',return_value=a.Flags()):
            with a.acquisition_batch('integration',sleep_fn=self.sleep):
                s=admin.capture_analysis('NVDA',history_loader=history,fundamentals_loader=snapshot_fundamentals)
        tr=s['production_input_trace'];self.assertTrue(tr['accepted_recovery_payload_is_downstream_payload'])
        for field in ('forward_eps','financial_currency','quote_currency'):
            r=tr[field];self.assertEqual(r['raw'],r['normalized']);self.assertEqual(r['raw'],r['valuation_input']);self.assertEqual(r['raw'],r['calibration_input'])
        self.assertEqual(tr['provider_recovery_status'],'RECOVERY_HEALTHY');self.assertEqual(tr['acceptance_status'],'PASS')
    def test_secret_exception_message_not_retained(self):
        (_,_,m),_=self.run_acquire(Failed(exc=Timeout('PRIVATE_KEY_COOKIE')))
        self.assertNotIn('PRIVATE_KEY_COOKIE',str(m))
    def test_schema_error_no_recovery(self):
        first=Healthy();first.get_info=lambda:['invalid']
        (_,_,m),factory=self.run_acquire(first)
        self.assertEqual(factory.call_count,1);self.assertEqual(m['primary_exception_category'],'NON_TRANSIENT_PROVIDER_ERROR')
    def test_empty_without_transient_not_retried(self):
        first=Healthy();first.get_info=lambda:{}
        (_,_,m),factory=self.run_acquire(first)
        self.assertEqual(factory.call_count,1);self.assertEqual(m['provider_recovery_decision']['reason'],'UNAVAILABLE_WITHOUT_TRANSIENT_EVIDENCE')
    def test_recovered_healthy_cache_has_zero_new_attempts(self):
        cache=a.RawAcquisitionCache();factory=Mock(side_effect=[Failed(),Healthy()])
        with a.acquisition_batch('first',sleep_fn=self.sleep):cache.get('NVDA',factory=factory,normalize=normalize,provider=self.provider)
        with a.acquisition_batch('second',sleep_fn=self.sleep):r=cache.get('NVDA',factory=factory,normalize=normalize,provider=self.provider)
        m=r['acquisition_metadata'];self.assertFalse(m['fresh_recovery_attempted']);self.assertEqual(m['provider_attempts']['yahoo_get_info_total'],0)
        self.assertTrue(m['origin_provider_recovery']['fresh_recovery_used'])
    def test_batch_summary_exported_without_persistence(self):
        import test_v45_snapshot_export as snapshot_tests
        fixture=snapshot_tests.SnapshotExportTests();fixture.setUp()
        try:
            counts={}
            def factory(ticker):
                counts[ticker]=counts.get(ticker,0)+1
                return Failed(ticker) if counts[ticker]==1 and ticker=='GOOG' else Healthy(ticker)
            fixture.client.table.side_effect=AssertionError('No Supabase I/O')
            with patch.object(a,'RAW_CACHE',a.RawAcquisitionCache()),patch.object(a,'BatchProviderRateLimitState',return_value=self.state),patch('mag7_monitor._yfinance',return_value=SimpleNamespace(Ticker=factory)),patch('finnhub_service.get_finnhub_provider',return_value=self.provider):
                r=admin.run_batch(fixture.client,'u',fixture.secrets,history_loader=history,fundamentals_loader=snapshot_fundamentals)
            self.assertEqual(r['provider_rate_limit_summary']['primary_rate_limit_count'],1)
            self.assertEqual(len(r['stocks']),5);self.assertEqual(sum(counts.values()),6)
            self.assertTrue(all(s['production_input_trace']['acceptance_status']=='PASS' for s in r['stocks']))
            fixture.client.table.assert_not_called()
        finally:fixture.tearDown()
    def test_failed_recovery_guard_stays_ineligible(self):
        from calibration_snapshot_guard import calibration_eligibility
        factory=lambda ticker:Failed(ticker)
        with patch.object(a,'RAW_CACHE',a.RawAcquisitionCache()),patch('mag7_monitor._yfinance',return_value=SimpleNamespace(Ticker=factory)),patch('finnhub_service.get_finnhub_provider',return_value=self.provider):
            with a.acquisition_batch('failed',sleep_fn=self.sleep):
                s=admin.capture_analysis('NVDA',history_loader=history,fundamentals_loader=snapshot_fundamentals)
        self.assertTrue(calibration_eligibility(s,None)['calibration_eligibility'].startswith('INELIGIBLE'))
    def test_real_yahoo_owned_alias_cannot_retry(self):
        from yfinance import Ticker
        from provider_recovery import pin_owned_info_alias
        ticker=Ticker('NVDA');network=Mock(side_effect=AssertionError('No additional network get_info'))
        ticker.get_info=network
        pin_owned_info_alias(ticker,{'symbol':'NVDA','forwardEps':5})
        one=ticker.info;one['forwardEps']=0
        self.assertEqual(ticker.info['forwardEps'],5);network.assert_not_called()
        other=Ticker('MSFT');self.assertNotIn('get_info',other.__dict__)

if __name__=='__main__':unittest.main()
