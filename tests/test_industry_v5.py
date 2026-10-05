from __future__ import annotations

import inspect
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from industry.constants import MAG7, MONETIZATION_ZH, TREND_LABEL
from industry.loader import (
    clear_industry_cache,
    normalize_watchlist_tickers,
    resolve_company,
    show_cloud_module,
    show_compute_module,
    show_memory_module,
    trend_label,
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
        self.assertIn("七巨头对照", src)

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
        self.assertIn("Catalyst / Risk", src)

    def test_12_company_click_routes_to_single_stock(self):
        src = _read("industry/ui.py")
        self.assertIn('_pending_nav_page = "单股分析"', src)
        self.assertIn('query_params["ticker"]', src)

    def test_13_export_controls_hidden(self):
        src = _read("industry/ui.py")
        self.assertNotIn("导出产业链地图", src)
        self.assertNotIn("Export Industry Map", src)
        # Export tooling may exist only inside collapsed 高级工具 caption
        self.assertIn("高级工具", src)

    def test_14_valuation_uses_analysis_service_bridge(self):
        app = _read("streamlit_app.py")
        self.assertIn("industry_valuation_snapshot", app)
        self.assertIn("valuation_loader=_industry_val_loader", app)

    def test_15_compute_module_gated(self):
        self.assertTrue(show_compute_module(["NVDA"]))
        self.assertTrue(show_compute_module(["ANET"]))
        self.assertFalse(show_compute_module(["CRM"]))

    def test_unclassified_watchlist_ticker_supported(self):
        self.assertIsNone(resolve_company("JPM"))
        rows_fn = industry_ui._overview_row
        row = rows_fn("JPM", row_group="My Watchlist", valuation_loader=None)
        self.assertEqual(row["产业层级"], "Other / Unclassified")
        self.assertTrue(row["_unclassified"])


class IndustryV511CompactLayoutTests(unittest.TestCase):
    """V5.1.1 — Industry Page Compact Decision-first Layout."""

    def setUp(self):
        clear_industry_cache()

    def test_header_no_product_subtitle(self):
        app = _read("streamlit_app.py")
        # Product intro must not sit under main chrome header
        self.assertNotIn(
            'st.caption("自选股数据库 + Sector-aware 公允价值 + SMA30/50/200 + 成交密集区 + 分层买入区")',
            app,
        )
        # Compact title (not st.title hero)
        self.assertIn("font-size:30px", app)
        self.assertNotIn('st.title("📈 Stock Fair Value Monitor")', app)

    def test_industry_no_hero_title(self):
        src = _read("industry/ui.py")
        self.assertNotIn("我的 AI 产业链情报", src)
        self.assertNotIn("基于当前自选股，查看产业位置", src)

    def test_industry_no_default_top_freshness(self):
        src = _read("industry/ui.py")
        # Freshness moved to footer expander / caption — not rendered before tabs
        self.assertIn('expander("数据说明"', src)
        # Must not call _freshness_line at page top (function removed)
        self.assertNotIn("_freshness_line", src)
        self.assertNotIn("最近更新：", src)

    def test_core_watchlist_column_order(self):
        expected = [
            "股票",
            "主要利润引擎",
            "最新收入增速",
            "季度变化",
            "AI变现",
            "CapEx强度",
            "当前估值状态",
        ]
        self.assertEqual(industry_ui.CORE_WATCHLIST_COLS, expected)

    def test_default_hides_advanced_fields(self):
        src = _read("industry/ui.py")
        # Default table uses CORE only; advanced appended when toggle on
        self.assertIn("CORE_WATCHLIST_COLS", src)
        self.assertIn("ADVANCED_WATCHLIST_COLS", src)
        for col in ["分组", "公司", "产业层级", "未来扩张", "Catalyst", "Risk"]:
            self.assertNotIn(col, industry_ui.CORE_WATCHLIST_COLS)
        self.assertEqual(
            industry_ui.ADVANCED_WATCHLIST_COLS,
            ["产业层级", "未来扩张", "Catalyst", "Risk", "公司"],
        )

    def test_more_info_toggle_and_benchmark_same_row(self):
        src = _read("industry/ui.py")
        self.assertIn('checkbox("七巨头对照"', src)
        self.assertIn('checkbox("更多信息"', src)
        # Same compact columns region
        idx_bench = src.index('checkbox("七巨头对照"')
        idx_more = src.index('checkbox("更多信息"')
        self.assertLess(abs(idx_bench - idx_more), 400)

    def test_valuation_status_from_analysis_service(self):
        called = []

        def loader(t):
            called.append(t)
            return {"status": "核心买入区"}

        row = industry_ui._overview_row("NVDA", row_group="My Watchlist", valuation_loader=loader)
        self.assertEqual(row["当前估值状态"], "核心买入区")
        self.assertTrue(called)

        app = _read("streamlit_app.py")
        self.assertIn("industry_valuation_snapshot", app)

    def test_chinese_short_labels(self):
        self.assertEqual(TREND_LABEL["improving"], "↑ 改善")
        self.assertEqual(trend_label("stable"), "→ 稳定")
        self.assertEqual(MONETIZATION_ZH["DIRECT"], "直接")
        self.assertEqual(industry_ui._monetization_zh("INDIRECT"), "间接")
        self.assertEqual(industry_ui._pct(0.18, signed=True), "+18%")
        self.assertEqual(industry_ui._pct(-0.05, signed=True), "-5%")
        self.assertEqual(industry_ui._pct(None, signed=True), "—")

    def test_tabs_label_visibility_collapsed(self):
        src = _read("industry/ui.py")
        self.assertIn('label_visibility="collapsed"', src)
        self.assertNotIn("st.subheader", src)


if __name__ == "__main__":
    unittest.main()
