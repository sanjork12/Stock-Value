from __future__ import annotations

import math
import os
import sys
import unittest

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mag7_monitor import (
    blend_models,
    buy_zones,
    dcf_model,
    growth_model,
    model_result,
    normalize_capex,
    pe_model,
    range_is_ordered,
    structural_valid,
    _yearly_cashflows,
)


class ValuationGuardTests(unittest.TestCase):
    def test_normalize_capex_sign(self):
        self.assertEqual(normalize_capex(-30), 30)
        self.assertEqual(normalize_capex(30), 30)
        self.assertIsNone(normalize_capex(None))

    def test_fcf_from_ocf_minus_normalized_capex(self):
        df = pd.DataFrame(
            {
                "2025-12-31": {
                    "Operating Cash Flow": 100.0,
                    "Capital Expenditure": -30.0,
                    "Free Cash Flow": 70.0,
                }
            }
        )
        rows = _yearly_cashflows(df)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["capital_expenditure"], 30.0)
        self.assertEqual(rows[0]["free_cash_flow_computed"], 70.0)

    def test_amzn1_negative_equity_is_invalid(self):
        dcf = dcf_model(
            "AMZN",
            fcf=3_219_124_992,
            shares=10_786_313_572,
            cash=122_988_003_328,
            debt=251_635_007_488,
        )
        self.assertFalse(dcf["valid"])
        self.assertEqual(dcf["reason"], "negative_equity_value")
        self.assertIsNone(dcf["low"])
        self.assertIsNone(dcf["mid"])
        self.assertIsNone(dcf["high"])

    def test_amzn2_invalid_dcf_not_in_blend(self):
        pe = pe_model("AMZN", 10.47571)
        growth = growth_model("AMZN", 10.47571, live_growth=2.423)
        dcf = dcf_model(
            "AMZN",
            fcf=3_219_124_992,
            shares=10_786_313_572,
            cash=122_988_003_328,
            debt=251_635_007_488,
        )
        blend = blend_models(pe, dcf, growth)
        self.assertNotIn("dcf", blend["included"])
        self.assertIn("pe", blend["included"])
        self.assertIn("growth", blend["included"])

    def test_amzn3_blend_uses_pe_and_growth_only(self):
        pe = pe_model("AMZN", 10.47571)
        growth = growth_model("AMZN", 10.47571, live_growth=2.423)
        dcf = model_result("DCF", valid=False, reason="negative_equity_value")
        blend = blend_models(pe, dcf, growth)
        self.assertGreaterEqual(blend["fair"], 300)
        self.assertLessEqual(blend["fair"], 320)
        self.assertEqual(set(blend["included"]), {"pe", "growth"})

    def test_amzn4_buy_zones_not_crushed(self):
        pe = pe_model("AMZN", 10.47571)
        growth = growth_model("AMZN", 10.47571, live_growth=2.423)
        dcf = model_result("DCF", valid=False, reason="negative_equity_value")
        fair = blend_models(pe, dcf, growth)["fair"]
        zones = buy_zones(fair)
        self.assertIsNotNone(zones)
        self.assertGreater(zones["deep"][0], 170)
        self.assertGreater(zones["first"][0], 200)

    def test_amzn5_valid_models_ordered(self):
        pe = pe_model("AMZN", 10.47571)
        growth = growth_model("AMZN", 10.47571, live_growth=2.423)
        dcf = dcf_model("AMZN", fcf=32_000_000_000, shares=10_786_313_572, cash=123_000_000_000, debt=150_000_000_000)
        for obj in (pe, growth, dcf):
            if structural_valid(obj):
                self.assertTrue(range_is_ordered(obj["low"], obj["mid"], obj["high"]))

    def test_amzn6_nan_inf_invalid(self):
        nan_model = dcf_model("AMZN", fcf=float("nan"), shares=1e10, cash=1e9, debt=1e9)
        inf_model = dcf_model("AMZN", fcf=float("inf"), shares=1e10, cash=1e9, debt=1e9)
        self.assertFalse(nan_model["valid"])
        self.assertFalse(inf_model["valid"])
        self.assertFalse(structural_valid(model_result("P/E", valid=True, low=1, mid=float("nan"), high=2)))

    def test_amzn7_single_valid_model_no_blend_or_zones(self):
        pe = pe_model("AMZN", 10.47571)
        dcf = model_result("DCF", valid=False, reason="negative_equity_value")
        growth = model_result("Growth / PEG", valid=False, reason="missing_or_nonpositive_forward_eps")
        blend = blend_models(pe, dcf, growth)
        self.assertTrue(blend["insufficient_models"])
        self.assertIsNone(blend["fair"])
        self.assertIsNone(buy_zones(blend["fair"]))

    def test_negative_range_not_wrapped(self):
        bad = model_result("DCF", valid=True, low=-3.45, mid=-4.05, high=-4.66)
        self.assertFalse(bad["valid"])
        self.assertFalse(range_is_ordered(bad["low"], bad["mid"], bad["high"]))

    def test_outlier_dcf_excluded(self):
        pe = model_result("P/E", valid=True, low=280, mid=309, high=335)
        growth = model_result("Growth / PEG", valid=True, low=276, mid=314, high=352)
        dcf = model_result("DCF", valid=True, low=3, mid=4, high=5)
        blend = blend_models(pe, dcf, growth)
        self.assertNotIn("dcf", blend["included"])
        self.assertTrue(blend["models"]["dcf"]["outlier"])
        self.assertGreaterEqual(blend["fair"], 300)
        self.assertLessEqual(blend["fair"], 320)


