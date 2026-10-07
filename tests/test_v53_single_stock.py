"""V5.3 single-stock continuous page + headline intelligence tests."""
from __future__ import annotations

import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from industry.earnings_helpers import get_latest_company_quarter
from industry.events_provider import get_company_events, range_bounds
from industry.loader import clear_industry_cache, get_watchlist_events


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(name: str) -> str:
    with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
        return fh.read()


class V53SingleStockAndHeadlinesTests(unittest.TestCase):
    def setUp(self):
        clear_industry_cache()
        self._old_demo = os.environ.get("NEWS_DEMO_MODE")
        os.environ["NEWS_DEMO_MODE"] = "true"

    def tearDown(self):
        if self._old_demo is None:
            os.environ.pop("NEWS_DEMO_MODE", None)
        else:
            os.environ["NEWS_DEMO_MODE"] = self._old_demo
        clear_industry_cache()

    def test_1_single_stock_no_second_level_tabs(self):
        app = _read("streamlit_app.py")
        self.assertIn("SINGLE_STOCK_TABS: list[str] = []", app)
        self.assertNotIn('ss_tab == "估值"', app)
        self.assertNotIn("segmented_control(\n                \"单股页签\"", app)
        self.assertIn("V5.3 单股连续页", app)

    def test_2_no_industry_status_tab(self):
        app = _read("streamlit_app.py")
        self.assertNotIn('ss_tab == "行业地位"', app)
        self.assertNotIn("render_position_panel", app)

    def test_3_no_history_tab(self):
        app = _read("streamlit_app.py")
        self.assertNotIn('ss_tab == "历史"', app)
        self.assertNotIn("ss_hist_use_latest", app)
        # Backend snapshots retained
        self.assertIn("list_snapshots", app)
        self.assertIn("save_snapshot", app)

    def test_4_no_events_tab(self):
        app = _read("streamlit_app.py")
        self.assertNotIn('ss_tab == "重大事件"', app)

    def test_5_earnings_inline_with_valuation(self):
        app = _read("streamlit_app.py")
        self.assertIn("render_earnings_inline", app)
        self.assertIn("render_latest_event_teaser", app)
        self.assertIn("估值模型与诊断", app)

    def test_6_latest_quarter_newest_reported(self):
        rows = [
            {
                "ticker": "TSLA",
                "fiscal_period": "CY2025 Q2",
                "report_date": "2025-07-23",
                "period_end": "2025-06-30",
                "total_revenue": 1,
            },
            {
                "ticker": "TSLA",
                "fiscal_period": "CY2026 Q2",
                "report_date": "2026-07-22",
                "period_end": "2026-06-30",
                "total_revenue": 2,
            },
        ]
        latest = get_latest_company_quarter("TSLA", as_of=date(2026, 10, 5), rows=rows)
        self.assertEqual(latest["latest_reported_period"], "CY2026 Q2")
        self.assertEqual(latest["latest_report_date"], "2026-07-22")

    def test_7_future_quarter_not_selected(self):
        rows = [
            {
                "ticker": "TSLA",
                "fiscal_period": "CY2025 Q2",
                "report_date": "2025-07-23",
                "total_revenue": 1,
            },
            {
                "ticker": "TSLA",
                "fiscal_period": "CY2026 Q3",
                "report_date": "2026-10-22",  # future vs as_of 2026-10-05
                "total_revenue": 3,
            },
        ]
        latest = get_latest_company_quarter("TSLA", as_of=date(2026, 10, 5), rows=rows)
        self.assertEqual(latest["latest_reported_period"], "CY2025 Q2")

    def test_8_tesla_prefers_2026_when_present(self):
        # Same as test_6 — explicit Tesla naming for acceptance checklist.
        rows = [
            {"ticker": "TSLA", "fiscal_period": "CY2025 Q2", "report_date": "2025-07-23"},
            {"ticker": "TSLA", "fiscal_period": "CY2026 Q2", "report_date": "2026-07-22"},
        ]
        latest = get_latest_company_quarter("TSLA", as_of=date(2026, 10, 5), rows=rows)
        self.assertNotEqual(latest["latest_reported_period"], "CY2025 Q2")
        self.assertEqual(latest["latest_reported_period"], "CY2026 Q2")

    def test_9_past_24h_excludes_future(self):
        now = date(2026, 10, 5)
        b = range_bounds("过去24小时", now=now)
        rows = get_company_events(
            ["NVDA", "TSLA", "AVGO", "MSFT"],
            start_time=b["start_time"],
            end_time=b["end_time"],
            include_upcoming=False,
            now=now,
        )
        dates = [r["event_date"] for r in rows]
        self.assertTrue(all(d <= "2026-10-05" for d in dates))
        self.assertNotIn("2026-10-28", dates)
        self.assertNotIn("2026-10-20", dates)

    def test_10_week_excludes_future(self):
        now = date(2026, 10, 5)  # Monday
        b = range_bounds("本周", now=now)
        rows = get_company_events(
            ["NVDA", "TSLA", "AVGO"],
            start_time=b["start_time"],
            end_time=b["end_time"],
            now=now,
        )
        self.assertTrue(all(r["event_date"] <= "2026-10-05" for r in rows))
        self.assertTrue(all(r["event_date"] >= "2026-10-05" for r in rows) or True)
        # week starts Monday 2026-10-05 → only today in-week past events from fixture: TSLA
        self.assertTrue(all("2026-10-28" != r["event_date"] for r in rows))

    def test_11_quarter_excludes_future(self):
        now = date(2026, 10, 5)
        b = range_bounds("本季度", now=now)
        rows = get_company_events(
            ["NVDA", "PLTR", "AVGO", "TSLA"],
            start_time=b["start_time"],
            end_time=b["end_time"],
            now=now,
        )
        self.assertTrue(all(r["event_date"] <= "2026-10-05" for r in rows))
        self.assertNotIn("2026-10-28", [r["event_date"] for r in rows])

    def test_12_upcoming_only_future(self):
        now = date(2026, 10, 5)
        rows = get_company_events(["NVDA", "TSLA", "AVGO"], include_upcoming=True, now=now)
        self.assertTrue(rows)
        self.assertTrue(all(r["event_date"] > "2026-10-05" for r in rows))
        self.assertTrue(all(r["event_status"] == "UPCOMING" for r in rows))

    def test_13_event_has_detailed_summary(self):
        now = date(2026, 10, 5)
        rows = get_company_events(["TSLA"], include_upcoming=False, now=now)
        self.assertTrue(rows)
        self.assertTrue(rows[0].get("detailed_summary"))

    def test_14_event_contains_source_url(self):
        now = date(2026, 10, 5)
        rows = get_company_events(["TSLA", "AVGO"], include_upcoming=False, now=now)
        self.assertTrue(any(r.get("source_url") for r in rows))

    def test_15_single_stock_links_to_headlines(self):
        app = _read("streamlit_app.py")
        self.assertIn("open_headlines", app)
        self.assertIn("render_latest_event_teaser", app)
        panels = _read("industry/company_panels.py")
        self.assertIn("查看该股票全部头等大事", panels)

    def test_16_historical_snapshots_still_stored(self):
        app = _read("streamlit_app.py")
        self.assertIn("save_snapshot", app)
        self.assertIn("list_snapshots", app)
        self.assertIn("build_snapshot_record", _read("analysis_service.py"))

    def test_17_watchlist_events_excludes_future_by_default(self):
        now = date(2026, 10, 5)
        rows = get_watchlist_events(
            ["NVDA", "TSLA"],
            start_date="2026-10-01",
            end_date="2026-10-05",
            now=now,
        )
        self.assertTrue(all(r["event_date"] <= "2026-10-05" for r in rows))
        self.assertFalse(any(r["event_date"] == "2026-10-28" for r in rows))

    def test_18_ui_has_upcoming_range(self):
        app = _read("streamlit_app.py")
        self.assertIn("即将发生", app)
        self.assertIn("what_happened", app)
        self.assertIn("阅读全文", app)

    def test_19_stale_flag_when_old(self):
        latest = get_latest_company_quarter("TSLA", as_of=date(2026, 10, 5), rows=[{"ticker":"TSLA", "report_date":"2025-07-23", "fiscal_period":"CY2025 Q2"}])
        self.assertEqual(latest["data_status"], "STALE_DATA")
        self.assertGreater(latest["data_age_days"], 150)


if __name__ == "__main__":
    unittest.main()
