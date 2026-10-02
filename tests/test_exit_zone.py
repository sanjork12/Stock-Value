from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis_service import (
    _recommendation_label,
    analyze_ticker,
    build_snapshot_record,
    format_extreme_zone,
    format_trim_zone,
)
from valuation_engine import (
    MODEL_VERSION,
    can_emit_exit_zones,
    dynamic_overvaluation_profile,
    exit_zone_from_snapshot,
    reconstruct_blend_from_snapshot,
)


def _profile(**kwargs):
    base = dict(
        blended_low=270,
        blended_mid=300,
        blended_high=330,
        confidence="MEDIUM",
        reliability_score=75,
        dispersion_pct=0.10,
        volatility_1y=0.20,
        cyclicality="low",
        valuation_class="mega_cap_tech",
    )
    base.update(kwargs)
    return dynamic_overvaluation_profile(**base)


class ExitZoneCoreTests(unittest.TestCase):
    def test_1_high_confidence_emits_exit_zones(self):
        ez = _profile(confidence="HIGH")
        self.assertIsNotNone(ez)
        self.assertGreater(ez["hold_upper_price"], 0)
        self.assertGreater(ez["trim_price"], ez["hold_upper_price"])
        self.assertGreater(ez["extreme_price"], ez["trim_price"])

    def test_2_medium_confidence_emits_exit_zones(self):
        ez = _profile(confidence="MEDIUM")
        self.assertIsNotNone(ez)
        self.assertIn("hold_upper_pct", ez)
        self.assertIn("trim_price", ez)

    def test_3_low_confidence_no_precise_exit_zones(self):
        ez = _profile(confidence="LOW")
        self.assertIsNone(ez)
        self.assertFalse(
            can_emit_exit_zones(
                {"confidence": "LOW", "blended_mid": 300, "blended_high": 330, "fair": 300, "fair_high": 330}
            )
        )

    def test_4_specialized_no_exit_zones(self):
        ez = _profile(confidence="SPECIALIZED")
        self.assertIsNone(ez)
        self.assertFalse(
            can_emit_exit_zones({"confidence": "SPECIALIZED", "blended_mid": 300, "blended_high": 330})
        )

    def test_5_high_volatility_widens_thresholds(self):
        base = _profile(volatility_1y=0.20)
        wide = _profile(volatility_1y=0.55)
        self.assertGreater(wide["trim_pct"], base["trim_pct"])
        self.assertGreater(wide["extreme_pct"], base["extreme_pct"])
        self.assertGreater(wide["trim_price"], base["trim_price"])

    def test_6_cyclical_class_widens_thresholds(self):
        base = _profile(cyclicality="low", valuation_class="mega_cap_tech")
        cyc = _profile(cyclicality="high", valuation_class="cyclical_semiconductor")
        self.assertGreater(cyc["trim_pct"], base["trim_pct"])
        self.assertGreater(cyc["extreme_pct"], base["extreme_pct"])

    def test_7_semiconductor_growth_wider_than_bank(self):
        semi = _profile(valuation_class="semiconductor_growth", cyclicality="low")
        bank = _profile(valuation_class="bank", cyclicality="low")
        self.assertGreater(semi["trim_pct"], bank["trim_pct"])
        self.assertGreater(semi["extreme_pct"], bank["extreme_pct"])
        self.assertGreater(semi["hold_upper_pct"], bank["hold_upper_pct"])
        self.assertGreater(semi["trim_price"], bank["trim_price"])

    def test_8_hold_upper_price_ge_blended_high(self):
        ez = _profile(blended_low=260, blended_mid=290, blended_high=320, confidence="MEDIUM")
        self.assertGreaterEqual(ez["hold_upper_price"], 320)

    def test_9_pct_and_price_ordering(self):
        ez = _profile()
        self.assertLess(ez["hold_upper_pct"], ez["overvalued_pct"])
        self.assertLess(ez["overvalued_pct"], ez["trim_pct"])
        self.assertLess(ez["trim_pct"], ez["extreme_pct"])
        self.assertLess(ez["hold_upper_price"], ez["overvalued_price"])
        self.assertLess(ez["overvalued_price"], ez["trim_price"])
        self.assertLess(ez["trim_price"], ez["extreme_price"])
        self.assertGreater(ez["trim_price"], ez["blended_high"])

    def test_10_historical_snapshot_uses_saved_exit_zone(self):
        saved = {
            "hold_upper_pct": 0.12,
            "overvalued_pct": 0.22,
            "trim_pct": 0.33,
            "extreme_pct": 0.48,
            "hold_upper_price": 335.0,
            "overvalued_price": 360.0,
            "trim_price": 390.0,
            "extreme_price": 435.0,
            "marker": "historical-saved",
        }
        snap = {
            "fair_value": 300,
            "confidence": "MEDIUM",
            "blended_low": 270,
            "blended_high": 330,
            "model_version": "v4.2-exit-zone",
            "snapshot_date": "2024-01-10",
            "hold_upper_price": 335.0,
            "overvalued_price": 360.0,
            "trim_price": 390.0,
            "extreme_price": 435.0,
            "exit_zone_json": saved,
            "raw": {"exit_zone_json": saved},
        }
        with patch("valuation_engine.dynamic_overvaluation_profile") as mocked:
            mocked.side_effect = AssertionError("must not recompute exit zone for historical snapshot")
            blend = reconstruct_blend_from_snapshot(snap)
            restored = exit_zone_from_snapshot(snap)
        self.assertEqual(blend["exit_zone"]["marker"], "historical-saved")
        self.assertEqual(restored["trim_price"], 390.0)
        self.assertEqual(restored["extreme_price"], 435.0)
        mocked.assert_not_called()

        def history_loader(t, d):
            import pandas as pd
            from test_v41_regression import _ohlcv
            return _ohlcv(400)

        result = analyze_ticker(
            "AMZN",
            as_of="2024-01-15",
            history_loader=history_loader,
            fundamentals_loader=lambda t: {},
            snapshot_loader=lambda t, d: snap,
        )
        self.assertEqual(result["exit_zone"]["marker"], "historical-saved")
        self.assertEqual(result["exit_zone"]["trim_price"], 390.0)

    def test_11_price_in_trim_range_status(self):
        ez = _profile()
        r = {
            "price": (ez["trim_price"] + ez["extreme_price"]) / 2,
            "confidence": "MEDIUM",
            "zones": {
                "first": (250, 260),
                "core": (230, 240),
                "deep": (200, 220),
                "labels": {"first": "第一批区", "core": "核心买入区", "deep": "深度价值区"},
            },
            "exit_zone": ez,
            "blend": {"confidence": "MEDIUM", "exit_zone": ez},
        }
        self.assertEqual(_recommendation_label(r), "减仓参考区")

    def test_12_price_above_extreme_status(self):
        ez = _profile()
        r = {
            "price": ez["extreme_price"] + 5,
            "confidence": "MEDIUM",
            "zones": {
                "first": (250, 260),
                "core": (230, 240),
                "deep": (200, 220),
                "labels": {"first": "第一批区", "core": "核心买入区", "deep": "深度价值区"},
            },
            "exit_zone": ez,
            "blend": {"confidence": "MEDIUM"},
        }
        self.assertEqual(_recommendation_label(r), "明显高估区")

    def test_13_low_confidence_no_precise_trim_prices_even_if_price_high(self):
        r = {
            "price": 500,
            "confidence": "LOW",
            "blended_mid": 300,
            "blended_low": 250,
            "blended_high": 350,
            "fair": 300,
            "fair_low": 250,
            "fair_high": 350,
            "zones": {
                "first": (250, 260),
                "core": (230, 240),
                "deep": (200, 220),
                "low_confidence": True,
                "labels": {"first": "参考关注区", "core": "参考折价区", "deep": "深度折价区"},
            },
            "exit_zone": None,
            "blend": {"confidence": "LOW"},
        }
        label = _recommendation_label(r)
        self.assertEqual(label, "估值偏高（低置信度）")
        self.assertIsNone(dynamic_overvaluation_profile(250, 300, 350, "LOW"))
        self.assertEqual(format_trim_zone(None), "—")
        self.assertEqual(format_extreme_zone(None), "—")
        row = build_snapshot_record(
            "user-1",
            {
                **r,
                "ticker": "PLTR",
                "date": "2024-01-01",
                "sma30": 1,
                "sma50": 1,
                "sma200": 1,
                "recommendation": label,
                "blend": {"confidence": "LOW", "models": {}},
            },
        )
        self.assertIsNone(row.get("trim_price"))
        self.assertIsNone(row.get("extreme_price"))
        self.assertIsNone(row.get("exit_zone_json"))

    def test_model_version_v42(self):
        self.assertEqual(MODEL_VERSION, "v4.2-exit-zone")


class ExitZoneBuyZoneRegression(unittest.TestCase):
    """TEST 14: existing buy-zone path still works with exit layer present."""

    def test_14_buy_zone_undervalued_status_unchanged(self):
        ez = _profile()
        r = {
            "price": 210,
            "confidence": "MEDIUM",
            "zones": {
                "first": (250, 260),
                "core": (230, 240),
                "deep": (200, 220),
                "labels": {"first": "第一批区", "core": "核心买入区", "deep": "深度价值区"},
            },
            "exit_zone": ez,
            "blend": {"confidence": "MEDIUM", "exit_zone": ez},
        }
        self.assertEqual(_recommendation_label(r), "深度价值区")
        r["price"] = 235
        self.assertEqual(_recommendation_label(r), "核心买入区")
        r["price"] = 255
        self.assertEqual(_recommendation_label(r), "第一批区")
        r["price"] = ez["hold_upper_price"] - 1
        self.assertEqual(_recommendation_label(r), "合理持有区")


if __name__ == "__main__":
    unittest.main()
