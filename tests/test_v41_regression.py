from __future__ import annotations

import os
import sys
import unittest

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis_service import analyze_ticker, format_fair_value
from mag7_monitor import fill_fundamental_fallbacks, flatten_yahoo_ohlcv
from valuation_engine import check_valuation_invariants, valuate


AAPL_FIN = {
    "forward_eps": 9.58,
    "trailing_eps": 8.73,
    "shares": 14_594_180_000,
    "fcf": 99_584_000_000,
    "cash": 62_399_000_576,
    "debt": 84_343_996_416,
    "market_cap": 4.8e12,
    "annual_cashflows": [
        {"free_cash_flow": 100e9, "period": "FY2025"},
        {"free_cash_flow": 99e9, "period": "FY2024"},
        {"free_cash_flow": 98e9, "period": "FY2023"},
    ],
}
JPM_FIN = {
    "forward_eps": 24.99,
    "trailing_eps": 23.32,
    "shares": 2_658_186_195,
    "book_value_per_share": 133.0,
    "tangible_book_value_per_share": 110.0,
    "roe": 0.178,
    "cash": 1.5e12,
    "debt": 1.3e12,
    "historical_eps": [{"eps": 22}, {"eps": 21}, {"eps": 20}, {"eps": 18}],
}
COIN_FIN = {
    "forward_eps": 2.84,
    "trailing_eps": 3.2,
    "shares": 222_803_032,
    "ebitda": 2.5e9,
    "enterprise_value": 40e9,
    "revenue": 6e9,
    "cash": 8.8e9,
    "debt": 6.7e9,
    "historical_eps": [{"eps": 3.0}, {"eps": 2.5}, {"eps": 1.8}],
}


def _ohlcv(close=100.0):
    idx = pd.date_range("2025-01-02", periods=260, freq="B")
    return pd.DataFrame(
        {
            "Open": close,
            "High": close + 1,
            "Low": close - 1,
            "Close": close,
            "Volume": 1_000_000,
            "SMA30": close - 1,
            "SMA50": close - 2,
            "SMA200": close - 5,
        },
        index=idx,
    )


