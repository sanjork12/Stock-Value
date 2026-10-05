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
    load_market_share,
    market_share_rows,
    normalize_watchlist_tickers,
    resolve_company,
    show_cloud_module,
    show_compute_module,
    show_memory_module,
)
from industry import ui as industry_ui
from industry.ui import (
    chart_rows_for_market,
    hbm_role_rows,
    period_for_market,
    table_rows_for_market,
)


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
                {"收入", "利润率", "资本开支", "竞争", "监管", "产品"},
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

    def test_landscape_qoq_and_previous_columns(self):
        table = table_rows_for_market("cloud_infrastructure")
        self.assertTrue(table)
        for row in table:
            self.assertIn("当前份额", row)
            self.assertIn("上季份额", row)
            self.assertIn("QoQ变化", row)
            self.assertIn("排名", row)
            self.assertIn("公司", row)
        aws = next(r for r in table if r["公司"] == "AWS")
        self.assertEqual(aws["当前份额"], "30.0%")
        self.assertEqual(aws["上季份额"], "31.0%")
        self.assertEqual(aws["QoQ变化"], "-1.0pp")

    def test_oracle_excluded_from_percentage_bar_chart(self):
        chart = chart_rows_for_market("cloud_infrastructure")
        names = [r["公司"] for r in chart]
        self.assertNotIn("Oracle", names)
        self.assertIn("AWS", names)
        self.assertIn("Azure", names)
        self.assertIn("Google Cloud", names)
        self.assertIn("Others", names)
        # Oracle still appears in the table as non-percentage disclosure.
        table = table_rows_for_market("cloud_infrastructure")
        oracle = next(r for r in table if r["公司"] == "Oracle")
        self.assertIn("not separately disclosed", oracle["当前份额"])
        self.assertEqual(oracle["QoQ变化"], "—")

    def test_hbm_no_fabricated_share_pct(self):
        rows = market_share_rows("hbm")
        self.assertTrue(rows)
        for r in rows:
            self.assertIsNone(r.get("share_pct"))
        chart = chart_rows_for_market("hbm", rows)
        self.assertEqual(chart, [])
        roles = hbm_role_rows(rows)
        self.assertEqual(
            roles,
            [
                ("SK hynix", "Leader"),
                ("Samsung", "Major supplier"),
                ("Micron", "Challenger"),
            ],
        )

    def test_market_share_values_unchanged(self):
        rows = load_market_share()
        cloud = {r["company"]: r for r in rows if r["market"] == "cloud_infrastructure"}
        self.assertEqual(cloud["AWS"]["share_pct"], 30.0)
        self.assertEqual(cloud["AWS"]["previous_share_pct"], 31.0)
        self.assertEqual(cloud["AWS"]["change_pp"], -1.0)
        self.assertEqual(cloud["Azure"]["share_pct"], 21.0)
        self.assertEqual(cloud["Google Cloud"]["share_pct"], 12.0)
        self.assertIsNone(cloud["Oracle"]["share_pct"])
        dram = {r["company"]: r for r in rows if r["market"] == "dram"}
        self.assertEqual(dram["Samsung"]["share_pct"], 34.0)
        self.assertEqual(dram["SK hynix"]["share_pct"], 33.0)
        self.assertEqual(dram["Micron"]["share_pct"], 23.0)
        self.assertEqual(period_for_market("cloud_infrastructure"), "2025 Q2")
        self.assertEqual(period_for_market("dram"), "2025 Q2")


if __name__ == "__main__":
    unittest.main()
