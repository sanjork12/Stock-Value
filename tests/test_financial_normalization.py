from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from financial_normalization import (
    CLASS_SPECIFIC_SHARES,
    CURRENCY_MISMATCH_REASON,
    normalize_financials,
    resolve_canonical_shares,
    statement_inputs_currency_safe,
)
from mag7_monitor import fill_fundamental_fallbacks
from valuation_engine import check_dcf_applicable, build_profile, valuate

from test_v41_regression import AAPL_FIN


class FinancialNormalizationTests(unittest.TestCase):
    def test_1_statement_eps_never_mutates_forward_eps(self):
        fin = {
            "historical_eps": [{"eps": 7.46, "shares": 15_000_000_000, "net_income": 112e9}],
            "trailing_eps": None,
            "shares": 14_594_180_000,
            "quote_currency": "USD",
            "financial_currency": "USD",
        }
        filled = fill_fundamental_fallbacks(fin)
        self.assertIsNone(filled.get("forward_eps"))
        self.assertAlmostEqual(filled["statement_eps"], 7.46, places=2)
        self.assertEqual(filled["trailing_eps_source"], "statement_derived")
        self.assertEqual(filled["eps_proxy_source"], "statement_trailing_eps")
        self.assertNotEqual(filled.get("eps_proxy_source"), "forward_eps")
        blend = valuate("AAPL", filled)
        pe = (blend.get("models") or {}).get("forward_pe") or {}
        self.assertNotEqual(pe.get("name"), "Forward P/E")
        self.assertTrue(pe.get("uses_proxy") or pe.get("eps_proxy"))

    def test_2_currency_mismatch_blocks_statement_derived_eps_proxy(self):
        fin = {
            "quote_currency": "USD",
            "financial_currency": "CNY",
            "historical_eps": [{"eps": 43.08, "shares": 2_404_375_000, "net_income": 103.6e9}],
            "shares": 2_487_744_939,
        }
        filled = normalize_financials(fin)
        self.assertIsNone(filled.get("forward_eps"))
        self.assertAlmostEqual(filled["statement_eps"], 43.08, places=2)
        self.assertIsNone(filled.get("eps_proxy"))
        self.assertFalse(filled.get("eps_proxy_currency_safe"))
        self.assertIn(CURRENCY_MISMATCH_REASON, filled.get("warnings") or [])
        self.assertFalse(statement_inputs_currency_safe(filled))

    def test_3_baba_style_cny_usd_rejected_without_fx(self):
        fin = {
            "quote_currency": "USD",
            "financial_currency": "CNY",
            "statement_eps": 43.08,
            "historical_eps": [{"eps": 43.08, "shares": 2.4e9}],
            "fcf": 77.5e9,
            "revenue": 1.045e12,
            "ebitda": 99.5e9,
            "shares": 2.49e9,
            "cash": 385e9,
            "debt": 267e9,
            "annual_cashflows": [
                {"free_cash_flow": 80e9},
                {"free_cash_flow": 75e9},
                {"free_cash_flow": 70e9},
            ],
        }
        blend = valuate("BABA", fin)
        pe = (blend.get("models") or {}).get("forward_pe") or {}
        dcf = (blend.get("models") or {}).get("normalized_fcf_dcf") or {}
        self.assertFalse(pe.get("applicable"))
        self.assertEqual(pe.get("reason") or pe.get("applicability_reason"), CURRENCY_MISMATCH_REASON)
        self.assertFalse(pe.get("executed"))
        self.assertEqual(dcf.get("reason") or dcf.get("applicability_reason"), CURRENCY_MISMATCH_REASON)
        self.assertNotIn("forward_pe", blend.get("included") or [])
        self.assertNotIn("normalized_fcf_dcf", blend.get("included") or [])
        self.assertIsNone(pe.get("mid"))

    def test_4_dual_class_selects_canonical_total_company_shares(self):
        fin = {
            "shares_outstanding": 5_527_000_000,
            "implied_shares_outstanding": 12_229_934_831,
            "market_cap": 4_177_623_515_136,
            "current_price": 341.59,
            "quote_currency": "USD",
            "financial_currency": "USD",
        }
        resolved = resolve_canonical_shares(fin)
        self.assertGreater(resolved["canonical_shares"], 10e9)
        self.assertIn(resolved["canonical_shares_source"], {"impliedSharesOutstanding", "marketCap/price"})
        gap = abs(resolved["canonical_shares"] - 12_229_934_831) / 12_229_934_831
        self.assertLess(gap, 0.02)

    def test_5_goog_style_share_mismatch_triggers_warning(self):
        fin = {
            "shares": 5_527_000_000,
            "shares_outstanding": 5_527_000_000,
            "implied_shares_outstanding": 12_229_934_831,
            "market_cap": 4_177_623_515_136,
            "current_price": 341.59,
            "forward_eps": 15.07,
            "trailing_eps": 19.93,
            "fcf": 72.76e9,
            "cash": 242e9,
            "debt": 121e9,
            "quote_currency": "USD",
            "financial_currency": "USD",
            "annual_cashflows": [
                {"free_cash_flow": 70e9},
                {"free_cash_flow": 72e9},
                {"free_cash_flow": 74e9},
            ],
        }
        filled = normalize_financials(fin)
        self.assertIn(CLASS_SPECIFIC_SHARES, filled.get("warnings") or [])
        self.assertIn("share_count_warning", filled.get("warnings") or [])
        self.assertGreater(filled["canonical_shares"], 10e9)
        self.assertNotAlmostEqual(filled["canonical_shares"], 5_527_000_000, delta=1e8)
        blend = valuate("GOOG", filled)
        dcf = (blend.get("models") or {}).get("normalized_fcf_dcf") or {}
        if dcf.get("inputs") and dcf["inputs"].get("shares"):
            self.assertGreater(dcf["inputs"]["shares"], 10e9)

    def test_6_proxy_pe_name_is_not_forward_pe(self):
        fin = dict(AAPL_FIN)
        fin.pop("forward_eps", None)
        filled = fill_fundamental_fallbacks(fin)
        blend = valuate("AAPL", filled)
        pe = (blend.get("models") or {}).get("forward_pe") or {}
        self.assertEqual(pe.get("name"), "Trailing EPS Proxy P/E")
        self.assertNotEqual(pe.get("name"), "Forward P/E")
        self.assertTrue(pe.get("uses_proxy") or pe.get("eps_proxy"))
        self.assertEqual(pe.get("proxy_source") or pe.get("inputs", {}).get("proxy_source"), "trailing_eps")

    def test_7_proxy_use_lowers_confidence(self):
        fin = dict(AAPL_FIN)
        fin.pop("forward_eps", None)
        proxy = valuate("AAPL", fill_fundamental_fallbacks(fin))
        full = valuate("AAPL", AAPL_FIN)
        self.assertLess(
            proxy["reliability"]["reliability_score"],
            full["reliability"]["reliability_score"],
        )
        pe = (proxy.get("models") or {}).get("forward_pe") or {}
        growth = (proxy.get("models") or {}).get("growth_adjusted_pe") or {}
        self.assertEqual(str(pe.get("confidence") or "").lower(), "low")
        self.assertEqual(str(growth.get("confidence") or "").lower(), "low")

    def test_8_dcf_applicability_independent_of_pe_model_level(self):
        nvda_low_pe = {
            "historical_eps": [{"eps": 4.90, "shares": 24.5e9, "net_income": 120e9}],
            "shares": 24.15e9,
            "fcf": 60.85e9,
            "cash": 62.5e9,
            "debt": 38.9e9,
            "quote_currency": "USD",
            "financial_currency": "USD",
            "annual_cashflows": [
                {"free_cash_flow": 60e9},
                {"free_cash_flow": 55e9},
                {"free_cash_flow": 50e9},
            ],
            "fcf_method": "median_3y_annual",
        }
        profile = build_profile("NVDA", nvda_low_pe)
        filled = normalize_financials(nvda_low_pe)
        ok, reason, _, _ = check_dcf_applicable(profile, filled)
        self.assertFalse(ok)
        self.assertEqual(reason, "fcf_conversion_unverified")
        blend = valuate("NVDA", filled)
        self.assertNotIn("normalized_fcf_dcf", blend.get("included") or [])
        dcf = (blend.get("models") or {}).get("normalized_fcf_dcf") or {}
        self.assertNotEqual(dcf.get("reason"), "outlier_vs_other_models")
        self.assertEqual(dcf.get("reason") or dcf.get("applicability_reason"), "fcf_conversion_unverified")

        with_forward = dict(nvda_low_pe)
        with_forward["forward_eps"] = 15.70
        with_forward["trailing_eps"] = 7.92
        filled_fwd = normalize_financials(with_forward)
        ok_fwd, reason_fwd, _, diag = check_dcf_applicable(profile, filled_fwd)
        self.assertFalse(ok_fwd)
        self.assertEqual(reason_fwd, "fcf_conversion_too_low")
        self.assertIsNotNone(diag.get("eps_for_conversion"))
        self.assertGreaterEqual(diag["eps_for_conversion"], 7.0)

    def test_9_enterprise_valuation_blocked_on_unresolved_currency_mismatch(self):
        fin = {
            "quote_currency": "USD",
            "financial_currency": "CNY",
            "forward_eps": 9.23,
            "trailing_eps": 4.43,
            "fcf": 77.5e9,
            "revenue": 1.045e12,
            "ebitda": 99.5e9,
            "shares": 2.49e9,
            "cash": 385e9,
            "debt": 267e9,
            "annual_cashflows": [
                {"free_cash_flow": 80e9},
                {"free_cash_flow": 75e9},
                {"free_cash_flow": 70e9},
            ],
        }
        blend = valuate("BABA", fin)
        for model_id in ("normalized_fcf_dcf", "revenue_multiple"):
            obj = (blend.get("models") or {}).get(model_id) or {}
            if obj:
                self.assertEqual(obj.get("reason") or obj.get("applicability_reason"), CURRENCY_MISMATCH_REASON)
                self.assertFalse(obj.get("applicable"))
        self.assertNotIn("normalized_fcf_dcf", blend.get("included") or [])
        pe = (blend.get("models") or {}).get("forward_pe") or {}
        self.assertEqual(pe.get("name"), "Forward P/E")
        self.assertAlmostEqual(pe.get("inputs", {}).get("eps_used"), 9.23, places=2)

    def test_10_full_yahoo_forward_eps_path_unchanged(self):
        blend = valuate("AAPL", AAPL_FIN)
        pe = (blend.get("models") or {}).get("forward_pe") or {}
        self.assertEqual(pe.get("name"), "Forward P/E")
        self.assertFalse(pe.get("eps_proxy"))
        self.assertAlmostEqual(pe.get("inputs", {}).get("eps_used"), 9.58, places=2)
        self.assertIn("forward_pe", blend.get("included") or [])
        self.assertIsNotNone(blend.get("blended_mid"))
        self.assertNotEqual(blend.get("confidence"), "UNAVAILABLE")
        filled = fill_fundamental_fallbacks(dict(AAPL_FIN))
        self.assertEqual(filled["forward_eps"], 9.58)
        self.assertIsNone(filled.get("eps_proxy"))


if __name__ == "__main__":
    unittest.main()
