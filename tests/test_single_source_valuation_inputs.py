"""Regression: one normalized snapshot for pre-gates and actual model execution."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from analysis_service import analyze_ticker
from financial_forensics import capture_financial_diagnostic
from financial_normalization import normalize_financials, NormalizedFinancialInputs
from last_reliable_valuation import reliable_snapshot, apply_last_reliable
from scripts.verify_peer_isolation import history, internal_snapshot
import tests.test_peer_diagnostic_isolation as peer_tests
import valuation_engine as engine


def amzn_inputs():
    f=deepcopy(peer_tests.FINANCIALS['AMZN'])
    f.update(split_context_known=True,last_split_date=960000000,last_split_factor='2:1',
             fcf=7e9,annual_cashflows=[{'free_cash_flow':1e9},{'free_cash_flow':10e9},
                                     {'free_cash_flow':10e9}])
    return f


def analyze_amzn(simulate=False):
    with patch('analysis_service._attach_peer_diagnostics',side_effect=lambda r,*a,**k:r):
        return analyze_ticker('AMZN',history_loader=history,fundamentals_loader=lambda _:amzn_inputs(),
                              diagnostic_simulate_missing_eps=simulate)


class SingleSourceInputTests(unittest.TestCase):
    def missing_snapshot(self):
        f=normalize_financials(amzn_inputs())
        for key in ('forward_eps','trailing_eps','eps_proxy'):
            f[key]=None
        return f

    def assert_blocked(self,model):
        f=self.missing_snapshot()
        before=deepcopy(f)
        runner=Mock(side_effect=AssertionError('Blocked model must never run'))
        with patch.dict(engine.MODEL_RUNNERS,{model:runner}):
            result=engine.valuate('AMZN',f)
        runner.assert_not_called()
        self.assertFalse(result['models'][model]['executed'])
        self.assertFalse(result['models'][model]['valid'])
        self.assertNotIn(model,result['included_models'])
        self.assertEqual(f,before)

    def test_01_missing_eps_blocks_forward_pe_execution(self):
        self.assert_blocked('forward_pe')

    def test_02_missing_eps_blocks_growth_execution(self):
        self.assert_blocked('growth_adjusted_pe')

    def test_03_pre_gate_false_never_valid_executed_or_included(self):
        f=self.missing_snapshot()
        profile=engine.build_profile('AMZN',f)
        gates={k:engine.APPLICABILITY_GATES[k](profile,f)[0] for k in profile.preferred_models}
        result=engine.valuate('AMZN',f)
        engine.check_model_input_invariants(result['models'],result['included_models'],gates)
        for model,allowed in gates.items():
            if not allowed:
                self.assertFalse(result['models'][model]['valid'])
                self.assertFalse(result['models'][model]['executed'])
                self.assertNotIn(model,result['included_models'])
        for bad,included in (({'executed':True},[]),({'valid':True},[]),({},['forward_pe'])):
            with self.assertRaisesRegex(AssertionError,'pre_valuation_applicability_violation'):
                engine.check_model_input_invariants({'forward_pe':bad},included,{'forward_pe':False})

    def test_04_amzn_simulation_live_unavailable_with_distorted_dcf(self):
        result=analyze_amzn(True)
        self.assertIsNone(result['fair_value'])
        self.assertEqual(result['valuation_mode'],'UNAVAILABLE')
        self.assertEqual(result['blend']['models']['normalized_fcf_dcf']['reason'],'capex_or_fcf_distortion')
        self.assertEqual(result['blend']['included_models'],[])
        for key in ('forward_eps','trailing_eps','eps_proxy'):
            self.assertIsNone(result['financials'][key])
        provider=Mock()
        provider.get_diagnostic_basic_financials.return_value={'status':'NO_DATA','fields':{}}
        report=capture_financial_diagnostic('AMZN',history_loader=history,
            fundamentals_loader=lambda _:amzn_inputs(),finnhub_provider=provider,simulate_missing_input=True)
        for model in report['model_applicability']:
            if model['model_name'] in ('forward_pe','growth_adjusted_pe'):
                self.assertFalse(model['pre_valuation_applicable'])
                self.assertFalse(model['valid'])
                self.assertFalse(model['executed'])

    def cached(self):
        now=datetime.now(timezone.utc)
        saved=reliable_snapshot(analyze_amzn(),now)
        row={'raw':{'last_reliable':saved}}
        result=apply_last_reliable(analyze_amzn(True),row,now,_admin_simulated_missing=True)
        return result,row,now

    def test_05_amzn_simulation_reads_reliable_cache(self):
        result,row,_=self.cached()
        self.assertEqual(result['source_status'],'cached_last_reliable')
        saved=row['raw']['last_reliable']['valuation']
        for key in ('fair_value','blended_low','blended_mid','blended_high','zones','exit_zone'):
            self.assertEqual(result[key],saved[key],key)

    def test_06_cached_timestamp_is_original(self):
        result,row,now=self.cached()
        self.assertEqual(result['calculated_at'],row['raw']['last_reliable']['calculated_at'])
        self.assertEqual(result['calculated_at'],now.isoformat())

    def test_07_simulated_failure_and_cached_result_cannot_overwrite_reliable(self):
        result,row,now=self.cached()
        before=deepcopy(row)
        apply_last_reliable(analyze_amzn(True),row,now,_admin_simulated_missing=True)
        self.assertEqual(row,before)
        self.assertIsNone(reliable_snapshot(result))
        self.assertIsNone(reliable_snapshot(analyze_amzn(True)))
        # The same EPS failure is still refused by the production cache policy.
        self.assertIsNone(apply_last_reliable(analyze_amzn(True),row,now)['fair_value'])

    def test_08_simulation_off_restores_identical_live_output(self):
        before=analyze_amzn()
        analyze_amzn(True)
        after=analyze_amzn()
        self.assertEqual(internal_snapshot(before),internal_snapshot(after))
        self.assertIsNotNone(after['fair_value'])
        self.assertNotIn('simulated_missing_input',after)

    def test_09_all_pre_fix_regression_snapshots_unchanged(self):
        fixture=Path(__file__).parent/'fixtures/input_path_pre_fix_hashes.json'
        baseline=json.loads(fixture.read_text(encoding='utf-8'))['tickers']
        helper=peer_tests.DiagnosticIsolationTests()
        for ticker,expected in baseline.items():
            with self.subTest(ticker=ticker):
                # Freeze the pre-V4.6 valuation payload; reliability/confidence
                # changes are separately covered by production governance tests.
                with patch('production_reliability_governance.govern_blend',side_effect=lambda t,f,b:b):
                    output=internal_snapshot(helper.without_peer(ticker))
                digest=hashlib.sha256(json.dumps(output,sort_keys=True).encode()).hexdigest()
                self.assertEqual(digest,expected)

    def test_serialized_explicit_null_snapshot_does_not_restore_statement_eps(self):
        f=dict(self.missing_snapshot())
        self.assertTrue(f.get('historical_eps'))
        result=engine.valuate('AMZN',f)
        self.assertFalse(result['models']['forward_pe']['executed'])
        self.assertFalse(result['models']['growth_adjusted_pe']['executed'])
        self.assertIsNone(result['fair_value'])

    def test_documented_statement_fallback_is_explicit_before_gate(self):
        raw=amzn_inputs()
        raw['forward_eps']=raw['trailing_eps']=None
        f=normalize_financials(raw)
        self.assertIsInstance(f,NormalizedFinancialInputs)
        self.assertIsNotNone(f['eps_proxy'])
        self.assertEqual(f['eps_proxy_source'],'statement_trailing_eps')
        profile=engine.build_profile('AMZN',f)
        self.assertTrue(engine.APPLICABILITY_GATES['forward_pe'](profile,f)[0])
        self.assertTrue(engine.valuate('AMZN',f)['models']['forward_pe']['valid'])


if __name__=='__main__':unittest.main()
