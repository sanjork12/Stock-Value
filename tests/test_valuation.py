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


if __name__ == "__main__":
    unittest.main()
