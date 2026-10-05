from __future__ import annotations

import inspect
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from industry.constants import MAG7
from industry.loader import (
    clear_industry_cache,
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


class IndustryV51Tests(unittest.TestCase):
    def setUp(self):
        clear_industry_cache()

    def test_1_page_accepts_watchlist_argument(self):
        sig = inspect.signature(industry_ui.render_industry_page)
        self.assertIn("watchlist_tickers", sig.parameters)

    def test_2_empty_watchlist_normalize(self):
        self.assertEqual(normalize_watchlist_tickers([]), [])
        self.assertEqual(normalize_watchlist_tickers(None), [])

    def test_3_map_uses_panorama_image(self):
        src = _read("industry/ui.py")
        self.assertIn("ai_industry_panorama.jpg", src)
        self.assertIn("st.image", src)
        img = os.path.join(ROOT, "assets", "ai_industry_panorama.jpg")
        self.assertTrue(os.path.exists(img))

    def test_4_layer_list_map_removed_from_tab(self):
        src = _read("industry/ui.py")
        self.assertNotIn("_render_layer_map", src)
        self.assertNotIn("高亮 = 你的自选股", src)

    def test_5_no_stars_in_ui_source(self):
        src = _read("industry/ui.py")
        self.assertNotIn("★", src)
        self.assertNotIn("stars_to_text", src)

    def test_6_no_detail_buttons_in_map(self):
        src = _read("industry/ui.py")
        self.assertNotIn("查看详情", src)
        self.assertNotIn('st.button("Detail"', src)

    def test_7_watchlist_overview_defaults_to_user_tickers(self):
        src = _read("industry/ui.py")
        self.assertIn('row_group="My Watchlist"', src)
        self.assertIn("显示七巨头对照", src)

    def test_8_benchmark_toggle_adds_mag7(self):
        src = _read("industry/ui.py")
        self.assertIn("Benchmark", src)
        self.assertIn("MAG7", src)
        self.assertEqual(len(MAG7), 7)

    def test_9_cloud_module_gated(self):
        self.assertTrue(show_cloud_module(["AMZN"]))
        self.assertTrue(show_cloud_module(["ORCL"]))
        self.assertFalse(show_cloud_module(["MU", "JPM"]))

    def test_10_memory_module_gated(self):
        self.assertTrue(show_memory_module(["MU"]))
        self.assertFalse(show_memory_module(["AMZN", "NVDA"]))

    def test_11_events_filtered_helper_exists(self):
        src = _read("industry/ui.py")
        self.assertIn("events_for", src)
        self.assertIn("仅自选股", src)

    def test_12_company_click_routes_to_single_stock(self):
        src = _read("industry/ui.py")
        self.assertIn('_pending_nav_page = "单股分析"', src)
        self.assertIn('query_params["ticker"]', src)

    def test_13_export_controls_hidden(self):
        src = _read("industry/ui.py")
        self.assertNotIn("导出产业链地图", src)
        self.assertNotIn("Export Industry Map", src)
        self.assertNotIn("PPT", src)

    def test_14_valuation_uses_analysis_service_bridge(self):
        app = _read("streamlit_app.py")
        self.assertIn("industry_valuation_snapshot", app)
        self.assertIn("valuation_loader=_industry_val_loader", app)

    def test_15_compute_module_gated(self):
        self.assertTrue(show_compute_module(["NVDA"]))
        self.assertTrue(show_compute_module(["ANET"]))
        self.assertFalse(show_compute_module(["CRM"]))

    def test_unclassified_watchlist_ticker_supported(self):
        # JPM may not have industry profile — UI must still list it
        self.assertIsNone(resolve_company("JPM"))
        rows_fn = industry_ui._overview_row
        row = rows_fn("JPM", row_group="My Watchlist", valuation_loader=None)
        self.assertEqual(row["产业层级"], "Other / Unclassified")
        self.assertTrue(row["_unclassified"])


if __name__ == "__main__":
    unittest.main()
