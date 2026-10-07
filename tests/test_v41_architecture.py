from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis_service import (
    analyze_ticker,
    build_snapshot_record,
    is_schema_cache_error,
)
from mag7_monitor import fill_fundamental_fallbacks
from valuation_engine import valuate

from test_v41_regression import AAPL_FIN, _ohlcv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(name: str) -> str:
    with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
        return fh.read()


class FakeError(Exception):
    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.code = code


class ArchitectureCleanupTests(unittest.TestCase):
    def test_a_missing_forward_eps_does_not_mutate_forward_eps(self):
        fin = dict(AAPL_FIN)
        fin.pop("forward_eps", None)
        filled = fill_fundamental_fallbacks(fin)
        self.assertIsNone(filled.get("forward_eps"))
        self.assertEqual(filled.get("eps_proxy"), filled.get("trailing_eps"))
        self.assertEqual(filled.get("eps_proxy_source"), "trailing_eps")

    def test_b_proxy_eps_is_marked_and_lowers_reliability(self):
        fin = dict(AAPL_FIN)
        fin.pop("forward_eps", None)
        filled = fill_fundamental_fallbacks(fin)
        proxy_blend = valuate("AAPL", filled)
        full_blend = valuate("AAPL", AAPL_FIN)
        pe = (proxy_blend.get("models") or {}).get("forward_pe") or {}
        self.assertEqual(pe.get("name"), "Trailing EPS Proxy P/E")
        self.assertTrue(pe.get("eps_proxy"))
        self.assertIn("using_trailing_eps_proxy", pe.get("warnings") or [])
        self.assertNotEqual(proxy_blend["confidence"], "UNAVAILABLE")
        self.assertIsNotNone(proxy_blend["reliability"]["reliability_score"])
        self.assertLess(
            proxy_blend["reliability"]["reliability_score"],
            full_blend["reliability"]["reliability_score"],
        )

    def test_c_unavailable_reliability_score_is_none(self):
        blend = valuate("AAPL", {"shares": 14_594_180_000})
        self.assertEqual(blend["confidence"], "UNAVAILABLE")
        self.assertIsNone(blend["fair"])
        self.assertIsNone(blend["reliability"]["reliability_score"])
        self.assertIsNotNone(blend["reliability"].get("data_quality_score"))

    def test_d_specialized_snapshot_saved_with_null_fair(self):
        result = analyze_ticker(
            "BMNR",
            history_loader=lambda t, d: _ohlcv(26.73),
            fundamentals_loader=lambda t: {"forward_eps": 0.4, "shares": 1e9, "fcf": 1e8},
        )
        self.assertIsNone(result["confidence"])
        self.assertEqual(result["valuation_mode"], "SPECIALIZED")
        self.assertIsNone(result["fair"])
        self.assertEqual(result["price"], 26.73)
        row = build_snapshot_record("user-1", result)
        self.assertIsNone(row["fair_value"])
        self.assertEqual(row["price"], 26.73)
        self.assertEqual(row["sma30"], 25.73)
        self.assertEqual(row["confidence"], "SPECIALIZED")
        self.assertEqual(row["valuation_class"], "crypto_treasury")

    def test_e_non_schema_errors_never_trigger_legacy_fallback(self):
        self.assertTrue(is_schema_cache_error(FakeError("Could not find the 'reliability_score' column of 'valuation_snapshots' in the schema cache", "PGRST204")))
        self.assertTrue(is_schema_cache_error(FakeError("undefined column", "42703")))
        self.assertFalse(is_schema_cache_error(FakeError("new row violates row-level security policy", "42501")))
        self.assertFalse(is_schema_cache_error(FakeError("JWT expired")))
        self.assertFalse(is_schema_cache_error(TimeoutError("network timeout")))
        self.assertFalse(is_schema_cache_error(ConnectionError("connection reset")))

    def test_f_dashboard_retains_note_and_valuation_class(self):
        src = _read("streamlit_app.py")
        # Nickname / valuation_class still computed in row payload for notes / edit flows
        self.assertIn('"备注": item.get("nickname") or ""', src)
        self.assertIn("估值类型", src)
        self.assertIn("class_label_zh", src)
        dash_block = src.split("if page == \"自选股\":", 1)[1].split("elif page ==", 1)[0]
        self.assertIn('show_advanced_cols', dash_block)
        self.assertIn('更多指标', dash_block)
        # V5.2: advanced metrics are zone/SMA/reliability — not 备注/估值类型 columns
        self.assertIn('dashboard_columns.extend([', dash_block)
        self.assertIn('"第一批区"', dash_block)

    def test_f2_dashboard_default_column_order_decision_first(self):
        src = _read("streamlit_app.py")
        dash_block = src.split("if page == \"自选股\":", 1)[1].split("elif page ==", 1)[0]
        expected = [
            "股票",
            "价格",
            "状态",
            "内部估值",
            "市场一致目标",
            "内部 vs 市场",
            "估值模式",
            "距公允价值%",
            "核心买入区",
            "减仓参考区",
            "置信度",
        ]
        # Parse default dashboard_columns list before advanced extend.
        start = dash_block.find("dashboard_columns = [")
        self.assertGreaterEqual(start, 0)
        end = dash_block.find("]", start)
        block = dash_block[start:end]
        order = []
        for name in expected + ["错误", "备注", "估值类型", "第一批区"]:
            token = f'"{name}"'
            if token in block:
                order.append((block.find(token), name))
        order.sort()
        names = [n for _, n in order if n != "错误"]
        self.assertEqual(names, expected)
        self.assertNotIn("备注", names)
        self.assertNotIn("估值类型", names)
        self.assertIn('if show_advanced_cols:', dash_block)
        self.assertIn('更多指标', dash_block)
        # Valuation engine files remain untouched by this UI change path.
        self.assertNotIn("valuation_engine", dash_block)
        self.assertNotIn("financial_normalization", dash_block)

    def test_g_only_one_production_valuation_engine(self):
        monitor = _read("mag7_monitor.py")
        engine = _read("valuation_engine.py")
        for name in (
            "def pe_model",
            "def growth_model",
            "def apply_outlier_flags",
            "def blend_models",
            "def blended_fair",
            "def buy_zones",
            "def value_from_financials",
            "def sanity_snapshot",
        ):
            self.assertNotIn(name, monitor)
        self.assertIn("def valuate(", engine)
        self.assertNotIn("from mag7_monitor import", engine)
        self.assertIn("from valuation_primitives import", engine)
        self.assertFalse(os.path.exists(os.path.join(ROOT, "valuation_snapshots.json")))
        self.assertTrue(os.path.exists(os.path.join(ROOT, "tests", "fixtures", "legacy_valuation_snapshots.json")))

    def test_h_dashboard_and_single_stock_use_analysis_service(self):
        src = _read("streamlit_app.py")
        service = _read("analysis_service.py")
        self.assertGreaterEqual(src.count("analyze_one("), 2)
        self.assertIn("return analyze_ticker(", src)
        self.assertIn("r = analyze_one(t, None, db, user_id)", src)
        self.assertIn("r = analyze_one(current, as_of, db, user_id)", src)
        self.assertEqual(service.count("blend = valuate("), 1)


if __name__ == "__main__":
    unittest.main()
