"""V5.2 Navigation & Information Architecture static tests."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(name: str) -> str:
    with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
        return fh.read()


class NavV52Tests(unittest.TestCase):
    def test_1_top_nav_flat_industry(self):
        app = _read("streamlit_app.py")
        self.assertIn(
            'NAV_PAGES = ["产业链地图", "市场格局", "自选股", "单股分析", "头等大事"]',
            app,
        )

    def test_2_history_not_in_top_nav(self):
        app = _read("streamlit_app.py")
        start = app.find("NAV_PAGES = [")
        end = app.find("]", start)
        block = app[start : end + 1]
        self.assertNotIn("历史快照", block)

    def test_3_account_not_in_top_nav(self):
        app = _read("streamlit_app.py")
        start = app.find("NAV_PAGES = [")
        end = app.find("]", start)
        block = app[start : end + 1]
        self.assertNotIn("账户", block)

    def test_4_industry_no_nested_secondary_menu(self):
        src = _read("industry/ui.py")
        self.assertNotIn("ind_v52_tabs", src)
        self.assertNotIn("segmented_control", src)
        app = _read("streamlit_app.py")
        self.assertIn('page in {"产业链地图", "市场格局"}', app)
        self.assertIn('mode="landscape"', app)

    def test_5_map_is_panorama(self):
        src = _read("industry/ui.py")
        self.assertIn("ai_industry_panorama.jpg", src)
        self.assertIn("st.image", src)
        self.assertNotIn("render_tab_watchlist", src)
        self.assertNotIn("当前估值状态", src)

    def test_6_single_stock_tabs(self):
        app = _read("streamlit_app.py")
        self.assertIn(
            'SINGLE_STOCK_TABS = ["估值", "财报与业务", "行业地位", "重大事件", "历史"]',
            app,
        )

    def test_7_historical_via_single_stock(self):
        app = _read("streamlit_app.py")
        self.assertIn('ss_tab == "历史"', app)
        self.assertIn("list_snapshots", app)
        self.assertNotIn('page == "历史快照"', app)

    def test_8_account_via_user_menu(self):
        app = _read("streamlit_app.py")
        self.assertIn("账户设置", app)
        self.assertIn("修改密码", app)
        self.assertIn("render_account_panel", app)
        self.assertIn("account_open", app)
        self.assertNotIn('page == "账户"', app)

    def test_9_watchlist_opens_single_stock(self):
        app = _read("streamlit_app.py")
        dash = app.split('if page == "自选股":', 1)[1].split("elif page ==", 1)[0]
        self.assertIn("open_single_stock", dash)

    def test_10_legacy_ai_industry_maps_to_panorama(self):
        app = _read("streamlit_app.py")
        self.assertIn('"AI产业链": "产业链地图"', app)

    def test_11_headline_opens_single_stock(self):
        app = _read("streamlit_app.py")
        head = app.split('page == "头等大事"', 1)[1]
        self.assertIn("open_single_stock", head)
        self.assertIn('tab="重大事件"', head)

    def test_12_headline_filters_watchlist_events(self):
        app = _read("streamlit_app.py")
        self.assertIn("get_watchlist_events", app)
        self.assertIn("目前没有发现影响投资逻辑的重大事件", app)

    def test_13_headline_empty_state(self):
        app = _read("streamlit_app.py")
        self.assertIn("目前没有发现影响投资逻辑的重大事件。", app)

    def test_14_valuation_uses_analysis_service(self):
        app = _read("streamlit_app.py")
        self.assertIn("from analysis_service import", app)
        self.assertIn("analyze_ticker", app)
        dash = app.split('if page == "自选股":', 1)[1].split("elif page ==", 1)[0]
        self.assertIn("analyze_one", dash)

    def test_15_watchlist_core_column_order(self):
        app = _read("streamlit_app.py")
        dash = app.split('if page == "自选股":', 1)[1].split("elif page ==", 1)[0]
        expected = [
            "股票",
            "价格",
            "状态",
            "公允价值",
            "距公允价值%",
            "核心买入区",
            "减仓参考区",
            "置信度",
        ]
        start = dash.find("dashboard_columns = [")
        self.assertGreaterEqual(start, 0)
        end = dash.find("]", start)
        block = dash[start:end]
        order = []
        for name in expected + ["错误", "第一批区", "备注"]:
            token = f'"{name}"'
            if token in block:
                order.append((block.find(token), name))
        order.sort()
        names = [n for _, n in order if n != "错误"]
        self.assertEqual(names, expected)
        self.assertIn('checkbox("更多指标"', dash)
        self.assertNotIn("备注", names)


if __name__ == "__main__":
    unittest.main()
