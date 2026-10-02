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
    build_exit_zone,
    compute_exit_reliability,
    dynamic_overvaluation_profile,
    exit_zone_from_snapshot,
    reconstruct_blend_from_snapshot,
)


def _ez(**kwargs):
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
    return build_exit_zone(**base)


class ExitReliabilityGuardTests(unittest.TestCase):
    def test_1_high_reliable_low_dispersion_precise(self):
        ez = _ez(confidence="HIGH", reliability_score=90, dispersion_pct=0.10)
        self.assertTrue(ez["eligible_for_precise_exit"])
        self.assertEqual(ez["display_mode"], "precise")
        self.assertEqual(ez["exit_confidence"], "HIGH")
        self.assertIsNotNone(ez["trim_price"])
        self.assertIsNotNone(ez["extreme_price"])

    def test_2_medium_reliable_low_dispersion_precise(self):
        ez = _ez(confidence="MEDIUM", reliability_score=75, dispersion_pct=0.20)
        self.assertTrue(ez["eligible_for_precise_exit"])
        self.assertEqual(ez["display_mode"], "precise")
        self.assertEqual(ez["exit_confidence"], "MEDIUM")

    def test_3_medium_dispersion_40_qualitative(self):
        ez = _ez(confidence="MEDIUM", reliability_score=75, dispersion_pct=0.40)
        self.assertFalse(ez["eligible_for_precise_exit"])
        self.assertEqual(ez["display_mode"], "qualitative")
        self.assertIsNone(ez["trim_price"])
        self.assertIsNone(ez["extreme_price"])
        self.assertIn("elevated_model_dispersion", ez["reason_codes"])

    def test_4_high_dispersion_60_qualitative(self):
        ez = _ez(confidence="MEDIUM", reliability_score=75, dispersion_pct=0.60)
        self.assertFalse(ez["eligible_for_precise_exit"])
        self.assertEqual(ez["display_mode"], "qualitative")
        self.assertIsNone(ez["trim_price"])
        self.assertIn("high_model_dispersion", ez["reason_codes"])

    def test_5_reliability_below_65_qualitative(self):
        ez = _ez(confidence="MEDIUM", reliability_score=60, dispersion_pct=0.10)
        self.assertFalse(ez["eligible_for_precise_exit"])
        self.assertEqual(ez["display_mode"], "qualitative")
        self.assertIsNone(ez["trim_price"])
        self.assertIn("insufficient_exit_reliability", ez["reason_codes"])

    def test_6_low_confidence_no_precise(self):
        ez = _ez(confidence="LOW", reliability_score=80, dispersion_pct=0.10)
        self.assertFalse(ez["eligible_for_precise_exit"])
        self.assertNotEqual(ez.get("display_mode"), "precise")
        self.assertIsNone(ez.get("trim_price"))

    def test_7_specialized_unavailable(self):
        rel = compute_exit_reliability("SPECIALIZED", 80, 0.10, 300, 330)
        self.assertEqual(rel["display_mode"], "unavailable")
        self.assertFalse(rel["eligible_for_precise_exit"])
        ez = build_exit_zone(270, 300, 330, "SPECIALIZED", 80, 0.10)
        self.assertEqual(ez["display_mode"], "unavailable")

    def test_8_unavailable_mode(self):
        rel = compute_exit_reliability("UNAVAILABLE", None, None, None, None)
        self.assertEqual(rel["display_mode"], "unavailable")
        self.assertFalse(rel["eligible_for_precise_exit"])

    def test_9_precise_mode_prices_visible(self):
        ez = _ez(reliability_score=75, dispersion_pct=0.20)
        self.assertEqual(format_trim_zone(ez), f"${ez['trim_price']:,.0f} - ${ez['extreme_price']:,.0f}")
        self.assertEqual(format_extreme_zone(ez), f">${ez['extreme_price']:,.0f}")

    def test_10_qualitative_mode_display_dash(self):
        ez = _ez(reliability_score=75, dispersion_pct=0.60)
        self.assertEqual(format_trim_zone(ez), "—")
        self.assertEqual(format_extreme_zone(ez), "—")

    def test_11_high_dispersion_status(self):
        ez = _ez(reliability_score=75, dispersion_pct=0.57)
        r = {
            "price": 400,
            "confidence": "MEDIUM",
            "blended_mid": 300,
            "blended_high": 330,
            "zones": {
                "first": (250, 260),
                "core": (230, 240),
                "deep": (200, 220),
                "labels": {"first": "第一批区", "core": "核心买入区", "deep": "深度价值区"},
            },
            "exit_zone": ez,
            "blend": {"confidence": "MEDIUM", "exit_zone": ez},
        }
        self.assertEqual(_recommendation_label(r), "估值偏高（模型分歧较大）")

    def test_12_historical_uses_saved_exit_reliability(self):
        saved = {
            "display_mode": "qualitative",
            "exit_confidence": "LOW",
            "eligible_for_precise_exit": False,
            "reason_codes": ["high_model_dispersion"],
            "hold_upper_price": None,
            "trim_price": None,
            "extreme_price": None,
            "internal_thresholds_disabled_by_reliability": True,
            "marker": "saved-reliability",
        }
        snap = {
            "fair_value": 300,
            "confidence": "MEDIUM",
            "blended_low": 270,
            "blended_high": 330,
            "model_version": "v4.2.1-exit-reliability",
            "snapshot_date": "2024-01-10",
            "exit_confidence": "LOW",
            "exit_display_mode": "qualitative",
            "exit_reliability_score": 75,
            "exit_reason_codes": ["high_model_dispersion"],
            "hold_upper_price": None,
            "trim_price": None,
            "extreme_price": None,
            "exit_zone_json": saved,
            "raw": {"exit_zone_json": saved, "exit_display_mode": "qualitative"},
        }
        with patch("valuation_engine.build_exit_zone") as mocked:
            mocked.side_effect = AssertionError("must not recompute exit zone")
            blend = reconstruct_blend_from_snapshot(snap)
            restored = exit_zone_from_snapshot(snap)
        self.assertEqual(blend["exit_zone"]["marker"], "saved-reliability")
        self.assertEqual(restored["display_mode"], "qualitative")
        self.assertEqual(restored["exit_confidence"], "LOW")
        mocked.assert_not_called()

        def history_loader(t, d):
            from test_v41_regression import _ohlcv
            return _ohlcv(400)

        result = analyze_ticker(
            "AAPL",
            as_of="2024-01-15",
            history_loader=history_loader,
            fundamentals_loader=lambda t: {},
            snapshot_loader=lambda t, d: snap,
        )
        self.assertEqual(result["exit_zone"]["marker"], "saved-reliability")
        self.assertEqual(result["exit_display_mode"], "qualitative")
        self.assertEqual(format_trim_zone(result["exit_zone"]), "—")

    def test_13_v42_threshold_math_unchanged(self):
        raw = dynamic_overvaluation_profile(
            270, 300, 330, "MEDIUM", 75, 0.10, 0.20, "low", "mega_cap_tech"
        )
        guarded = _ez(reliability_score=75, dispersion_pct=0.10)
        self.assertAlmostEqual(raw["hold_upper_pct"], guarded["hold_upper_pct"])
        self.assertAlmostEqual(raw["trim_pct"], guarded["trim_pct"])
        self.assertAlmostEqual(raw["extreme_pct"], guarded["extreme_pct"])
        self.assertAlmostEqual(raw["trim_price"], guarded["trim_price"])

    def test_14_buy_zone_priority_unchanged(self):
        ez = _ez(reliability_score=90, dispersion_pct=0.10, confidence="HIGH")
        r = {
            "price": 210,
            "confidence": "HIGH",
            "zones": {
                "first": (250, 260),
                "core": (230, 240),
                "deep": (200, 220),
                "labels": {"first": "第一批区", "core": "核心买入区", "deep": "深度价值区"},
            },
            "exit_zone": ez,
            "blend": {"confidence": "HIGH", "exit_zone": ez},
        }
        self.assertEqual(_recommendation_label(r), "深度价值区")

    def test_model_version(self):
        self.assertEqual(MODEL_VERSION, "v4.2.1-exit-reliability")

    def test_snapshot_nulls_prices_when_qualitative(self):
        ez = _ez(reliability_score=75, dispersion_pct=0.60)
        row = build_snapshot_record(
            "user-1",
            {
                "ticker": "AAPL",
                "date": "2024-01-01",
                "price": 400,
                "sma30": 1,
                "sma50": 1,
                "sma200": 1,
                "fair": 300,
                "fair_low": 270,
                "fair_high": 330,
                "confidence": "MEDIUM",
                "recommendation": "估值偏高（模型分歧较大）",
                "exit_zone": ez,
                "exit_confidence": ez["exit_confidence"],
                "exit_display_mode": ez["display_mode"],
                "exit_reason_codes": ez["reason_codes"],
                "blend": {"confidence": "MEDIUM", "models": {}, "exit_zone": ez},
            },
        )
        self.assertIsNone(row["trim_price"])
        self.assertIsNone(row["extreme_price"])
        self.assertEqual(row["exit_display_mode"], "qualitative")
        self.assertTrue(row["exit_zone_json"]["internal_thresholds_disabled_by_reliability"])

    def test_aapl_goog_style_high_dispersion_no_precise(self):
        for disp in (0.57, 0.69, 0.63, 0.74):
            ez = _ez(confidence="MEDIUM", reliability_score=68, dispersion_pct=disp)
            self.assertEqual(ez["display_mode"], "qualitative")
            self.assertIsNone(ez["trim_price"])
            self.assertEqual(format_trim_zone(ez), "—")


if __name__ == "__main__":
    unittest.main()
