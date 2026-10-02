from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from financial_normalization import (
    CURRENCY_MISMATCH_REASON,
    FORWARD_AND_TRAILING_UNAVAILABLE,
    normalize_financials,
)
from mag7_monitor import fill_fundamental_fallbacks
from valuation_engine import valuate

from test_v41_regression import AAPL_FIN


def _cloud_wipe(fin: dict) -> dict:
    data = dict(fin)
    data["forward_eps"] = None
    data["forward_eps_source"] = None
    data["trailing_eps"] = None
    data["trailing_eps_source"] = None
    data["eps_proxy"] = None
    data["eps_proxy_source"] = None
    return fill_fundamental_fallbacks(data)


AVGO_CLOUD = {
    "historical_eps": [{"eps": 4.77, "shares": 4.85e9, "net_income": 23e9}],
    "shares": 4.77e9,
    "fcf": 19e9,
    "cash": 24e9,
    "debt": 59e9,
    "quote_currency": "USD",
    "financial_currency": "USD",
    "annual_cashflows": [
        {"free_cash_flow": 20e9},
        {"free_cash_flow": 18e9},
        {"free_cash_flow": 15e9},
    ],
}
NVDA_CLOUD = {
    "historical_eps": [{"eps": 4.9, "shares": 24.5e9}],
    "shares": 24.15e9,
    "fcf": 60e9,
    "cash": 62e9,
    "debt": 39e9,
    "quote_currency": "USD",
    "financial_currency": "USD",
    "annual_cashflows": [
        {"free_cash_flow": 60e9},
        {"free_cash_flow": 55e9},
        {"free_cash_flow": 50e9},
    ],
}
PLTR_CLOUD = {
    "historical_eps": [{"eps": 0.63, "shares": 2.56e9}],
    "shares": 2.3e9,
    "revenue": 6e9,
    "fcf": 1.1e9,
    "cash": 9e9,
    "debt": 0.2e9,
    "quote_currency": "USD",
    "financial_currency": "USD",
    "annual_cashflows": [
        {"free_cash_flow": 1.1e9},
        {"free_cash_flow": 0.9e9},
        {"free_cash_flow": 0.7e9},
    ],
}
MU_CLOUD = {
    "historical_eps": [{"eps": 7.59, "shares": 1.125e9}, {"eps": 0.7}, {"eps": 7.7}],
    "shares": 1.13e9,
    "ebitda": 108e9,
    "fcf": 0.12e9,
    "cash": 43e9,
    "debt": 5e9,
    "quote_currency": "USD",
    "financial_currency": "USD",
    "annual_cashflows": [
        {"free_cash_flow": 0.12e9},
        {"free_cash_flow": 1e9},
        {"free_cash_flow": -2e9},
    ],
}
AAPL_CLOUD = {
    "historical_eps": [{"eps": 7.46, "shares": 15e9}],
    "shares": 14.59e9,
    "fcf": 99e9,
    "cash": 62e9,
    "debt": 84e9,
    "quote_currency": "USD",
    "financial_currency": "USD",
    "annual_cashflows": [
        {"free_cash_flow": 100e9},
        {"free_cash_flow": 99e9},
        {"free_cash_flow": 98e9},
    ],
}
MSFT_CLOUD = {
    "historical_eps": [{"eps": 17.95, "shares": 7.45e9}],
    "shares": 7.43e9,
    "fcf": 71e9,
    "cash": 77e9,
    "debt": 129e9,
    "quote_currency": "USD",
    "financial_currency": "USD",
    "annual_cashflows": [
        {"free_cash_flow": 71e9},
        {"free_cash_flow": 65e9},
        {"free_cash_flow": 60e9},
    ],
}
BABA_CLOUD = {
    "historical_eps": [{"eps": 44.0, "shares": 2.4e9}],
    "shares": 2.49e9,
    "quote_currency": "USD",
    "financial_currency": "CNY",
    "fcf": 77e9,
    "cash": 385e9,
    "debt": 267e9,
}


