"""Forced diagnostic isolation invariants; all inputs are synthetic fixtures."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import analysis_service
from peer_comparable import PeerComparableResult
from scripts.verify_peer_isolation import history, internal_snapshot

ROOT=Path(__file__).resolve().parents[1]
FINANCIALS=json.loads((ROOT/'tests/fixtures/peer_diagnostic_financials.json').read_text(encoding='utf-8'))['tickers']


class DiagnosticIsolationTests(unittest.TestCase):
    def analyze(self,ticker):
        return analysis_service.analyze_ticker(ticker,peer_mode='diagnostic',history_loader=history,
                                              fundamentals_loader=lambda _:deepcopy(FINANCIALS[ticker]))

    def without_peer(self,ticker):
        # Skip the append-only sidecar entirely, keeping the internal pipeline.
        with patch('analysis_service._attach_peer_diagnostics',side_effect=lambda result,*a,**k:result):
            return self.analyze(ticker)

    def with_peer(self,ticker,valid=False):
        p=PeerComparableResult(ticker,'synthetic',valid=valid,applicable=True,
                               low=1e6,mid=2e6,high=3e6,confidence='HIGH' if valid else 'UNAVAILABLE')
        with patch('peer_comparable.calculate_peer_comparable',return_value=p):
            return self.analyze(ticker)

    def assert_isolated(self,ticker,valid=False):
        off=self.without_peer(ticker)
        on=self.with_peer(ticker,valid)
        self.assertEqual(internal_snapshot(off),internal_snapshot(on))
        self.assertEqual(off['financials'],on['financials'])
        return off,on

    def test_01_nvda_diagnostic_on_off_identical(self):
        off,on=self.assert_isolated('NVDA',True)
        self.assertIsNotNone(off['fair_value'])
        self.assertEqual(off['blend']['reliability_governance_audit']['confidence_before'],'MEDIUM')
        self.assertIn(off['confidence'],('MEDIUM','LOW'))

    def test_02_avgo_diagnostic_on_off_identical(self):
        off,on=self.assert_isolated('AVGO',True)
        self.assertIsNotNone(off['fair_value'])

    def test_03_mu_unavailable_peer_keeps_cyclical_valuation(self):
        off,on=self.assert_isolated('MU')
        self.assertEqual(on['valuation_class'],'cyclical_semiconductor')
        self.assertIsNotNone(on['fair_value'])

    def test_04_pltr_unavailable_peer_preserves_low(self):
        off,on=self.assert_isolated('PLTR')
        self.assertEqual(on['confidence'],'LOW')
        self.assertEqual(on['valuation_mode'],'LOW_CONFIDENCE')

    def test_05_coin_unavailable_peer_preserves_valuation(self):
        off,on=self.assert_isolated('COIN')
        self.assertIsNotNone(on['fair_value'])

    def test_06_crcl_unavailable_peer_preserves_valuation(self):
        off,on=self.assert_isolated('CRCL')
        self.assertIsNotNone(on['fair_value'])

    def test_07_diagnostic_excluded_from_all_model_counts(self):
        off,on=self.assert_isolated('NVDA',True)
        self.assertNotIn('peer_comparable',on['blend']['models'])
        self.assertNotIn('peer_comparable',on['blend']['included_models'])
        for field in ['model_count_total','model_count_valid','model_count_included','model_count_excluded']:
            self.assertEqual(off['blend']['reliability'][field],on['blend']['reliability'][field])

    def test_08_diagnostic_excluded_from_dispersion_and_outliers(self):
        off,on=self.assert_isolated('NVDA',True)
        self.assertEqual(off['dispersion_pct'],on['dispersion_pct'])
        self.assertEqual(off['blend']['models'],on['blend']['models'])

    def test_09_diagnostic_excluded_from_reliability(self):
        off,on=self.assert_isolated('AVGO',True)
        self.assertEqual(off['blend']['reliability'],on['blend']['reliability'])

    def test_10_diagnostic_excluded_from_buy_exit_zones(self):
        off,on=self.assert_isolated('NVDA',True)
        self.assertIsNotNone(off['zones'])
        self.assertEqual(off['zones'],on['zones'])
        self.assertEqual(off['exit_zone'],on['exit_zone'])

    def test_only_two_peer_sidecar_fields_added(self):
        off,on=self.assert_isolated('NVDA')
        self.assertEqual(set(on)-set(off),{'peer_comparable_result','peer_diagnostics'})
        self.assertEqual(set(off)-set(on),set())

    def test_every_requested_ticker_preserves_internal_payload(self):
        for ticker in FINANCIALS:
            with self.subTest(ticker=ticker):self.assert_isolated(ticker,True)

    def test_mutating_diagnostic_cannot_clear_internal_financials(self):
        for ticker in ['NVDA','AVGO','MU','PLTR','COIN','CRCL']:
            with self.subTest(ticker=ticker):
                off=self.without_peer(ticker)
                def mutate(*args,**kwargs):
                    args[1].clear()
                    raise RuntimeError('Injected external failure')
                with patch('peer_comparable.calculate_peer_comparable',side_effect=mutate):on=self.analyze(ticker)
                self.assertEqual(internal_snapshot(off),internal_snapshot(on))
                self.assertEqual(off['financials'],on['financials'])
                self.assertEqual(on['peer_diagnostics']['status'],'UNAVAILABLE')

    def test_nested_diagnostic_input_mutation_is_isolated(self):
        off=self.without_peer('NVDA')
        def mutate(*args,**kwargs):
            args[1]['annual_cashflows'][0]['free_cash_flow']=0
            return PeerComparableResult('NVDA','semiconductor_growth')
        with patch('peer_comparable.calculate_peer_comparable',side_effect=mutate):on=self.analyze('NVDA')
        self.assertEqual(off['financials'],on['financials'])
        self.assertEqual(internal_snapshot(off),internal_snapshot(on))

    def test_diagnostic_runs_after_all_internal_display_fields(self):
        import market_reference
        events=[]
        original=market_reference.apply_reference_display_policy
        def policy(result):
            events.append('internal_display_complete')
            return original(result)
        def peer(*a,**k):
            self.assertEqual(events,['internal_display_complete'])
            events.append('peer')
            return PeerComparableResult('NVDA','semiconductor_growth')
        with patch('analysis_service.apply_reference_display_policy',side_effect=policy),patch('peer_comparable.calculate_peer_comparable',side_effect=peer):
            self.analyze('NVDA')
        self.assertEqual(events,['internal_display_complete','peer'])

    def test_serialization_or_import_failure_is_diagnostic_only(self):
        off=self.without_peer('NVDA')
        bad=Mock();bad.to_dict.side_effect=ValueError('bad external response')
        with patch('analysis_service._peer_result',return_value=bad):on=self.analyze('NVDA')
        self.assertEqual(internal_snapshot(off),internal_snapshot(on))
        with patch('analysis_service._peer_result',side_effect=ImportError('unavailable peer dependency')):on=self.analyze('NVDA')
        self.assertEqual(internal_snapshot(off),internal_snapshot(on))

    def test_peer_requirements_cannot_change_existing_eps_applicability(self):
        # Peer P/E rejects a price/forwardPE source; the original engine keeps
        # its own existing applicability rules, which this patch must preserve.
        f=deepcopy(FINANCIALS['NVDA']);f['forward_eps_source']='price/forwardPE'
        def reject(ticker,financials,*args,**kwargs):
            self.assertEqual(financials['forward_eps_source'],'price/forwardPE')
            return PeerComparableResult(ticker,'semiconductor_growth')
        kwargs=dict(peer_mode='diagnostic',history_loader=history,fundamentals_loader=lambda _:deepcopy(f))
        with patch('analysis_service._attach_peer_diagnostics',side_effect=lambda result,*a,**k:result):off=analysis_service.analyze_ticker('NVDA',**kwargs)
        with patch('peer_comparable.calculate_peer_comparable',side_effect=reject):on=analysis_service.analyze_ticker('NVDA',**kwargs)
        self.assertEqual(internal_snapshot(off),internal_snapshot(on))
        self.assertTrue(on['blend']['models']['forward_pe']['applicable'])


if __name__=='__main__':unittest.main()
