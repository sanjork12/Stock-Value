"""Peer model contract tests using synthetic fixtures, never market observations."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os
import unittest
from unittest.mock import patch

from peer_comparable import (GROUPS, PeerComparableResult, calculate_peer_comparable,
                             canonical, group_for, peer_model_mode, quantile)
from finnhub_service import FinnhubProvider
from valuation_engine import valuate
from analysis_service import analyze_ticker
from test_v41_regression import AAPL_FIN, JPM_FIN, _ohlcv

NOW = datetime(2026, 10, 7, 12, tzinfo=timezone.utc)
FIN = dict(forward_eps=5, forward_eps_source='forwardEps', trailing_eps=4,
           trailing_eps_source='trailingEps', canonical_shares=10,
           canonical_shares_source='impliedSharesOutstanding', shares=10,
           revenue=2000, ebitda=1000, cash=100, debt=200,
           roe=.15, book_value_per_share=20)
METRICS = {'Forward PE':20, 'TTM PE':25, 'EV/EBITDA TTM':10,
           'EV/Revenue TTM':5, 'P/B':2, 'ROE TTM':15,
           'Revenue Growth TTM YoY':10, 'Operating Margin TTM':20}


class FixtureProvider:
    def __init__(self):
        tickers = {t for group in GROUPS.values() for t in group}
        self.metrics = {t:dict(METRICS) for t in tickers}
        self.profiles = {t:{'marketCapitalization':1000, 'finnhubIndustry':'Software'} for t in tickers}
        self.calls = []
        self.status = {}
        self.fetched_at = NOW.isoformat()

    def response(self, ticker, kind, data):
        self.calls.append((ticker, kind))
        return dict(status=self.status.get((ticker,kind),'AVAILABLE'), data=deepcopy(data),
                    fetched_at=self.fetched_at, source='Finnhub')

    def get_company_profile(self, ticker):
        return self.response(ticker,'profile',self.profiles.get(ticker,{}))

    def get_basic_financials(self, ticker):
        return self.response(ticker,'metrics',self.metrics.get(ticker,{}))


class PeerComparableTests(unittest.TestCase):
    def setUp(self): self.provider = FixtureProvider()

    def calc(self, ticker='NVDA', cls='semiconductor_growth', financials=None, peers=None):
        return calculate_peer_comparable(ticker, financials if financials is not None else FIN, cls,
                    provider=self.provider, now=NOW, peer_tickers=peers)

    def test_business_groups(self):
        for ticker, cls, expected in [('ORCL','high_growth_software','enterprise_software'),
            ('MSFT','mega_cap_tech','enterprise_software'),('JPM','bank','bank'),
            ('NVDA','semiconductor_growth','semiconductor_growth'),('AMZN','mega_cap_tech','commerce_platform')]:
            self.assertEqual(group_for(ticker,cls),expected)

    def test_alias_deduplicated_and_self_excluded(self):
        r = self.calc('GOOGL','mega_cap_tech',peers=['GOOG','GOOGL','META','PINS','TTD'])
        self.assertEqual(r.target_ticker,'GOOG')
        self.assertEqual(r.peers_considered,['META','PINS','TTD'])
        self.assertEqual(sum(t=='GOOG' and kind=='profile' for t,kind in self.provider.calls),1)

    def test_under_three_unavailable(self):
        r = self.calc(peers=['AVGO','AMD'])
        self.assertFalse(r.valid); self.assertIsNone(r.mid)

    def test_quantiles_and_range(self):
        for t,value in zip(['AVGO','AMD','MRVL'],[10,20,30]):self.provider.metrics[t]['Forward PE']=value
        r=self.calc()
        self.assertTrue(r.valid)
        self.assertEqual((r.peer_q1,r.peer_median,r.peer_q3),(15,20,25))
        self.assertEqual((r.low,r.mid,r.high),(75,100,125))
        self.assertNotEqual(r.confidence,'HIGH')

    def test_outlier_removed_then_minimum_applied(self):
        for t,value in zip(['META','TTD','PINS','SNAP'],[20,21,22,500]):self.provider.metrics[t]['Forward PE']=value
        r=self.calc('GOOG','mega_cap_tech')
        self.assertTrue(r.valid)
        self.assertEqual(r.exclusion_reasons['SNAP'],'peer_excluded_as_outlier')
        self.assertEqual(r.peer_median,21)

    def test_outlier_leaves_two_unavailable(self):
        self.provider.metrics['MRVL']['Forward PE']=1000
        f={**FIN,'ebitda':None,'revenue':None}
        self.assertFalse(self.calc(financials=f).valid)

    def test_missing_forward_eps_cannot_use_forward_pe(self):
        r=self.calc(financials={**FIN,'forward_eps':None,'ebitda':None,'revenue':None})
        self.assertFalse(r.valid)

    def test_statement_proxy_cannot_drive_peer_pe(self):
        for source in ['statement_derived','ni_over_diluted_shares','price/forwardPE','unknown','']:
            with self.subTest(source=source):
                self.assertFalse(self.calc(financials={**FIN,'forward_eps_source':source,'ebitda':None,'revenue':None}).valid)

    def test_ev_to_equity_uses_canonical_shares(self):
        r=self.calc(financials={**FIN,'forward_eps':None,'shares':1})
        self.assertEqual(r.selected_multiple,'EV/EBITDA')
        self.assertEqual(r.mid,(1000*10+100-200)/10)

    def test_ev_missing_cash_debt_or_canonical_shares_rejected(self):
        for field in ['cash','debt','canonical_shares']:
            with self.subTest(field=field):
                self.assertFalse(self.calc(financials={**FIN,'forward_eps':None,field:None}).valid)

    def test_corrected_dual_class_canonical_shares_accepted(self):
        r=self.calc(financials={**FIN,'forward_eps':None,'class_specific_shares':True})
        self.assertTrue(r.valid)
        self.assertFalse(self.calc(financials={**FIN,'forward_eps':None,'class_specific_shares':True,
                                             'canonical_shares_source':'sharesOutstanding'}).valid)

    def test_ev_currency_mismatch_rejected(self):
        r=self.calc(financials={**FIN,'forward_eps':None,'quote_currency':'USD','financial_currency':'EUR'})
        self.assertFalse(r.valid)

    def test_bank_uses_pb_with_roe_context_not_ev(self):
        r=self.calc('JPM','bank')
        self.assertTrue(r.valid); self.assertEqual(r.selected_multiple,'P/B')
        self.assertEqual(r.mid,40)
        self.assertEqual(r.provenance['roe_adjustment']['factor'],1)

    def test_bank_missing_book_falls_back_to_pe(self):
        r=self.calc('JPM','bank',financials={**FIN,'book_value_per_share':None})
        self.assertTrue(r.valid);self.assertEqual(r.selected_multiple,'P/E TTM')

    def test_nonpositive_cap_excluded(self):
        self.provider.profiles['AMD']['marketCapitalization']=0
        r=self.calc()
        self.assertFalse(r.valid)
        self.assertEqual(r.exclusion_reasons['AMD'],'missing_or_nonpositive_market_cap')

    def test_extreme_growth_and_profitability_excluded(self):
        self.provider.metrics['AMD']['Revenue Growth TTM YoY']=10000
        self.provider.metrics['MRVL']['TTM PE']=-5
        r=self.calc(financials={**FIN,'revenue':None})
        self.assertEqual('comparability_weight_below_floor',r.exclusion_reasons['AMD'])
        self.assertEqual(r.exclusion_reasons['MRVL'],'noncomparable_profitability_basis')

    def test_memory_storage_not_comparable(self):
        r=self.calc('MU','cyclical_semiconductor')
        self.assertFalse(r.valid)
        self.assertEqual(r.exclusion_reasons['WDC'],'business_model_mismatch')

    def test_stale_data_excluded_and_warned(self):
        self.provider.fetched_at=(NOW-timedelta(days=4)).isoformat()
        r=self.calc()
        self.assertFalse(r.valid)
        self.assertTrue(any('stale' in s for s in r.warnings))

    def test_rate_limit_stops_subsequent_calls(self):
        self.provider.status[('NVDA','metrics')]='RATE_LIMIT'
        r=self.calc()
        self.assertEqual(self.provider.calls,[('NVDA','profile'),('NVDA','metrics')])
        self.assertFalse(r.valid)
        self.assertTrue(all(reason=='RATE_LIMIT' for reason in r.exclusion_reasons.values()))

    def test_provenance_and_input_immutability(self):
        before=deepcopy(FIN);r=self.calc()
        self.assertEqual(FIN,before)
        self.assertEqual(r.provenance['source'],'Finnhub')
        self.assertEqual(r.provenance['AMD']['peer_data_age_hours'],0)
        self.assertEqual(r.provenance['endpoints'],['stock/profile2','stock/metric'])

    def test_only_free_endpoints_and_new_metric_mapping(self):
        calls=[]
        def fetch(path,params,key):
            calls.append(path)
            if path=='stock/profile2':return {'name':'Example','marketCapitalization':1000,'finnhubIndustry':'Semiconductors'}
            return {'metric':{'forwardPE':20,'peTTM':25,'evEbitdaTTM':10,'evRevenueTTM':5,'forwardPEG':1.2,
                              'marketCapitalization':1000,'revenueGrowthTTMYoy':10,'operatingMarginTTM':20}}
        p=FinnhubProvider(key_loader=lambda:'fixture-only',fetch=fetch,sleep=lambda _:None)
        r=calculate_peer_comparable('NVDA',FIN,'semiconductor_growth',provider=p)
        self.assertTrue(r.valid)
        self.assertEqual(set(calls),{'stock/profile2','stock/metric'})
        self.assertEqual(p.get_basic_financials('NVDA')['data']['Forward PEG'],1.2)

    def test_diagnostic_engine_exactly_unchanged(self):
        peer=PeerComparableResult('AAPL','mega_cap_tech',valid=True,applicable=True,low=200,mid=220,high=240)
        self.assertEqual(valuate('AAPL',AAPL_FIN),valuate('AAPL',AAPL_FIN,peer_result=peer,peer_mode='diagnostic'))

    def test_active_weights_preserve_existing_proportions(self):
        baseline=valuate('AAPL',AAPL_FIN)
        peer=PeerComparableResult('AAPL','mega_cap_tech',valid=True,applicable=True,
                                   low=baseline['fair_low'],mid=baseline['fair'],high=baseline['fair_high'])
        active=valuate('AAPL',AAPL_FIN,peer_result=peer,peer_mode='active')
        self.assertAlmostEqual(active['weights_used']['peer_comparable'],.15)
        for name,weight in baseline['weights_used'].items():self.assertAlmostEqual(active['weights_used'][name],weight*.85)
        self.assertAlmostEqual(sum(active['weights_used'].values()),1)

    def test_active_unavailable_peer_unchanged(self):
        self.assertEqual(valuate('AAPL',AAPL_FIN),valuate('AAPL',AAPL_FIN,
            peer_result=PeerComparableResult('AAPL','mega_cap_tech'),peer_mode='active'))

    def test_config_defaults_safely(self):
        with patch.dict(os.environ,{'PEER_MODEL_MODE':'bad'}):self.assertEqual(peer_model_mode(),'diagnostic')
        with patch.dict(os.environ,{'PEER_MODEL_MODE':'active'}):self.assertEqual(peer_model_mode(),'active')

    def test_analysis_external_failure_preserves_all_zones(self):
        args=dict(history_loader=lambda *_:_ohlcv(), fundamentals_loader=lambda _:deepcopy(AAPL_FIN),peer_mode='diagnostic')
        with patch('peer_comparable.calculate_peer_comparable',return_value=PeerComparableResult('AAPL','mega_cap_tech')):
            baseline=analyze_ticker('AAPL',**args)
        with patch('peer_comparable.calculate_peer_comparable',side_effect=RuntimeError('provider failed')):
            failed=analyze_ticker('AAPL',**args)
        for field in ['blend','fair','zones','exit_zone','reliability_score']:
            self.assertEqual(baseline.get(field),failed.get(field))
        self.assertIn('peer_reference_unavailable',failed['peer_diagnostics']['warnings'])

    def test_high_growth_revenue_requires_comparable_profitability(self):
        self.provider.metrics['SNOW']['Operating Margin TTM']=-3
        r=self.calc('PLTR','high_growth_software',financials={**FIN,'forward_eps':None,'ebitda':None})
        self.assertTrue(r.valid)
        self.assertEqual(r.selected_multiple,'EV/Revenue')
        self.assertEqual(r.exclusion_reasons['SNOW'],'noncomparable_profitability_basis')

    def test_high_growth_pe_requires_profitability_history(self):
        r=self.calc('PLTR','high_growth_software',financials={**FIN,'revenue':None,'ebitda':None})
        self.assertFalse(r.valid)
        self.assertTrue(any(x.get('reason')=='stable_target_profitability_unverified'
                            for x in r.provenance['selection_attempts']))

    def test_active_bank_weight(self):
        baseline=valuate('JPM',JPM_FIN)
        peer=PeerComparableResult('JPM','bank',valid=True,applicable=True,
            low=baseline['fair_low'],mid=baseline['fair'],high=baseline['fair_high'])
        active=valuate('JPM',JPM_FIN,peer_result=peer,peer_mode='active')
        self.assertAlmostEqual(active['weights_used']['peer_comparable'],.15)

    def test_report_without_key_does_not_fetch_target_or_infer_direction(self):
        from scripts.report_peer_comparable import build_report
        from unittest.mock import Mock
        p=FinnhubProvider(key_loader=lambda:None)
        loader=Mock(side_effect=AssertionError('No target calls without configuration'))
        report=build_report(provider=p,financial_loader=loader,references={'NVDA':{'external_benchmark':300}})
        loader.assert_not_called()
        self.assertEqual(len(report['comparison']),5)
        self.assertTrue(all(row['current_internal_mid'] is None and row['peer_mid'] is None
                            and row['benchmark_direction']=='UNAVAILABLE' for row in report['comparison']))

    def test_historical_analysis_does_not_fetch_current_peers(self):
        p=FixtureProvider()
        r=analyze_ticker('AAPL','2025-01-01',history_loader=lambda *_:_ohlcv(),
                         snapshot_loader=lambda *_:None,peer_provider=p,peer_mode='active')
        self.assertEqual(p.calls,[])
        self.assertIsNone(r['peer_comparable_result'])

    def test_one_peer_transport_failure_is_explicit_and_isolated(self):
        original=self.provider.get_company_profile
        def failing(ticker):
            if ticker=='IBM':raise OSError('transport failed')
            return original(ticker)
        self.provider.get_company_profile=failing
        r=self.calc('MSFT','mega_cap_tech')
        self.assertTrue(r.valid)
        self.assertEqual(r.exclusion_reasons['IBM'],'NETWORK_ERROR')

    def test_foreign_peer_result_cannot_enter_active_blend(self):
        peer=PeerComparableResult('MSFT','mega_cap_tech',valid=True,applicable=True,low=200,mid=220,high=240)
        self.assertEqual(valuate('AAPL',AAPL_FIN),valuate('AAPL',AAPL_FIN,peer_result=peer,peer_mode='active'))

    def test_five_requested_samples_with_synthetic_inputs(self):
        for ticker,cls in [('NVDA','semiconductor_growth'),('ORCL','high_growth_software'),
                           ('MSFT','mega_cap_tech'),('GOOG','mega_cap_tech'),('AMZN','mega_cap_tech')]:
            with self.subTest(ticker=ticker):
                r=self.calc(ticker,cls)
                if ticker=='AMZN':
                    self.assertFalse(r.valid)
                    self.assertEqual(r.eligibility,'NOT_ELIGIBLE')
                    continue
                self.assertTrue(r.valid)
                self.assertGreaterEqual(len(r.peers_included),3)


if __name__=='__main__':unittest.main()
