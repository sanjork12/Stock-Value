from copy import deepcopy
from dataclasses import replace
from datetime import datetime,timezone
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
import pandas as pd

import fundamental_acquisition as a
from mag7_monitor import _get_live_fundamentals_impl,get_live_fundamentals
from test_cloud_financial_forensics import YahooFixture
from valuation_engine import valuate


class Healthy(YahooFixture):
    def __init__(self,ticker='NVDA',raw=None):
        super().__init__();self.ticker=ticker
        self.raw=raw if raw is not None else {'symbol':ticker,'exchange':'NMS','currentPrice':100,
            'marketCap':1e11,'sharesOutstanding':1e9,'impliedSharesOutstanding':1e9,
            'forwardEps':5,'trailingEps':4,'forwardPE':20,'currency':'USD','financialCurrency':'USD',
            'totalCash':3e9,'totalDebt':2e9,'ebitda':5e9,'totalRevenue':20e9,'earningsGrowth':.2,
            'lastSplitDate':1717977600,'lastSplitFactor':'20:1'}
        self.fast_info={'shares':1e9,'market_cap':1e11,'last_price':100,'currency':'USD'}
        self.splits=pd.Series([20.],index=pd.DatetimeIndex(['2024-06-10']))
    def get_info(self):return deepcopy(self.raw)
    @property
    def info(self):return deepcopy(self.raw)
    def get_history_metadata(self):return {'symbol':self.ticker,'currency':'USD','exchangeName':'NASDAQ'}


def incomplete():
    raw=Healthy().get_info()
    for k in ('forwardEps','currency','financialCurrency'):raw.pop(k)
    return raw


def normalize(info,t,meta):return _get_live_fundamentals_impl('NVDA',allow_estimates=True,_raw_context=(info,t,meta))


class QualityAcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.no_provider=Mock()
        self.no_provider.get_company_profile.return_value={'status':'NOT_CONFIGURED','data':None}
        self.no_provider.get_quote.return_value={'status':'NO_DATA','data':None}

    def acquire(self,primary=None,fresh=None,options=None):
        first=primary or Healthy()
        factory=Mock(side_effect=[first,fresh or Healthy()])
        info,t,meta=a.acquire('NVDA',factory,provider=self.no_provider,options=options or a.Flags())
        return info,t,meta,factory

    def test_nonempty_partial_not_healthy(self):
        self.assertEqual(a.health('NVDA',incomplete()).overall_state,'DEGRADED')

    def test_missing_forward_required_is_critical(self):
        raw=Healthy().raw;raw.pop('forwardEps')
        self.assertIn('forward_eps',a.health('NVDA',raw).critical_missing_fields)

    def test_missing_quote_is_critical(self):
        raw=Healthy().raw;raw.pop('currency')
        self.assertIn('quote_currency',a.health('NVDA',raw).critical_missing_fields)

    def test_irrelevant_forward_eps_not_required_for_bank(self):
        raw=Healthy('JPM').raw;raw.pop('forwardEps');raw.pop('ebitda')
        self.assertNotIn('forward_eps',a.health('JPM',raw).critical_missing_fields)
        self.assertNotIn('ebitda',a.health('JPM',raw).missing_fields)

    def test_fresh_success_whole_response(self):
        primary=Healthy(raw=incomplete());primary.raw['unrelated_old_marker']=123
        info,_,m,f=self.acquire(primary)
        self.assertEqual(m['fresh_recovery_result'],'ACCEPT_RECOVERY');self.assertEqual(info['forwardEps'],5)
        self.assertNotIn('unrelated_old_marker',info);self.assertEqual(f.call_count,2)
        self.assertEqual(m['health_state'],'HEALTHY')

    def test_fresh_failure_no_more_retries(self):
        raw=incomplete();first=Healthy(raw=raw);first.fast_info={}
        first.get_history_metadata=lambda:{}
        info,_,m,f=self.acquire(first,Healthy(raw=raw))
        self.assertEqual(f.call_count,2);self.assertIsNone(info.get('forwardEps'))
        self.assertEqual(m['health_state'],'DEGRADED');self.assertNotIn('financialCurrency',info)

    def test_healthy_no_fresh(self):
        _,_,m,f=self.acquire()
        self.assertEqual(f.call_count,1);self.assertFalse(m['fresh_recovery_attempted'])

    def test_fresh_disabled(self):
        _,_,m,f=self.acquire(Healthy(raw=incomplete()),options=a.Flags(fresh_recovery=False))
        self.assertFalse(m['fresh_recovery_attempted']);self.assertEqual(f.call_count,1)

    def test_fresh_wrong_identity_rejected(self):
        info,_,m,_=self.acquire(Healthy(raw=incomplete()),Healthy('WRONG'))
        self.assertNotEqual(m['fresh_recovery_result'],'ACCEPT_RECOVERY');self.assertIsNone(info.get('forwardEps'))

    def test_healthy_ttl_900(self):
        c=a.RawAcquisitionCache();r=c.get('NVDA',factory=Healthy,normalize=normalize,provider=self.no_provider)
        self.assertEqual(r['acquisition_metadata']['cache_ttl'],900)

    def test_partial_ttl_300(self):
        raw=Healthy().raw;raw.pop('forwardPE')
        c=a.RawAcquisitionCache();r=c.get('NVDA',factory=lambda _:Healthy(raw=raw),normalize=normalize,provider=self.no_provider)
        self.assertEqual(r['acquisition_metadata']['health_state'],'PARTIAL')
        self.assertEqual(r['acquisition_metadata']['cache_ttl'],300)

    def test_degraded_ttl_60(self):
        c=a.RawAcquisitionCache();r=c.get('NVDA',factory=lambda _:Healthy(raw=incomplete()),normalize=normalize,provider=self.no_provider)
        self.assertLessEqual(r['acquisition_metadata']['cache_ttl'],60)

    def test_expired_degraded_refresh(self):
        ticks=[0.];factory=Mock(side_effect=lambda _:Healthy(raw=incomplete()));c=a.RawAcquisitionCache(clock=lambda:ticks[0])
        c.get('NVDA',factory=factory,normalize=normalize,provider=self.no_provider)
        n=factory.call_count;ticks[0]=59
        hit=c.get('NVDA',factory=factory,normalize=normalize,provider=self.no_provider)
        self.assertTrue(hit['acquisition_metadata']['cache_hit']);self.assertEqual(factory.call_count,n)
        ticks[0]=61;c.get('NVDA',factory=factory,normalize=normalize,provider=self.no_provider)
        self.assertGreater(factory.call_count,n)

    def test_healthy_cache_not_overwritten(self):
        current=[Healthy()];factory=lambda _:current[0];c=a.RawAcquisitionCache()
        c.get('NVDA',factory=factory,normalize=normalize,provider=self.no_provider)
        current[0]=Healthy(raw=incomplete())
        fresh=c.get('NVDA',factory=factory,normalize=normalize,provider=self.no_provider,force_refresh=True)
        self.assertEqual(fresh['fundamentals_source_status'],'degraded_live')
        self.assertTrue(fresh['acquisition_metadata']['fresh_degraded_attempt_observed'])
        hit=c.get('NVDA',factory=factory,normalize=normalize,provider=self.no_provider)
        self.assertEqual(hit['forward_eps'],5);self.assertEqual(hit['fundamentals_source_status'],'cached_healthy')

    def test_cache_promotion(self):
        current=[Healthy(raw=incomplete())];factory=lambda _:current[0];c=a.RawAcquisitionCache()
        c.get('NVDA',factory=factory,normalize=normalize,provider=self.no_provider)
        current[0]=Healthy()
        r=c.get('NVDA',factory=factory,normalize=normalize,provider=self.no_provider,force_refresh=True)
        self.assertTrue(r['acquisition_metadata']['cache_quality_promoted'])
        self.assertEqual(r['acquisition_metadata']['cache_ttl'],900)

    def test_request_scope_coalescing_and_copy(self):
        c=a.RawAcquisitionCache();factory=Mock(side_effect=Healthy)
        with a.acquisition_batch(force_refresh=True) as scope:
            one=c.get('NVDA',factory=factory,normalize=normalize,provider=self.no_provider)
            two=c.get('NVDA',factory=factory,normalize=normalize,provider=self.no_provider)
            self.assertEqual(one,two);two['cash']=0;self.assertNotEqual(one['cash'],two['cash'])
            self.assertEqual(one['input_batch_id'],scope['batch_id'])
        self.assertEqual(factory.call_count,1)

    def test_new_batch_bypasses_stale_entry(self):
        c=a.RawAcquisitionCache();current=[Healthy(raw=incomplete())];factory=lambda _:current[0]
        with a.acquisition_batch(force_refresh=True):old=c.get('NVDA',factory=factory,normalize=normalize,provider=self.no_provider)
        current[0]=Healthy()
        with a.acquisition_batch(force_refresh=True):new=c.get('NVDA',factory=factory,normalize=normalize,provider=self.no_provider)
        self.assertNotEqual(old['input_batch_id'],new['input_batch_id']);self.assertEqual(new['forward_eps'],5)

    def test_quote_from_metadata_and_financial_unknown(self):
        raw=Healthy().raw;raw.pop('currency');raw.pop('financialCurrency')
        info,_,m,_=self.acquire(Healthy(raw=raw),Healthy(raw=raw))
        self.assertEqual(info['currency'],'USD');self.assertNotIn('financialCurrency',info)
        self.assertEqual(m['quote_currency_source'],'yahoo.history_metadata.currency')

    def test_quote_finnhub_valid_identity(self):
        raw=Healthy().raw;raw.pop('currency');t=Healthy(raw=raw);t.fast_info.pop('currency');t.get_history_metadata=lambda:{}
        self.no_provider.get_company_profile.return_value={'status':'AVAILABLE','data':{'ticker':'NVDA','exchange':'NASDAQ','currency':'USD'}}
        info,_,m,_=self.acquire(t,Healthy(raw=raw))
        self.assertEqual(m['quote_currency_source'],'finnhub.profile2.currency');self.assertEqual(info['currency'],'USD')

    def test_currency_conflict_unresolved(self):
        raw=Healthy().raw;raw.pop('currency');t=Healthy(raw=raw);t.fast_info['currency']='EUR'
        info,_,m,_=self.acquire(t,Healthy(raw=raw))
        self.assertNotIn('currency',info);self.assertEqual(m['quote_currency_validation'],'CURRENCY_PROVIDER_CONFLICT')

    def test_currency_listing_conflict_unresolved(self):
        raw=Healthy().raw;raw.pop('currency')
        self.no_provider.get_company_profile.return_value={'status':'AVAILABLE','data':{'ticker':'NVDA','exchange':'NYSE','currency':'USD'}}
        info,_,m,_=self.acquire(Healthy(raw=raw),Healthy(raw=raw))
        self.assertNotIn('currency',info);self.assertEqual(m['quote_currency_validation'],'LISTING_IDENTITY_CONFLICT')

    def test_split_direct_recovery(self):
        raw=Healthy().raw;raw.pop('lastSplitDate');raw.pop('lastSplitFactor')
        info,_,m,_=self.acquire(Healthy(raw=raw))
        self.assertEqual(info['lastSplitFactor'],20);self.assertEqual(m['split_source'],'yahoo.splits')
        self.assertTrue(m['split_fallback_used'])

    def test_split_ratio_canonical(self):
        self.assertEqual(a.split_ratio('20:1'),a.split_ratio(20.))
        self.assertIsNone(a.split_ratio('1:0'))

    def test_split_day_ignores_session_hours(self):
        self.assertEqual(a.split_day('2024-06-10T00:00:00-04:00'),a.split_day('2024-06-10T04:00:00Z'))

    def test_provider_split_disagreement_canonical(self):
        from input_resilience_audit import disagreements
        paths={'a':{'values':{'last_split_factor':'20:1'}},'b':{'values':{'last_split_factor':20.}}}
        self.assertEqual(disagreements(paths)[0]['status'],'CONSISTENT')

    def test_no_derived_forward_eps_even_flag_true(self):
        raw=Healthy().raw;raw.pop('forwardEps');t=Healthy(raw=raw)
        info,recorded,m,_=self.acquire(t,Healthy(raw=raw),a.Flags(derived_forward_eps=True))
        r=normalize(info,recorded,m)
        self.assertIsNone(r['forward_eps']);self.assertNotEqual(r['forward_eps_source'],'price/forwardPE')

    def test_trailing_and_statement_do_not_fill_forward(self):
        raw=Healthy().raw;raw.pop('forwardEps')
        info,t,m,_=self.acquire(Healthy(raw=raw),Healthy(raw=raw));r=normalize(info,t,m)
        self.assertIsNone(r['forward_eps']);self.assertIsNotNone(r['trailing_eps']);self.assertIsNotNone(r['statement_eps'])

    def test_existing_estimate_preserved(self):
        raw=Healthy().raw;raw.pop('forwardEps');t=Healthy(raw=raw)
        t.get_earnings_estimate=lambda:pd.DataFrame({'avg':[6.]},index=['0y'])
        info,recorded,m,_=self.acquire(t,Healthy(raw=raw));r=normalize(info,recorded,m)
        self.assertEqual(r['forward_eps'],6);self.assertEqual(r['forward_eps_acquisition_path'],'existing_earnings_estimate_path')
        self.assertEqual(r['existing_earnings_estimate_audit']['selected_period'],'0y')

    def test_last_reliable_never_requested(self):
        with patch('last_reliable_valuation.apply_last_reliable',side_effect=AssertionError('No Last Reliable')):
            c=a.RawAcquisitionCache();r=c.get('NVDA',factory=lambda _:Healthy(raw=incomplete()),normalize=normalize,provider=self.no_provider)
        self.assertIsNone(r['forward_eps'])

    def test_healthy_normalized_and_production_invariants(self):
        with patch('mag7_monitor._yfinance',return_value=SimpleNamespace(Ticker=Healthy)):
            old=_get_live_fundamentals_impl('NVDA')
        c=a.RawAcquisitionCache();new=c.get('NVDA',factory=Healthy,normalize=normalize,provider=self.no_provider)
        for key,value in old.items():self.assertEqual(new[key],value,key)
        before=valuate('NVDA',old,.3);after=valuate('NVDA',new,.3)
        self.assertEqual(before,after)

    def test_goog_canonical_basis_preserved(self):
        raw=Healthy('GOOG').raw;raw.update(sharesOutstanding=5.53e9,impliedSharesOutstanding=12.23e9,
            marketCap=12.23e9*100)
        ticker=Healthy('GOOG',raw=raw)
        with patch('mag7_monitor._yfinance',return_value=SimpleNamespace(Ticker=lambda _:ticker)):
            old=_get_live_fundamentals_impl('GOOG')
        info,t,m=a.acquire('GOOG',lambda _:ticker,provider=self.no_provider)
        new=_get_live_fundamentals_impl('GOOG',_raw_context=(info,t,m))
        self.assertEqual(old['canonical_shares'],new['canonical_shares']);self.assertEqual(new['canonical_shares'],12.23e9)
        self.assertEqual(old['canonical_shares_source'],new['canonical_shares_source'])

    def test_feature_flag_rollback(self):
        with patch('mag7_monitor._yfinance',return_value=SimpleNamespace(Ticker=Healthy)),patch.object(a,'flags',return_value=a.Flags(quality_cache=False)):
            old=_get_live_fundamentals_impl('NVDA');new=get_live_fundamentals('NVDA')
        self.assertEqual(old,new);self.assertNotIn('acquisition_metadata',new)

    def test_simulation_no_production_cache_write(self):
        from acquisition_simulation import run_simulation
        entries=repr(a.RAW_CACHE.entries);counts=a.RAW_CACHE.telemetry()
        with patch('valuation_engine.valuate',side_effect=AssertionError('No valuation')):
            result=run_simulation(factory=Healthy,provider=self.no_provider)
        self.assertEqual(entries,repr(a.RAW_CACHE.entries));self.assertEqual(counts,a.RAW_CACHE.telemetry())
        self.assertEqual(len(result['stocks']),5);self.assertTrue(all(len(s['scenarios'])==5 for s in result['stocks']))
        self.assertTrue(all(r['new_provider_requests_in_scenario']==0 for s in result['stocks'] for r in s['scenarios']))

    def test_incomplete_simulation_aborts(self):
        from acquisition_simulation import run_simulation
        def factory(ticker):
            raw=incomplete();raw['symbol']=ticker
            return Healthy(ticker,raw=raw)
        result=run_simulation(factory=factory,provider=self.no_provider)
        self.assertTrue(all(s['status']=='BASELINE_INCOMPLETE' and not s['scenarios'] for s in result['stocks']))

    def test_simulation_cache_local_does_not_write(self):
        c=a.RawAcquisitionCache();c.get('NVDA',factory=Healthy,normalize=normalize,provider=self.no_provider,simulation=True)
        self.assertEqual(c.entries,{});self.assertEqual(c.telemetry()['logical_acquisition_count'],0)

    def test_price_fallback_timestamp_and_listing(self):
        raw=Healthy().raw;raw.pop('currentPrice');t=Healthy(raw=raw);t.fast_info.pop('last_price')
        self.no_provider.get_company_profile.return_value={'status':'AVAILABLE','data':{'ticker':'NVDA','exchange':'NASDAQ','currency':'USD'}}
        self.no_provider.get_quote.return_value={'status':'AVAILABLE','data':{'c':101,'t':datetime.now(timezone.utc).timestamp()}}
        info,_,m,_=self.acquire(t,Healthy(raw=raw))
        self.assertEqual(info['currentPrice'],101);self.assertIn('current_price',m['provider_health']['fallback_fields_used'])

    def test_stale_price_rejected(self):
        raw=Healthy().raw;raw.pop('currentPrice');t=Healthy(raw=raw);t.fast_info.pop('last_price')
        self.no_provider.get_company_profile.return_value={'status':'AVAILABLE','data':{'ticker':'NVDA','exchange':'NASDAQ','currency':'USD'}}
        self.no_provider.get_quote.return_value={'status':'AVAILABLE','data':{'c':101,'t':1}}
        info,_,_,_=self.acquire(t,Healthy(raw=raw));self.assertNotIn('currentPrice',info)

    def test_forward_recovery_provenance(self):
        c=a.RawAcquisitionCache();factory=Mock(side_effect=[Healthy(raw=incomplete()),Healthy()])
        r=c.get('NVDA',factory=factory,normalize=normalize,provider=self.no_provider)
        self.assertEqual(r['forward_eps_acquisition_path'],'yahoo.fresh_get_info.forwardEps')
        self.assertEqual(r['fundamentals_source_status'],'fresh_recovered')

    def test_raw_cache_contains_no_valuation_results(self):
        c=a.RawAcquisitionCache();c.get('NVDA',factory=Healthy,normalize=normalize,provider=self.no_provider)
        entry=next(iter(c.entries.values()))
        self.assertEqual(set(entry),{'info','recorded','meta','written','expires'})
        self.assertNotIn('fair_value',entry['info'])

    def test_telemetry_no_identity(self):
        c=a.RawAcquisitionCache();factory=lambda _:Healthy(raw=incomplete())
        c.get('NVDA',factory=factory,normalize=normalize,provider=self.no_provider)
        c.get('NVDA',factory=factory,normalize=normalize,provider=self.no_provider)
        counts=c.telemetry();self.assertEqual(counts['degraded_cache_write_count'],1)
        self.assertEqual(counts['degraded_cache_hit_count'],1);self.assertEqual(counts['fresh_recovery_count'],1)
        self.assertTrue(all(isinstance(v,int) for v in counts.values()))

    def test_five_healthy_production_results_including_zones_identical(self):
        from analysis_service import analyze_ticker
        from scripts.verify_peer_isolation import history,internal_snapshot
        for ticker in ('GOOG','MSFT','ORCL','NVDA','AMZN'):
            factory=lambda symbol:Healthy(symbol)
            with patch('mag7_monitor._yfinance',return_value=SimpleNamespace(Ticker=factory)):
                old=_get_live_fundamentals_impl(ticker)
            c=a.RawAcquisitionCache()
            new=c.get(ticker,factory=factory,provider=self.no_provider,
                normalize=lambda info,t,meta:_get_live_fundamentals_impl(ticker,_raw_context=(info,t,meta)))
            with patch('analysis_service._attach_peer_diagnostics',side_effect=lambda result,*args,**kwargs:result):
                before=analyze_ticker(ticker,history_loader=history,fundamentals_loader=lambda _:deepcopy(old))
                after=analyze_ticker(ticker,history_loader=history,fundamentals_loader=lambda _:deepcopy(new))
            self.assertEqual(internal_snapshot(before),internal_snapshot(after),ticker)
            for key in ('zones','exit_zone','blend','reliability','confidence','fair_value'):
                self.assertEqual(before.get(key),after.get(key),(ticker,key))

    def test_guard_consumes_recovered_live_fields_without_special_override(self):
        from production_snapshot_admin import capture_analysis
        from calibration_snapshot_guard import calibration_eligibility
        from scripts.verify_peer_isolation import history
        factory=Mock(side_effect=[Healthy(raw=incomplete()),Healthy()]);c=a.RawAcquisitionCache()
        recovered=c.get('NVDA',factory=factory,normalize=normalize,provider=self.no_provider)
        stock=capture_analysis('NVDA',history_loader=history,fundamentals_loader=lambda _:recovered)
        result=calibration_eligibility(stock)
        self.assertEqual(result['calibration_eligibility'],'ELIGIBLE')

    def test_failed_recovery_still_guard_ineligible(self):
        from production_snapshot_admin import capture_analysis
        from calibration_snapshot_guard import calibration_eligibility
        from scripts.verify_peer_isolation import history
        c=a.RawAcquisitionCache();r=c.get('NVDA',factory=lambda _:Healthy(raw=incomplete()),normalize=normalize,provider=self.no_provider)
        stock=capture_analysis('NVDA',history_loader=history,fundamentals_loader=lambda _:r)
        result=calibration_eligibility(stock)
        self.assertNotEqual(result['calibration_eligibility'],'ELIGIBLE')
        self.assertIn('financial_currency_unknown',result['calibration_eligibility_reasons'])

    def test_real_admin_batch_new_ids_and_one_fetch_per_stock(self):
        from test_v45_snapshot_export import SnapshotExportTests
        import production_snapshot_admin as admin
        helper=SnapshotExportTests();helper.setUp()
        try:
            load=Mock(side_effect=lambda ticker:deepcopy(helper.financials[ticker]))
            from scripts.verify_peer_isolation import history
            first=admin.run_batch(helper.client,'u',helper.secrets,history_loader=history,fundamentals_loader=load)
            self.assertEqual(load.call_count,5);load.reset_mock();admin._LAST_RUN.clear()
            second=admin.run_batch(helper.client,'u',helper.secrets,history_loader=history,fundamentals_loader=load)
            self.assertEqual(load.call_count,5)
            self.assertNotEqual(first['input_batch_id'],second['input_batch_id'])
            self.assertTrue(all(s['input_batch_id']==second['input_batch_id'] for s in second['stocks']))
            helper.client.table.assert_not_called()
        finally:helper.doCleanups()

    def test_simulation_admin_access_required(self):
        import input_resilience_admin as admin
        with patch.object(admin,'is_cloud_runtime',return_value=True),patch.object(admin,'verified_admin',return_value=False):
            with self.assertRaises(PermissionError):admin.run_cloud_simulation(Mock(),'u',{})
