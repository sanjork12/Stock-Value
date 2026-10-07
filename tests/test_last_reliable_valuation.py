from copy import deepcopy
from datetime import datetime, timezone, timedelta
import unittest
from unittest.mock import Mock, patch
import ast
from pathlib import Path

from analysis_service import analyze_ticker, build_snapshot_record, legacy_snapshot_record
from last_reliable_valuation import (apply_last_reliable, reliable_snapshot,
                                     resolve_live_result, render_cache_notice, DISPLAY_FIELDS)
from tests.test_peer_diagnostic_isolation import FINANCIALS
from scripts.verify_peer_isolation import history, internal_snapshot


NOW = datetime(2026, 10, 7, 12, tzinfo=timezone.utc)


def analyze(ticker='JPM', **changes):
    f = deepcopy(FINANCIALS[ticker])
    f.update(split_context_known=True, last_split_date=960000000, last_split_factor='2:1',
             quote_currency='USD', financial_currency='USD')
    f.update(changes)
    with patch('analysis_service._attach_peer_diagnostics', side_effect=lambda r, *a, **k: r):
        return analyze_ticker(ticker, history_loader=history, fundamentals_loader=lambda _: f)


class LastReliableTests(unittest.TestCase):
    def setUp(self):
        self.good = analyze()
        self.saved = reliable_snapshot(self.good, NOW)
        self.row = {'raw': {'last_reliable': self.saved}}
        self.missing = analyze(book_value_per_share=None, tangible_book_value_per_share=None)

    def fallback(self, result=None, now=NOW):
        return apply_last_reliable(result or self.missing, self.row, now)

    def test_live_success_saves_snapshot_without_changing_outputs(self):
        save, load = Mock(), Mock()
        result = resolve_live_result(self.good, load, save)
        save.assert_called_once()
        load.assert_not_called()
        self.assertEqual(internal_snapshot(result), internal_snapshot(self.good))
        record = build_snapshot_record('owner', result)
        saved = record['raw']['last_reliable']
        self.assertEqual(saved['source_status'], 'live')
        self.assertEqual(saved['buy_zones'], self.good['zones'])
        self.assertEqual(saved['exit_zones'], self.good['exit_zone'])
        self.assertEqual(len(saved['input_fingerprint']), 64)
        self.assertEqual(legacy_snapshot_record(record)['raw'], record['raw'])

    def test_actual_missing_bank_input_uses_fresh_snapshot(self):
        self.assertIsNone(self.missing['fair_value'])
        result = self.fallback(now=NOW + timedelta(hours=23, minutes=59))
        self.assertEqual(result['source_status'], 'cached_last_reliable')
        self.assertEqual(result['stale_reason'], 'current_financial_input_incomplete')
        for key in DISPLAY_FIELDS:
            self.assertEqual(result[key], self.good.get(key), key)
        self.assertEqual(result['financials'], self.missing['financials'])
        self.assertIsNone(result['current_live_valuation']['fair_value'])
        self.assertIsNone(reliable_snapshot(result))

    def test_expired_boundary_future_and_missing_rejected(self):
        for delta in (timedelta(hours=24), timedelta(hours=25), timedelta(seconds=-1)):
            with self.subTest(delta=delta):
                self.assertEqual(self.fallback(now=NOW+delta)['source_status'], 'live')
        for row in (None, {}, {'raw': {'last_reliable': {'calculated_at': 'bad'}}}):
            self.assertIsNone(apply_last_reliable(self.missing, row, NOW)['fair_value'])

    def test_currency_split_and_share_basis_mismatch_rejected(self):
        for key, value in (
            ('quote_currency', 'EUR'), ('financial_currency', 'EUR'),
            ('last_split_date', 970000000), ('last_split_factor', '10:1'),
            ('canonical_shares', self.good['financials']['canonical_shares'] * 1.11),
            ('canonical_shares_source', 'marketCap/price'),
            ('split_context_known', False), ('quote_currency', None),
            ('currency_mismatch', True),
        ):
            with self.subTest(field=key):
                result = deepcopy(self.missing)
                result['financials'][key] = value
                self.assertEqual(self.fallback(result)['source_status'], 'live')
        result = deepcopy(self.missing)
        result['ticker'] = 'OTHER'
        self.assertEqual(self.fallback(result)['source_status'], 'live')

    def test_economic_invalidity_and_guard_never_fallback(self):
        self.assertEqual(self.fallback(analyze(roe=-0.1))['source_status'], 'live')
        for reason in ('forward_and_trailing_eps_unavailable', 'specialized_valuation_required',
                       'fcf_conversion_unverified', 'currency_mismatch_without_fx_conversion',
                       'valuation_error', None):
            with self.subTest(reason=reason):
                result = deepcopy(self.missing)
                result['blend']['reason'] = reason
                self.assertEqual(self.fallback(result)['source_status'], 'live')
        result = deepcopy(self.missing)
        result['valuation_mode'] = 'SPECIALIZED'
        self.assertEqual(self.fallback(result)['source_status'], 'live')

    def test_model_shortage_without_disappearing_input_rejected(self):
        result = deepcopy(self.missing)
        for key in ('book_value_per_share', 'tangible_book_value_per_share'):
            result['financials'][key] = self.good['financials'][key]
        self.assertEqual(self.fallback(result)['source_status'], 'live')

    def test_new_model_guard_and_outlier_block_fallback(self):
        for reason in ('fcf_conversion_unverified', 'normalized_fcf_nonpositive',
                       'outlier_vs_other_models', 'missing_or_nonpositive_forward_eps'):
            result = deepcopy(self.missing)
            result['blend']['models']['price_to_book_roe']['reason'] = reason
            self.assertEqual(self.fallback(result)['source_status'], 'live')
        result = deepcopy(self.missing)
        result['blend']['models']['price_to_book_roe']['outlier'] = True
        self.assertEqual(self.fallback(result)['source_status'], 'live')

    def test_peer_diagnostics_independent(self):
        before = self.fallback()
        for valid in (True, False):
            result = deepcopy(self.missing)
            result['peer_comparable_result'] = {'valid': valid, 'mid': 999999}
            result['peer_diagnostics'] = {'mode': 'diagnostic'}
            after = self.fallback(result)
            self.assertEqual(internal_snapshot(before), internal_snapshot(after))
            self.assertEqual(after['peer_comparable_result'], result['peer_comparable_result'])

    def test_existing_ticker_outputs_unchanged(self):
        for ticker in FINANCIALS:
            with self.subTest(ticker=ticker):
                result = analyze(ticker)
                cached = apply_last_reliable(result, self.row, NOW)
                self.assertEqual(internal_snapshot(result), internal_snapshot(cached))

    def test_ui_notice_only_when_cached(self):
        ui = Mock()
        render_cache_notice(ui, self.good)
        ui.warning.assert_not_called()
        render_cache_notice(ui, self.fallback())
        self.assertIn('实时财务输入暂不完整，当前显示最近一次可靠估值。', ui.warning.call_args.args[0])
        self.assertIn(self.saved['calculated_at'], ui.caption.call_args.args[0])

    def app_functions(self, **overrides):
        # Load production storage functions without booting the authenticated UI.
        path = Path(__file__).resolve().parents[1] / 'streamlit_app.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                     and n.name in ('analyze_one', 'save_snapshot')]
        namespace = {'Client': object, 'date': datetime, 'analyze_ticker': Mock(return_value=self.good),
                     'history_cached': Mock(), 'fundamentals_cached': Mock(),
                     'assert_live_session': Mock(return_value='owner'),
                     'build_snapshot_record': build_snapshot_record,
                     'fetch_historical_snapshot': Mock(return_value=self.row),
                     'get_cloud_snapshot': Mock(return_value=self.row),
                     'is_rls_or_auth_error': lambda exc: False,
                     'is_schema_cache_error': lambda exc: False,
                     'legacy_snapshot_record': legacy_snapshot_record}
        namespace.update(overrides)
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), 'exec'), namespace)
        return namespace

    def test_storage_preserves_reliable_on_failed_same_day_upsert(self):
        app, db = self.app_functions(), Mock()
        app['save_snapshot'](db, 'owner', self.missing)
        payload = db.table.return_value.upsert.call_args.args[0]
        self.assertEqual(payload['raw']['last_reliable'], self.saved)
        app['assert_live_session'].assert_called_once_with(db, 'owner')
        db.reset_mock()
        app['save_snapshot'](db, 'owner', self.fallback())
        db.table.assert_not_called()

    def test_application_saves_success_even_without_dashboard_auto_save(self):
        app, db = self.app_functions(), Mock()
        result = app['analyze_one']('JPM', None, db, 'owner')
        self.assertEqual(result['source_status'], 'live')
        self.assertEqual(internal_snapshot(result), internal_snapshot(self.good))
        self.assertIsNotNone(db.table.return_value.upsert.call_args.args[0]['raw']['last_reliable'])

    def test_storage_failure_preserves_live_result_auth_error_propagates(self):
        app, db = self.app_functions(), Mock()
        db.table.side_effect = RuntimeError('storage offline')
        result = app['analyze_one']('JPM', None, db, 'owner')
        self.assertEqual(result['fair_value'], self.good['fair_value'])
        self.assertEqual(result['reliable_cache_status'], 'storage_unavailable')
        app = self.app_functions(is_rls_or_auth_error=lambda exc: True)
        with self.assertRaises(RuntimeError):
            app['analyze_one']('JPM', None, db, 'owner')


if __name__ == '__main__':
    unittest.main()