class ProxyApplicabilityGuardTests(unittest.TestCase):
    def test_avgo_cloud_missing_eps_unavailable(self):
        blend = valuate("AVGO", _cloud_wipe(AVGO_CLOUD))
        self.assertEqual(blend["confidence"], "UNAVAILABLE")
        self.assertIsNone(blend["fair"])
        self.assertIsNone(blend["blended_mid"])
        self.assertEqual(blend["reason"], FORWARD_AND_TRAILING_UNAVAILABLE)
        pe = (blend.get("models") or {}).get("forward_pe") or {}
        self.assertEqual(pe.get("reason") or pe.get("applicability_reason"), FORWARD_AND_TRAILING_UNAVAILABLE)

    def test_nvda_cloud_missing_eps_unavailable(self):
        blend = valuate("NVDA", _cloud_wipe(NVDA_CLOUD))
        self.assertEqual(blend["confidence"], "UNAVAILABLE")
        self.assertIsNone(blend["fair"])
        self.assertEqual(blend["reason"], FORWARD_AND_TRAILING_UNAVAILABLE)

    def test_pltr_cloud_missing_eps_unavailable(self):
        blend = valuate("PLTR", _cloud_wipe(PLTR_CLOUD))
        self.assertEqual(blend["confidence"], "UNAVAILABLE")
        self.assertIsNone(blend["fair"])
        self.assertEqual(blend["reason"], FORWARD_AND_TRAILING_UNAVAILABLE)
        self.assertNotIn("revenue_multiple", blend.get("included") or [])

    def test_mu_cloud_missing_eps_unavailable(self):
        blend = valuate("MU", _cloud_wipe(MU_CLOUD))
        self.assertEqual(blend["confidence"], "UNAVAILABLE")
        self.assertIsNone(blend["fair"])
        self.assertEqual(blend["reason"], FORWARD_AND_TRAILING_UNAVAILABLE)

    def test_aapl_cloud_proxy_allowed_but_low(self):
        filled = _cloud_wipe(AAPL_CLOUD)
        self.assertEqual(filled.get("eps_proxy_source"), "statement_trailing_eps")
        blend = valuate("AAPL", filled)
        self.assertEqual(blend["confidence"], "LOW")
        self.assertIsNotNone(blend["fair"])
        pe = (blend.get("models") or {}).get("forward_pe") or {}
        self.assertEqual(pe.get("name"), "Trailing EPS Proxy P/E")
        self.assertTrue(pe.get("uses_proxy") or pe.get("eps_proxy"))
        self.assertIn("using_statement_derived_trailing_eps_proxy", pe.get("warnings") or [])
        full = valuate("AAPL", AAPL_FIN)
        self.assertLess(
            blend["reliability"]["reliability_score"],
            full["reliability"]["reliability_score"],
        )

    def test_msft_cloud_proxy_allowed_but_low(self):
        blend = valuate("MSFT", _cloud_wipe(MSFT_CLOUD))
        self.assertEqual(blend["confidence"], "LOW")
        self.assertIsNotNone(blend["fair"])
        pe = (blend.get("models") or {}).get("forward_pe") or {}
        self.assertEqual(pe.get("name"), "Trailing EPS Proxy P/E")
        self.assertTrue(pe.get("uses_proxy") or pe.get("eps_proxy"))

    def test_baba_currency_mismatch_unavailable(self):
        blend = valuate("BABA", _cloud_wipe(BABA_CLOUD))
        self.assertEqual(blend["confidence"], "UNAVAILABLE")
        self.assertIsNone(blend["fair"])
        pe = (blend.get("models") or {}).get("forward_pe") or {}
        self.assertEqual(pe.get("reason") or pe.get("applicability_reason"), CURRENCY_MISMATCH_REASON)

    def test_full_yahoo_forward_eps_path_unchanged(self):
        blend = valuate("AAPL", AAPL_FIN)
        pe = (blend.get("models") or {}).get("forward_pe") or {}
        self.assertEqual(pe.get("name"), "Forward P/E")
        self.assertFalse(pe.get("eps_proxy"))
        self.assertAlmostEqual(pe.get("inputs", {}).get("eps_used"), 9.58, places=2)
        self.assertEqual(blend["confidence"], "MEDIUM")
        self.assertIsNotNone(blend["blended_mid"])
        filled = normalize_financials(dict(AAPL_FIN))
        self.assertEqual(filled["forward_eps"], 9.58)
        self.assertIsNone(filled.get("eps_proxy"))


if __name__ == "__main__":
    unittest.main()
