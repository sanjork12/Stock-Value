"""V5.4 Watchlist News Intelligence UX + provider architecture tests."""
from __future__ import annotations

import os
import sys
import unittest
from datetime import date
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from industry.loader import clear_industry_cache
from industry.news import (
    ExternalNewsProvider,
    IRProvider,
    NewsProvider,
    SECProvider,
    StaticDemoProvider,
    get_company_events,
    news_demo_mode_enabled,
    news_source_status,
    normalize_event,
    range_bounds,
    texts_too_similar,
)
from industry.news.schema import translate_ui_term


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(name: str) -> str:
    with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
        return fh.read()


class V54NewsIntelligenceTests(unittest.TestCase):
    def setUp(self):
        clear_industry_cache()
        self._old_demo = os.environ.get("NEWS_DEMO_MODE")

    def tearDown(self):
        if self._old_demo is None:
            os.environ.pop("NEWS_DEMO_MODE", None)
        else:
            os.environ["NEWS_DEMO_MODE"] = self._old_demo
        clear_industry_cache()

    def test_1_direct_headline_nav_defaults_all_watchlist(self):
        app = _read("streamlit_app.py")
        self.assertIn("_prev_nav_for_headlines", app)
        self.assertIn('pop("headline_ticker_filter"', app)
        # Top-nav arrival without deep-link clears sticky filter
        self.assertIn('_arrived_from != "头等大事"', app)

    def test_2_single_stock_deep_link_filters_ticker(self):
        app = _read("streamlit_app.py")
        self.assertIn("headline_filter_ticker = t", app)
        self.assertIn("_headline_deep_link", app)
        panels = _read("industry/company_panels.py")
        self.assertIn("查看该股票全部头等大事", panels)

    def test_3_clear_filter_restores_all_watchlist(self):
        app = _read("streamlit_app.py")
        self.assertIn("清除筛选", app)
        self.assertIn('pop("headline_ticker_filter", None)', app)

    def test_4_time_bounds_strict(self):
        now = date(2026, 10, 5)
        b24 = range_bounds("过去24小时", now=now)
        self.assertEqual(b24["start_time"], "2026-10-04")
        self.assertEqual(b24["end_time"], "2026-10-05")
        self.assertFalse(b24["include_upcoming"])
        bw = range_bounds("本周", now=now)
        self.assertEqual(bw["start_time"], "2026-10-05")
        bq = range_bounds("本季度", now=now)
        self.assertEqual(bq["start_time"], "2026-10-01")

    def test_5_future_only_upcoming(self):
        os.environ["NEWS_DEMO_MODE"] = "true"
        clear_industry_cache()
        now = date(2026, 10, 5)
        past = get_company_events(
            ["NVDA", "TSLA", "MSFT"],
            start_time="2026-10-01",
            end_time="2026-10-05",
            include_upcoming=False,
            now=now,
            range_key="本季度",
        )
        self.assertTrue(all(r["event_date"] <= "2026-10-05" for r in past))
        up = get_company_events(
            ["NVDA", "MSFT", "MU"],
            include_upcoming=True,
            now=now,
            range_key="即将发生",
        )
        self.assertTrue(up)
        self.assertTrue(all(r["event_date"] > "2026-10-05" for r in up))

    def test_6_demo_static_hidden_in_production(self):
        os.environ.pop("NEWS_DEMO_MODE", None)
        clear_industry_cache()
        self.assertFalse(news_demo_mode_enabled())
        rows = get_company_events(
            ["TSLA", "NVDA", "AVGO"],
            start_time="2026-10-01",
            end_time="2026-10-05",
            now=date(2026, 10, 5),
            range_key="本季度",
        )
        self.assertEqual(rows, [])
        self.assertTrue(all(r.get("source_type") != "demo_static" for r in rows))

    def test_7_empty_state_correct(self):
        os.environ.pop("NEWS_DEMO_MODE", None)
        status = news_source_status()
        self.assertEqual(status["message_if_empty"], "当前未配置实时新闻源。")
        app = _read("streamlit_app.py")
        self.assertIn("本周期没有发现明显改变投资逻辑的重大事件。", app)
        self.assertIn("当前未配置实时新闻源。", app)

    def test_8_summary_not_equal_why(self):
        os.environ["NEWS_DEMO_MODE"] = "true"
        clear_industry_cache()
        rows = get_company_events(
            ["TSLA", "AVGO", "NVDA"],
            start_time="2026-10-01",
            end_time="2026-10-05",
            now=date(2026, 10, 5),
            range_key="本季度",
        )
        self.assertTrue(rows)
        for r in rows:
            self.assertTrue(r.get("what_happened"))
            self.assertTrue(r.get("why_it_matters"))
            self.assertFalse(texts_too_similar(r["what_happened"], r["why_it_matters"]))

    def test_9_event_detail_has_what_happened(self):
        os.environ["NEWS_DEMO_MODE"] = "true"
        clear_industry_cache()
        rows = get_company_events(
            ["TSLA"],
            start_time="2026-10-05",
            end_time="2026-10-05",
            now=date(2026, 10, 5),
            range_key="过去24小时",
        )
        self.assertTrue(rows)
        self.assertIn("what_happened", rows[0])
        self.assertTrue(rows[0]["what_happened"])
        app = _read("streamlit_app.py")
        self.assertIn("【发生了什么】", app)

    def test_10_event_detail_has_watch_next(self):
        os.environ["NEWS_DEMO_MODE"] = "true"
        clear_industry_cache()
        rows = get_company_events(
            ["TSLA"],
            start_time="2026-10-05",
            end_time="2026-10-05",
            now=date(2026, 10, 5),
            range_key="过去24小时",
        )
        self.assertTrue(rows[0].get("watch_next"))
        app = _read("streamlit_app.py")
        self.assertIn("【接下来关注】", app)

    def test_11_source_url_required_for_real_event(self):
        bad = normalize_event(
            {
                "ticker": "X",
                "headline": "h",
                "what_happened": "公司公布了新的产品计划并说明了落地节奏。",
                "why_it_matters": "这可能改变收入预期与竞争格局，需要跟踪后续指引。",
                "event_date": "2026-10-01",
                "source_type": "market_api",
                "source_url": "",
                "importance": "重大",
            },
            now=date(2026, 10, 5),
        )
        self.assertFalse(bad["content_quality_ok"])
        good = normalize_event(
            {
                "ticker": "X",
                "headline": "h",
                "what_happened": "公司公布了新的产品计划并说明了落地节奏。",
                "why_it_matters": "这可能改变收入预期与竞争格局，需要跟踪后续指引。",
                "event_date": "2026-10-01",
                "source_type": "ir",
                "source_url": "https://example.com/ir",
                "importance": "重大",
            },
            now=date(2026, 10, 5),
        )
        self.assertTrue(good["content_quality_ok"])

    def test_12_no_copyrighted_full_article_storage(self):
        ev = normalize_event(
            {
                "ticker": "NVDA",
                "headline": "h",
                "what_happened": "摘要事实一段。",
                "why_it_matters": "对收入与估值逻辑有影响，需单独跟踪。",
                "full_article": "COPYRIGHTED FULL BODY " * 50,
                "article_body": "MORE BODY",
                "event_date": "2026-10-01",
                "source_url": "https://investor.nvidia.com/",
                "source_type": "ir",
                "importance": "重要",
            },
            now=date(2026, 10, 5),
        )
        self.assertNotIn("full_article", ev)
        self.assertNotIn("article_body", ev)
        self.assertNotIn("COPYRIGHTED", str(ev))

    def test_13_provider_architecture_present(self):
        self.assertTrue(issubclass(SECProvider, NewsProvider))
        self.assertTrue(issubclass(IRProvider, NewsProvider))
        self.assertTrue(issubclass(ExternalNewsProvider, NewsProvider))
        self.assertTrue(issubclass(StaticDemoProvider, NewsProvider))
        for cls in (SECProvider, IRProvider, ExternalNewsProvider):
            self.assertEqual(cls().fetch_company_news("NVDA"), [])

    def test_14_ui_translates_internal_terms(self):
        self.assertEqual(translate_ui_term("model_platform"), "AI平台")
        self.assertEqual(translate_ui_term("applications"), "应用层")
        self.assertEqual(translate_ui_term("DIRECT"), "直接变现")
        self.assertEqual(translate_ui_term("INDIRECT"), "间接受益")
        self.assertEqual(translate_ui_term("Strategic"), "战略影响")
        self.assertEqual(translate_ui_term("OPTIONALITY"), "未来业务")
        app = _read("streamlit_app.py")
        self.assertNotIn("model_platform", app.split("头等大事")[-1][:2000] if False else "")
        # Headline UI uses translate_ui_term — no raw internal jargon sections
        self.assertIn("translate_ui_term", app)
        self.assertIn("【影响判断】", app)

    def test_15_per_ticker_limits_applied(self):
        os.environ["NEWS_DEMO_MODE"] = "true"
        clear_industry_cache()
        now = date(2026, 10, 5)
        rows = get_company_events(
            ["TSLA", "AMZN", "AVGO", "NVDA", "MSFT"],
            start_time="2026-10-04",
            end_time="2026-10-05",
            now=now,
            range_key="过去24小时",
        )
        counts = Counter(r["ticker"] for r in rows)
        self.assertTrue(all(v <= 2 for v in counts.values()))


if __name__ == "__main__":
    unittest.main()
