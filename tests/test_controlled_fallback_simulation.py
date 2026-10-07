"""Controlled admin tests must not mix synthetic EPS loss with a new fetch."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import unittest
from unittest.mock import Mock, patch

import financial_forensics as forensics
from last_reliable_valuation import apply_last_reliable, reliable_snapshot
from scripts.verify_peer_isolation import history, internal_snapshot
from tests.test_single_source_valuation_inputs import amzn_inputs, analyze_amzn


class ControlledFallbackTests(unittest.TestCase):
    def setUp(self):
        self.provider=Mock()
        self.provider.get_diagnostic_basic_financials.return_value={'status':'NO_DATA','fields':{}}

    def capture(self,raw=None,**kwargs):
        return forensics.capture_financial_diagnostic('AMZN',history_loader=history,
            fundamentals_loader=lambda _:amzn_inputs() if raw is None else raw,
            finnhub_provider=self.provider,simulate_missing_input=True,**kwargs)

    def test_simulation_preserves_currency(self):
        baseline=analyze_amzn()
        _,simulation=forensics._controlled_eps_simulation(baseline)
        for key in ('quote_currency','financial_currency','currency_mismatch','fx_converted'):
            self.assertEqual(simulation['financials'].get(key),baseline['financials'].get(key))

    def test_simulation_preserves_share_basis_and_every_non_eps_field(self):
        baseline=analyze_amzn()
        original=deepcopy(baseline['financials'])
        _,simulation=forensics._controlled_eps_simulation(baseline)
        expected=deepcopy(original)
        expected.update(forward_eps=None,trailing_eps=None,eps_proxy=None,simulated_missing_input=True)
        self.assertEqual(simulation['financials'],expected)
        self.assertEqual(baseline['financials'],original)

    def test_simulation_makes_no_second_yahoo_or_history_call(self):
        fundamental_calls=[]
        def load(ticker):
            fundamental_calls.append(ticker)
            if len(fundamental_calls)>1:
                raise AssertionError('No second Yahoo request permitted')
            return amzn_inputs()
        history_loader=Mock(side_effect=history)
        simulated=[]
        report=forensics.capture_financial_diagnostic('AMZN',history_loader=history_loader,
            fundamentals_loader=load,finnhub_provider=self.provider,simulate_missing_input=True,
            result_sink=lambda r:simulated.append(r) or {})
        self.assertEqual(fundamental_calls,['AMZN'])
        history_loader.assert_called_once()
        self.assertEqual(report['baseline_valuation']['source_status'],'live')
        self.assertIsNotNone(report['baseline_valuation']['fair_value'])
        self.assertIsNone(simulated[0]['fair_value'])

    def test_incomplete_baseline_aborts_before_simulation_or_snapshot_read(self):
        for key,value in (('quote_currency',None),('financial_currency',None),
                          ('split_context_known',False),('forward_eps',None)):
            raw=amzn_inputs()
            raw[key]=value
            if key=='forward_eps':
                # An unavailable live baseline, rather than an EPS proxy that
                # is still legitimately usable during normal normalization.
                raw.update(trailing_eps=None,historical_eps=[],statement_eps=None)
            sink=Mock()
            with self.subTest(field=key),patch.object(forensics,'_controlled_eps_simulation') as simulation:
                report=self.capture(raw,result_sink=sink)
                self.assertTrue(report['simulation_aborted'])
                self.assertFalse(report['simulated_missing_input'])
                simulation.assert_not_called()
                sink.assert_not_called()
        baseline=analyze_amzn()
        for key in ('canonical_shares','canonical_shares_source'):
            incomplete=deepcopy(baseline)
            incomplete['financials'][key]=None
            self.assertFalse(forensics._controlled_baseline_available(incomplete))
        self.provider.get_diagnostic_basic_financials.assert_not_called()

    def test_baseline_network_failure_aborts_without_second_fetch(self):
        loader=Mock(side_effect=RuntimeError('simulated public-provider outage'))
        sink=Mock()
        with patch.object(forensics,'_controlled_eps_simulation') as simulation:
            report=forensics.capture_financial_diagnostic('AMZN',history_loader=history,
                fundamentals_loader=loader,finnhub_provider=self.provider,
                simulate_missing_input=True,result_sink=sink)
        self.assertTrue(report['simulation_aborted'])
        loader.assert_called_once()
        simulation.assert_not_called()
        sink.assert_not_called()

    def test_production_safety_rules_unchanged_and_controlled_cache_retains_time(self):
        baseline=analyze_amzn()
        stamp=datetime.now(timezone.utc)
        row={'raw':{'last_reliable':reliable_snapshot(baseline,stamp)}}
        original=deepcopy(row)
        _,simulation=forensics._controlled_eps_simulation(baseline)
        # Production still refuses this class of model-invalid unavailable.
        self.assertIsNone(apply_last_reliable(simulation,row,stamp)['fair_value'])
        restored=apply_last_reliable(simulation,row,stamp,_admin_simulated_missing=True)
        self.assertEqual(restored['source_status'],'cached_last_reliable')
        self.assertEqual(restored['calculated_at'],stamp.isoformat())
        self.assertEqual(internal_snapshot(restored),internal_snapshot(baseline))
        self.assertEqual(row,original)
        for key,value in (('quote_currency',None),('financial_currency','EUR'),
                          ('canonical_shares_source','other'),('split_context_known',False)):
            invalid=deepcopy(simulation)
            invalid['financials'][key]=value
            self.assertIsNone(apply_last_reliable(invalid,row,stamp,_admin_simulated_missing=True)['fair_value'])
        self.assertIsNone(apply_last_reliable(simulation,row,stamp+timedelta(hours=24),
                                             _admin_simulated_missing=True)['fair_value'])


if __name__=='__main__':unittest.main()