class V4SectorAwareTests(unittest.TestCase):
    def test_ticker_normalize(self):
        from valuation_engine import normalize_ticker
        self.assertEqual(normalize_ticker(" amzn "), "AMZN")
        self.assertEqual(normalize_ticker("BRK.B"), "BRK.B")
        self.assertIsNone(normalize_ticker("DROP TABLE"))
        self.assertIsNone(normalize_ticker(""))
        self.assertIsNone(normalize_ticker("this-is-way-too-long-ticker"))

    def test_override_classes(self):
        from valuation_engine import build_profile
        expected = {
            "AAPL": "mega_cap_tech",
            "MSFT": "mega_cap_tech",
            "GOOG": "mega_cap_tech",
            "AMZN": "mega_cap_tech",
            "META": "mega_cap_tech",
            "NVDA": "semiconductor_growth",
            "AVGO": "semiconductor_growth",
            "MU": "cyclical_semiconductor",
            "JPM": "bank",
            "COIN": "fintech_exchange",
            "BMNR": "crypto_treasury",
            "PLTR": "high_growth_software",
            "SPCX": "space_optionality",
            "TSLA": "auto_optionality",
            "TEM": "pre_profit_growth",
            "UBER": "mature_growth",
            "NFLX": "consumer_platform",
            "BABA": "consumer_platform",
            "ORCL": "mature_growth",
        }
        for ticker, vclass in expected.items():
            self.assertEqual(build_profile(ticker).valuation_class, vclass)

    def test_infer_not_only_sector(self):
        from valuation_engine import infer_valuation_class
        growth_semi = infer_valuation_class("FAKE1", {"industry": "Semiconductors", "earnings_growth": 0.55, "forward_eps": 5, "fcf": 1})
        memory_semi = infer_valuation_class("FAKE2", {"industry": "Semiconductors - DRAM / Memory", "earnings_growth": 2.0, "forward_eps": 5, "fcf": 1})
        self.assertEqual(growth_semi, "semiconductor_growth")
        self.assertEqual(memory_semi, "cyclical_semiconductor")

    def test_mu_rebound_growth_not_four_thousand(self):
        from valuation_engine import valuate, can_emit_buy_zones
        financials = {
            "forward_eps": 8.4,
            "trailing_eps": 0.42,
            "earnings_growth": 4.2,
            "historical_eps": [{"eps": 0.8}, {"eps": 1.1}, {"eps": 2.0}, {"eps": 4.5}],
            "ebitda": 15_000_000_000,
            "revenue": 30_000_000_000,
            "shares": 1_120_000_000,
            "cash": 10_000_000_000,
            "debt": 15_000_000_000,
            "fcf": 5_000_000_000,
            "fcf_method": "median_3y",
            "sector": "Technology",
            "industry": "Semiconductors",
        }
        blend = valuate("MU", financials)
        self.assertEqual(blend["profile"]["valuation_class"], "cyclical_semiconductor")
        self.assertNotIn("growth_adjusted_pe", blend["included"])
        self.assertIsNotNone(blend["fair"])
        self.assertLess(blend["fair"], 400)
        self.assertGreater(blend["fair"], 10)
        self.assertTrue(can_emit_buy_zones(blend))

    def test_history_eps_scale_mismatch_ignored(self):
        from valuation_engine import valuate
        financials = {
            "forward_eps": 80.0,
            "trailing_eps": 70.0,
            "earnings_growth": 10.0,
            "historical_eps": [{"eps": 0.8}, {"eps": 1.1}, {"eps": 7.5}],
            "ebitda": 20_000_000_000,
            "shares": 1_120_000_000,
            "cash": 10_000_000_000,
            "debt": 15_000_000_000,
            "fcf": 5_000_000_000,
            "fcf_method": "median_3y",
        }
        blend = valuate("MU", financials)
        self.assertNotEqual(blend.get("fair"), None)
        self.assertLess(blend["fair"], 2500)

    def test_jpm_excludes_corporate_dcf(self):
        from valuation_engine import valuate
        financials = {
            "book_value_per_share": 120,
            "tangible_book_value_per_share": 90,
            "roe": 0.16,
            "forward_eps": 20,
            "trailing_eps": 18,
            "earnings_growth": 0.08,
            "fcf": 50_000_000_000,
            "shares": 2_800_000_000,
            "cash": 1_000_000_000_000,
            "debt": 800_000_000_000,
            "sector": "Financial Services",
            "industry": "Banks - Diversified",
        }
        blend = valuate("JPM", financials)
        self.assertEqual(blend["profile"]["valuation_class"], "bank")
        self.assertNotIn("normalized_fcf_dcf", blend["included"])
        excluded_names = {item["name"] for item in blend["excluded"]}
        self.assertIn("normalized_fcf_dcf", excluded_names)
        self.assertIsNotNone(blend["fair"])
        self.assertLess(blend["fair"], 400)
        self.assertGreater(blend["fair"], 80)
        self.assertIn("price_to_book_roe", blend["included"])
        self.assertIn("residual_income", blend["included"])

    def test_nvda_caps_extreme_growth(self):
        from valuation_engine import valuate
        financials = {
            "forward_eps": 6.5,
            "trailing_eps": 2.8,
            "earnings_growth": 1.20,
            "fcf": 60_000_000_000,
            "shares": 24_500_000_000,
            "cash": 40_000_000_000,
            "debt": 10_000_000_000,
            "fcf_method": "median_3y",
            "sector": "Technology",
            "industry": "Semiconductors",
        }
        blend = valuate("NVDA", financials)
        growth = blend["models"]["growth_adjusted_pe"]
        self.assertLessEqual(growth["inputs"]["growth_used"], 0.18)
        self.assertLess(blend["fair"], 400)
        self.assertGreater(blend["fair"], 50)

    def test_specialized_tickers_return_none(self):
        from valuation_engine import valuate, can_emit_buy_zones
        dummy = {
            "forward_eps": 3.0,
            "trailing_eps": 2.0,
            "fcf": 10_000_000_000,
            "shares": 3_000_000_000,
            "cash": 20_000_000_000,
            "debt": 10_000_000_000,
        }
        for ticker, vclass in (
            ("TSLA", "auto_optionality"),
            ("SPCX", "space_optionality"),
            ("BMNR", "crypto_treasury"),
            ("TEM", "pre_profit_growth"),
        ):
            fin = dict(dummy)
            if ticker == "TEM":
                fin["forward_eps"] = -1.0
                fin["trailing_eps"] = -1.0
                fin["fcf"] = -500_000_000
            blend = valuate(ticker, fin)
            self.assertEqual(blend["profile"]["valuation_class"], vclass)
            self.assertIsNone(blend["fair"])
            self.assertIn(blend["confidence"], {"SPECIALIZED", "UNAVAILABLE"})
            self.assertFalse(can_emit_buy_zones(blend))

    def test_pltr_low_confidence_policy(self):
        from valuation_engine import valuate
        financials = {
            "forward_eps": 0.55,
            "trailing_eps": 0.20,
            "earnings_growth": 0.40,
            "revenue": 3_000_000_000,
            "fcf": 1_200_000_000,
            "shares": 2_300_000_000,
            "cash": 4_000_000_000,
            "debt": 200_000_000,
            "fcf_method": "median_3y",
        }
        blend = valuate("PLTR", financials)
        self.assertEqual(blend["profile"]["valuation_class"], "high_growth_software")
        if blend["fair"] is not None:
            self.assertEqual(blend["confidence"], "LOW")

    def test_coin_low_confidence(self):
        from valuation_engine import valuate
        financials = {
            "forward_eps": 5.0,
            "trailing_eps": 2.0,
            "earnings_growth": 0.30,
            "ebitda": 2_000_000_000,
            "revenue": 6_000_000_000,
            "shares": 250_000_000,
            "cash": 8_000_000_000,
            "debt": 4_000_000_000,
        }
        blend = valuate("COIN", financials)
        self.assertEqual(blend["profile"]["valuation_class"], "fintech_exchange")
        if blend["fair"] is not None:
            self.assertEqual(blend["confidence"], "LOW")

    def test_two_models_required_for_blend(self):
        from valuation_engine import valuate, can_emit_buy_zones
        financials = {
            "forward_eps": None,
            "trailing_eps": None,
            "fcf": 1_000_000_000,
            "shares": 1_000_000_000,
            "cash": 5_000_000_000,
            "debt": 1_000_000_000,
            "fcf_method": "median_3y",
        }
        blend = valuate("ORCL", financials)
        self.assertTrue(blend["insufficient_models"])
        self.assertIsNone(blend["fair"])
        self.assertFalse(can_emit_buy_zones(blend))

    def test_buy_zones_not_from_sma_alone(self):
        from mag7_monitor import buy_zones
        from valuation_engine import can_emit_buy_zones
        self.assertFalse(can_emit_buy_zones({"fair": None, "included": [], "confidence": "UNAVAILABLE"}))
        self.assertFalse(can_emit_buy_zones({"fair": 100, "included": ["forward_pe"], "confidence": "MEDIUM", "insufficient_models": True}))
        self.assertIsNone(buy_zones(None, technical_mid=180, sma200=170))


if __name__ == "__main__":
    unittest.main()
