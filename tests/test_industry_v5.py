"""V5.2 Industry + V5.2.2 market snapshot tests."""
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
    load_market_snapshot,
    market_snapshot_block,
    normalize_watchlist_tickers,
    resolve_company,
    show_cloud_module,
    show_compute_module,
    show_memory_module,
    validate_market_snapshot,
)
from industry import ui as industry_ui
from industry.ui import (
    snapshot_chart_rows,
    snapshot_hbm_roles,
    snapshot_qoq_summary,
    snapshot_table_rows,
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

    def test_snapshot_periods_2026_q2(self):
        cloud = market_snapshot_block("cloud")
        dram = market_snapshot_block("dram")
        hbm = market_snapshot_block("hbm")
        self.assertEqual(cloud.get("period"), "2026 Q2")
        self.assertEqual(dram.get("period"), "2026 Q2")
        self.assertEqual(hbm.get("period"), "2026 Q2")
        self.assertEqual(cloud.get("previous_period"), "2026 Q1")
        self.assertEqual(dram.get("previous_period"), "2026 Q1")

    def test_snapshot_share_sums_near_100(self):
        for key in ("cloud", "dram"):
            block = market_snapshot_block(key)
            total = sum(float(c["share"]) for c in block["companies"])
            self.assertAlmostEqual(total, 100.0, delta=1.5, msg=f"{key} sum={total}")

    def test_snapshot_qoq_math(self):
        for key in ("cloud", "dram"):
            for c in market_snapshot_block(key)["companies"]:
                expected = float(c["share"]) - float(c["previous_share"])
                self.assertAlmostEqual(float(c["change_pp"]), expected, delta=0.051)

    def test_snapshot_oracle_not_in_chart(self):
        cloud = market_snapshot_block("cloud")
        chart = snapshot_chart_rows(cloud, order=("AWS", "Microsoft", "Google Cloud", "Others"))
        names = [r["公司"] for r in chart]
        self.assertNotIn("Oracle", names)
        self.assertEqual(names, ["AWS", "Microsoft", "Google Cloud", "Others"])
        by_name = {r["公司"]: r["份额"] for r in chart}
        self.assertEqual(by_name["AWS"], 28.0)
        self.assertEqual(by_name["Microsoft"], 20.0)
        self.assertEqual(by_name["Google Cloud"], 15.0)
        self.assertEqual(by_name["Others"], 37.0)

    def test_snapshot_hbm_no_fabricated_percentage(self):
        hbm = market_snapshot_block("hbm")
        self.assertNotIn("companies", hbm)
        for role in hbm.get("roles") or []:
            self.assertNotIn("share", role)
            self.assertNotIn("share_pct", role)
        roles = snapshot_hbm_roles(hbm)
        self.assertEqual(
            roles,
            [
                ("SK hynix", "Leader"),
                ("Samsung", "Major supplier"),
                ("Micron", "Challenger"),
            ],
        )

    def test_snapshot_source_metadata(self):
        for key in ("cloud", "dram", "hbm"):
            block = market_snapshot_block(key)
            self.assertTrue(str(block.get("source") or "").strip())
            self.assertTrue(str(block.get("source_url") or "").strip())

    def test_snapshot_table_and_qoq_columns(self):
        cloud = market_snapshot_block("cloud")
        table = snapshot_table_rows(cloud, order=("AWS", "Microsoft", "Google Cloud", "Others"))
        self.assertTrue(table)
        for row in table:
            self.assertIn("公司", row)
            self.assertIn("当前份额", row)
            self.assertIn("上季份额", row)
            self.assertIn("QoQ变化", row)
            self.assertIn("排名", row)
        aws = next(r for r in table if r["公司"] == "AWS")
        self.assertEqual(aws["当前份额"], "28.0%")
        self.assertEqual(aws["上季份额"], "28.0%")
        self.assertEqual(aws["QoQ变化"], "+0.0pp")
        qoq = snapshot_qoq_summary(cloud, order=("AWS", "Microsoft", "Google Cloud", "Others"))
        self.assertEqual(qoq[0], ("AWS", "+0.0pp"))
        self.assertEqual(qoq[1], ("Microsoft", "-1.0pp"))
        self.assertEqual(qoq[2], ("Google", "+1.0pp"))

    def test_snapshot_dram_values(self):
        dram = market_snapshot_block("dram")
        by_name = {c["name"]: c for c in dram["companies"]}
        self.assertEqual(by_name["Samsung"]["share"], 39.4)
        self.assertEqual(by_name["Samsung"]["previous_share"], 38.5)
        self.assertEqual(by_name["SK hynix"]["share"], 24.9)
        self.assertEqual(by_name["SK hynix"]["change_pp"], -3.9)
        self.assertEqual(by_name["Micron"]["share"], 23.3)
        self.assertEqual(by_name["Others"]["share"], 12.4)

    def test_validate_market_snapshot_ok(self):
        self.assertEqual(validate_market_snapshot(), [])
        self.assertEqual(validate_market_snapshot(load_market_snapshot()), [])

    def test_ui_reads_snapshot_json_not_hardcoded_shares(self):
        src = _read("industry/ui.py")
        self.assertIn("load_market_snapshot", src)
        self.assertIn("market_snapshot_block", src)
        self.assertIn("Cloud Market Share", src)
        self.assertIn("DRAM Market Share", src)
        self.assertIn("HBM Competitive Position", src)
        self.assertNotIn("load_accelerator_ecosystem", src)
        self.assertNotIn("market_share_rows", src)
        # Shares come from JSON helpers, not literal vendor percentages in UI.
        self.assertNotIn("28.0", src)
        self.assertNotIn("39.4", src)


if __name__ == "__main__":
    unittest.main()