class V41RegressionTests(unittest.TestCase):
    def test_1_aapl_two_plus_models_not_unavailable(self):
        blend = valuate("AAPL", AAPL_FIN)
        self.assertGreaterEqual(len(blend["included"]), 2)
        self.assertIsNotNone(blend["blended_mid"])
        self.assertEqual(blend["blended_mid"], blend["fair_value"])
        self.assertEqual(blend["fair"], blend["fair_value"])
        self.assertNotEqual(blend["confidence"], "UNAVAILABLE")

    def test_2_jpm_bank_fair_not_none(self):
        blend = valuate("JPM", JPM_FIN)
        self.assertGreaterEqual(len(blend["included"]), 2)
        self.assertIsNotNone(blend["fair"])
        self.assertNotEqual(blend["confidence"], "UNAVAILABLE")

    def test_3_coin_low_has_indicative_range(self):
        blend = valuate("COIN", COIN_FIN)
        self.assertEqual(blend["confidence"], "LOW")
        self.assertIsNotNone(blend["blended_low"])
        self.assertIsNotNone(blend["blended_high"])
        text = format_fair_value({
            "confidence": blend["confidence"],
            "blended_mid": blend["blended_mid"],
            "blended_low": blend["blended_low"],
            "blended_high": blend["blended_high"],
        })
        self.assertIn("–", text)

    def test_4_spcx_specialized_fair_none(self):
        blend = valuate("SPCX", {"forward_eps": 1, "shares": 1e9, "fcf": 1e8})
        self.assertEqual(blend["confidence"], "SPECIALIZED")
        self.assertIsNone(blend["fair"])
        self.assertIsNone(blend["blended_mid"])

    def test_5_reliability_two_models_not_unavailable(self):
        blend = valuate("AAPL", AAPL_FIN)
        score = blend["reliability"]["reliability_score"]
        self.assertIsNotNone(score)
        self.assertGreaterEqual(score, 40)
        self.assertGreaterEqual(len(blend["included"]), 2)
        self.assertNotEqual(blend["confidence"], "UNAVAILABLE")
        self.assertEqual(check_valuation_invariants(blend, strict=True), [])

    def test_6_fundamentals_failure_keeps_ohlcv(self):
        def boom(_ticker):
            raise RuntimeError("yahoo fundamentals down")

        result = analyze_ticker(
            "AMZN",
            history_loader=lambda t, d: _ohlcv(248.0),
            fundamentals_loader=boom,
        )
        self.assertEqual(result["price"], 248.0)
        self.assertEqual(result["sma50"], 246.0)
        self.assertTrue(result["errors"])
        self.assertEqual(result["errors"][0]["stage"], "fundamentals")

    def test_7_dashboard_and_single_share_formatter(self):
        blend = valuate("AAPL", AAPL_FIN)
        dashboard = format_fair_value({
            "confidence": blend["confidence"],
            "blended_mid": blend["blended_mid"],
            "fair": blend["fair"],
            "blended_low": blend["blended_low"],
            "blended_high": blend["blended_high"],
        })
        single = format_fair_value({
            "confidence": blend["overall_confidence"],
            "fair_value": blend["fair_value"],
            "fair_low": blend["fair_low"],
            "fair_high": blend["fair_high"],
        })
        self.assertEqual(dashboard, single)
        self.assertNotEqual(dashboard, "—")

    def test_8_blended_mid_aliases_fair_value(self):
        blend = valuate("AAPL", AAPL_FIN)
        self.assertEqual(blend["blended_mid"], blend["fair"])
        self.assertEqual(blend["blended_mid"], blend["fair_value"])
        result = analyze_ticker(
            "AAPL",
            history_loader=lambda t, d: _ohlcv(330.0),
            fundamentals_loader=lambda t: AAPL_FIN,
        )
        self.assertEqual(result["blended_mid"], result["fair"])
        self.assertEqual(result["fair"], result["fair_value"])

    def test_empty_info_reproduces_unavailable_82(self):
        blend = valuate("AAPL", {"shares": 14_594_180_000})
        self.assertEqual(blend["confidence"], "UNAVAILABLE")
        self.assertEqual(blend["reliability"]["reliability_score"], 82)
        self.assertIsNone(blend["fair"])

    def test_trailing_eps_fallback_emits_fair(self):
        fin = dict(AAPL_FIN)
        fin.pop("forward_eps", None)
        filled = fill_fundamental_fallbacks(fin)
        self.assertEqual(filled["forward_eps"], filled["trailing_eps"])
        blend = valuate("AAPL", filled)
        self.assertIsNotNone(blend["blended_mid"])
        self.assertNotEqual(blend["confidence"], "UNAVAILABLE")
        self.assertGreaterEqual(len(blend["included"]), 2)

    def test_jpm_roe_from_book_and_trailing(self):
        fin = dict(JPM_FIN)
        fin.pop("roe", None)
        fin.pop("forward_eps", None)
        filled = fill_fundamental_fallbacks(fin)
        self.assertIsNotNone(filled.get("roe"))
        self.assertEqual(filled["forward_eps"], filled["trailing_eps"])
        blend = valuate("JPM", filled)
        self.assertIsNotNone(blend["blended_mid"])
        self.assertNotEqual(blend["confidence"], "UNAVAILABLE")

    def test_flatten_ticker_first_multiindex(self):
        idx = pd.date_range("2025-01-02", periods=3, freq="B")
        cols = pd.MultiIndex.from_product([["AMZN"], ["Open", "High", "Low", "Close", "Volume"]])
        raw = pd.DataFrame([[1, 2, 0.5, 1.5, 10]] * 3, index=idx, columns=cols)
        out = flatten_yahoo_ohlcv(raw)
        self.assertIn("Close", out.columns)
        self.assertEqual(float(out["Close"].iloc[0]), 1.5)


if __name__ == "__main__":
    unittest.main()
