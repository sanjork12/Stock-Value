from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis_service import industry_valuation_snapshot
from industry.constants import MAG7
from industry.loader import (
    build_industry_map_export,
    clear_industry_cache,
    latest_earnings,
    load_companies,
    load_market_share,
    market_share_rows,
    resolve_company,
    validate_datasets,
    valuation_ticker_for,
)
from industry.models import segment_pct_sum


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class IndustryV5Tests(unittest.TestCase):
    def setUp(self):
        clear_industry_cache()

    def test_1_mag7_all_have_profiles(self):
        for tid in MAG7:
            c = resolve_company(tid)
            self.assertIsNotNone(c, tid)
            self.assertTrue(c.get("current_profit_layers"), tid)
            self.assertIn("ai_monetization_status", c)

    def test_2_revenue_mix_sums_near_100(self):
        for c in load_companies():
            earn = latest_earnings(c.get("company_id") or "")
            if not earn:
                continue
            segs = earn.get("segments") or []
            if not segs:
                continue
            total = segment_pct_sum(segs)
            self.assertLessEqual(abs(total - 100.0), 2.5, f"{c.get('company_id')} sum={total}")

    def test_3_market_share_pct_range(self):
        for row in load_market_share():
            share = row.get("share_pct")
            if share is None:
                continue
            self.assertGreaterEqual(float(share), 0)
            self.assertLessEqual(float(share), 100)

    def test_4_cloud_share_period_and_source(self):
        rows = market_share_rows("cloud_infrastructure")
        self.assertTrue(rows)
        self.assertTrue(any(r.get("period") for r in rows))
        self.assertTrue(any(r.get("source") or r.get("source_url") for r in rows))
        oracle = [r for r in rows if str(r.get("company")).lower() == "oracle"]
        self.assertTrue(oracle)
        self.assertIsNone(oracle[0].get("share_pct"))

    def test_5_memory_share_period_and_source(self):
        rows = market_share_rows("dram")
        self.assertTrue(rows)
        self.assertTrue(any(r.get("period") for r in rows))
        self.assertTrue(any(r.get("source") or r.get("source_url") for r in rows))

    def test_6_current_profit_separated_from_future(self):
        for tid in MAG7:
            c = resolve_company(tid)
            self.assertTrue(c.get("current_profit_layers"))
            self.assertIn("future_expansion_layers", c)
            # Fields exist distinctly (may overlap themes but must both be present as lists)
            self.assertIsInstance(c.get("current_profit_layers"), list)
            self.assertIsInstance(c.get("future_expansion_layers"), list)

    def test_7_specialized_valuation_independent_of_industry_map(self):
        # Industry dataset must not require fair value; SPECIALIZED tickers still resolve profiles.
        # PLTR may or may not be specialized depending on engine — profile must exist either way.
        c = resolve_company("PLTR")
        self.assertIsNotNone(c)
        self.assertEqual(c.get("include_in_valuation"), True)
        # Fake specialized summary must still be pass-through without mutating industry data
        summary = industry_valuation_snapshot(
            "PLTR",
            analyze_fn=lambda t, **kw: {
                "ticker": "PLTR",
                "price": 40.0,
                "confidence": "SPECIALIZED",
                "blended_mid": None,
                "recommendation": "仅技术观察",
                "financials": {},
            },
        )
        self.assertEqual(summary["confidence"], "SPECIALIZED")
        self.assertEqual(summary["fair_value_display"], "—")
        self.assertEqual(resolve_company("PLTR")["company_id"], "PLTR")

    def test_8_company_detail_valuation_ticker_jump(self):
        self.assertEqual(valuation_ticker_for("NVDA"), "NVDA")
        self.assertEqual(valuation_ticker_for("GOOG"), "GOOGL")
        self.assertEqual(valuation_ticker_for("GOOGL"), "GOOGL")
        self.assertIsNone(valuation_ticker_for("OPENAI"))
        self.assertIsNone(valuation_ticker_for("SAMSUNG"))

    def test_9_goog_googl_mapping(self):
        a = resolve_company("GOOG")
        b = resolve_company("GOOGL")
        self.assertIsNotNone(a)
        self.assertIsNotNone(b)
        self.assertEqual(a.get("company_id"), b.get("company_id"))
        self.assertEqual(a.get("company_name"), "Alphabet")

    def test_10_source_metadata_mandatory_on_shares_and_earnings(self):
        errors = [e for e in validate_datasets() if "missing source" in e.lower() or "without source" in e.lower()]
        self.assertEqual(errors, [])

    def test_11_no_industry_percentage_without_source(self):
        for row in load_market_share():
            if row.get("share_pct") is None:
                continue
            self.assertTrue(row.get("source") or row.get("source_url"), row)

    def test_validate_datasets_clean(self):
        errs = validate_datasets()
        self.assertEqual(errs, [], errs)

    def test_export_payload_has_layers(self):
        payload = build_industry_map_export()
        self.assertEqual(len(payload.get("layers") or []), 4)
        self.assertIn("companies", payload)
        self.assertIn("market_share", payload)
        self.assertIn("events", payload)


if __name__ == "__main__":
    unittest.main()
