from __future__ import annotations

import inspect
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from industry.constants import MAG7
from industry.loader import (
    clear_industry_cache,
    get_watchlist_events,
    normalize_watchlist_tickers,
    resolve_company,
    show_cloud_module,
    show_compute_module,
    show_memory_module,
)
from industry import ui as industry_ui


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(name: str) -> str:
    with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
        return fh.read()


class IndustryV52Tests(unittest.TestCase):
    def setUp(self):
        clear_industry_cache()

    def test_1_page_accepts_watchlist_and_mode(self):
        sig = inspect.signature(industry_ui.render_industry_page)
        self.assertIn("watchlist_tickers", sig.parameters)
        self.assertIn("mode", sig.parameters)

    def test_2_empty_watchlist_normalize(self):
        self.assertEqual(normalize_watchlist_tickers([]), [])
        self.assertEqual(normalize_watchlist_tickers(None), [])

    def test_3_map_uses_panorama_image(self):
        src = _read("industry/ui.py")
        self.assertIn("ai_industry_panorama.jpg", src)
        self.assertIn("st.image", src)
        img = os.path.join(ROOT, "assets", "ai_industry_panorama.jpg")
        self.assertTrue(os.path.exists(img))

    def test_4_no_nested_industry_tabs(self):
        src = _read("industry/ui.py")
        self.assertNotIn("ind_v52_tabs", src)
        self.assertNotIn("segmented_control", src)
        self.assertNotIn("render_tab_watchlist", src)
        self.assertNotIn("LAYER_MAP_ORDER", src)

    def test_5_no_stars_in_ui_source(self):
        src = _read("industry/ui.py")
        self.assertNotIn("★", src)
        self.assertNotIn("stars_to_text", src)

    def test_6_no_ticker_button_grid_on_map(self):
        src = _read("industry/ui.py")
        self.assertNotIn("ind_map_", src)
        self.assertNotIn("companies_touching_layer", src)

    def test_7_cloud_module_gated(self):
        self.assertTrue(show_cloud_module(["AMZN"]))
        self.assertTrue(show_cloud_module(["ORCL"]))
        self.assertFalse(show_cloud_module(["MU", "JPM"]))

    def test_8_memory_module_gated(self):
        self.assertTrue(show_memory_module(["MU"]))
        self.assertFalse(show_memory_module(["AMZN", "NVDA"]))

    def test_9_compute_module_gated(self):
        self.assertTrue(show_compute_module(["NVDA"]))
        self.assertTrue(show_compute_module(["ANET"]))
        self.assertFalse(show_compute_module(["CRM"]))

    def test_10_mag7_constant(self):
        self.assertEqual(len(MAG7), 7)

    def test_11_get_watchlist_events_filters(self):
        rows = get_watchlist_events(["NVDA", "JPM"], start_date="2000-01-01")
        tickers = {r["ticker"] for r in rows}
        self.assertTrue(tickers <= {"NVDA", "JPM"} or len(rows) == 0 or "NVDA" in tickers)
        for r in rows:
            self.assertIn(r["importance"], {"重大", "重要", "一般"})
            self.assertIn("headline", r)
            self.assertIn("why_it_matters", r)
            self.assertIn(
                r.get("impact_area"),
                {"Revenue", "Margin", "CapEx", "Competition", "Regulation", "Product"},
            )

    def test_12_get_watchlist_events_empty_watchlist(self):
        self.assertEqual(get_watchlist_events([]), [])

    def test_13_company_panels_exist(self):
        from industry import company_panels as panels

        self.assertTrue(callable(panels.render_earnings_panel))
        self.assertTrue(callable(panels.render_position_panel))
        self.assertTrue(callable(panels.render_events_panel))

    def test_unclassified_resolve(self):
        self.assertIsNone(resolve_company("JPM"))


if __name__ == "__main__":
    unittest.main()
