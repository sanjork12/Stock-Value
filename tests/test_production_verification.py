from __future__ import annotations

import os
import re
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from valuation_engine import (
    MODEL_VERSION,
    is_legacy_snapshot,
    primary_valuation_view,
    reconstruct_blend_from_snapshot,
    reliability_from_snapshot,
    valuate,
)


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(name: str) -> str:
    with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
        return fh.read()


class SchemaAndPolicyStaticTests(unittest.TestCase):
    def test_schema_adds_v41_columns_idempotently(self):
        sql = _read("supabase_schema.sql") + "\n" + _read("supabase_v4_1_production_migration.sql")
        for col in (
            "valuation_class",
            "confidence",
            "models_json",
            "model_version",
            "reliability_score",
            "dispersion_pct",
            "blended_low",
            "blended_high",
            "volatility_1y",
            "reliability_json",
        ):
            self.assertIn(f"add column if not exists {col}", sql.lower())
        self.assertNotRegex(sql, r"(?m)^\s*drop table\b")
        self.assertNotIn("disable row level security", sql.lower())
        self.assertIn("unique(user_id, ticker)", sql)
        self.assertIn("unique(user_id, ticker, snapshot_date)", sql)

    def test_schema_adds_v42_exit_zone_columns(self):
        sql = (_read("supabase_schema.sql") + "\n" + _read("supabase_v4_2_exit_zone_migration.sql")).lower()
        for col in (
            "hold_upper_price",
            "overvalued_price",
            "trim_price",
            "extreme_price",
            "exit_zone_json",
        ):
            self.assertIn(f"add column if not exists {col}", sql)
        self.assertNotRegex(sql, r"(?m)^\s*drop table\b")
        self.assertNotIn("disable row level security", sql)

    def test_policies_are_authenticated_and_owner_scoped(self):
        sql = _read("supabase_schema.sql")
        self.assertIn("to authenticated", sql.lower())
        self.assertNotRegex(sql, r"using\s*\(\s*true\s*\)", re.I)
        self.assertNotRegex(sql, r"with check\s*\(\s*true\s*\)", re.I)
        self.assertIn("auth.uid() = user_id", sql)
        self.assertIn('drop policy if exists "Users can insert own watchlist"', sql)
        self.assertIn('create policy "watchlist_insert_own"', sql)


class SessionAndSecretStaticTests(unittest.TestCase):
    def test_authenticated_client_is_not_cached(self):
        src = _read("streamlit_app.py")
        self.assertNotIn("@st.cache_resource", src)
        self.assertIn("Do not store this client in st.cache_resource", src)
        self.assertNotRegex(src, r"^authenticated_client\s*=", re.M)
        self.assertNotIn("global authenticated_client", src)

    def test_gitignore_covers_secrets(self):
        gitignore = _read(".gitignore")
        self.assertIn(".env", gitignore)
        self.assertIn(".streamlit/secrets.toml", gitignore)
        example = _read(os.path.join(".streamlit", "secrets.toml.example"))
        self.assertNotIn("service_role", example.lower())
        self.assertIn("YOUR_SUPABASE_ANON_KEY", example)
        self.assertIn("SESSION_COOKIE_SECRET", example)

    def test_remember_cookie_is_sealed(self):
        src = _read("streamlit_app.py")
        self.assertIn("_seal_remember_payload", src)
        self.assertIn("SESSION_COOKIE_SECRET", src)
        self.assertIn("seal_remember_payload", src)
        self.assertIn("from cryptography.fernet import Fernet, InvalidToken", _read("remember_session.py"))
        self.assertNotIn("cookie_manager.set(\n            REMEMBER_COOKIE,\n            refresh_token", src)
        self.assertNotIn("keystream", _read("remember_session.py").lower())
        self.assertNotIn("hmac.new", _read("remember_session.py"))

    def test_logs_do_not_print_token_values(self):
        src = _read("streamlit_app.py")
        self.assertNotIn("logger.exception(\"login failed\")", src)
        self.assertIn("has_access_token=%s", src)
        self.assertIn('bool(st.session_state.get("access_token"))', src)
        self.assertNotIn("print(access_token)", src)
        self.assertNotIn("print(refresh_token)", src)
        self.assertNotIn("st.exception", src)


class SnapshotReconstructionTests(unittest.TestCase):
    def test_legacy_snapshot_is_flagged_and_not_backfilled(self):
        snap = {
            "snapshot_date": "2026-09-01",
            "fair_value": 188.25,
            "model_version": None,
            "price": 190,
        }
        self.assertTrue(is_legacy_snapshot(snap))
        blend = reconstruct_blend_from_snapshot(snap)
        self.assertEqual(blend["fair"], 188.25)
        self.assertEqual(blend["model_version"], "legacy")
        self.assertTrue(blend["legacy"])
        self.assertFalse(blend["reliability"])
        self.assertIsNone(blend["reliability"].get("reliability_score") if blend["reliability"] else None)

    def test_v41_snapshot_keeps_saved_reliability(self):
        snap = {
            "snapshot_date": "2026-10-01",
            "fair_value": 291.0,
            "blended_low": 259.0,
            "blended_high": 323.0,
            "confidence": "MEDIUM",
            "model_version": "v4.1-reliability",
            "reliability_score": 71,
            "dispersion_pct": 0.18,
            "reliability_json": {
                "reliability_score": 71,
                "dispersion_pct": 0.18,
                "overall_confidence": "MEDIUM",
            },
        }
        blend = reconstruct_blend_from_snapshot(snap)
        self.assertEqual(blend["fair"], 291.0)
        self.assertEqual(blend["reliability"]["reliability_score"], 71)
        self.assertEqual(blend["model_version"], "v4.1-reliability")
        self.assertFalse(blend["legacy"])

    def test_look_ahead_mock_does_not_call_valuate(self):
        snap = {
            "snapshot_date": "2026-10-01",
            "fair_value": 111,
            "confidence": "LOW",
            "model_version": "v4.1-reliability",
            "reliability_score": 40,
            "dispersion_pct": 0.80,
            "blended_low": 50,
            "blended_high": 200,
            "reliability_json": {"reliability_score": 40, "dispersion_pct": 0.80},
        }
        with patch("valuation_engine.valuate") as mocked:
            first = reconstruct_blend_from_snapshot(snap)
            mocked.assert_not_called()
            self.assertEqual(first["fair"], 111)
            self.assertEqual(first["reliability"]["reliability_score"], 40)
            with patch("valuation_engine.MODEL_VERSION", "v9-future"):
                second = reconstruct_blend_from_snapshot(snap)
            self.assertEqual(second["fair"], 111)
            self.assertEqual(second["model_version"], "v4.1-reliability")
            self.assertEqual(second["reliability"]["reliability_score"], 40)

    def test_reliability_json_wins_over_raw(self):
        snap = {
            "fair_value": 200,
            "confidence": "MEDIUM",
            "reliability_score": 71,
            "reliability_json": {"reliability_score": 71, "overall_confidence": "MEDIUM"},
            "raw": {"reliability_json": {"reliability_score": 10, "overall_confidence": "LOW"}},
        }
        saved = reliability_from_snapshot(snap)
        self.assertEqual(saved["reliability_score"], 71)
        self.assertEqual(saved["overall_confidence"], "MEDIUM")


class PresentationStaticTests(unittest.TestCase):
    def test_low_view_is_range_primary(self):
        view = primary_valuation_view(
            {"confidence": "LOW", "fair": 46.12, "fair_low": 30, "fair_high": 80}
        )
        self.assertEqual(view["mode"], "indicative_range")
        self.assertEqual(view["primary"], "range")
        self.assertEqual(view["label"], "Indicative valuation range")
        src = _read("streamlit_app.py")
        self.assertIn("Indicative Valuation Range", src)
        self.assertIn("Reference midpoint", src)
        self.assertNotIn('c2.metric("参考中枢"', src)

    def test_medium_and_specialized_copy(self):
        medium = primary_valuation_view(
            {"confidence": "MEDIUM", "fair": 291, "fair_low": 259, "fair_high": 323}
        )
        self.assertEqual(medium["label"], "Fair value estimate")
        specialized = primary_valuation_view({"confidence": "SPECIALIZED"})
        self.assertEqual(specialized["mode"], "specialized")
        src = _read("streamlit_app.py")
        self.assertIn("Fair Value Estimate", src)
        self.assertIn("Reasonable Range", src)
        self.assertIn("传统估值模型不适用，需要专项场景估值。", src)
        self.assertIn("该历史快照创建于可靠性层之前，部分可靠性指标不可用。", src)

    def test_dashboard_and_single_share_analyze_one(self):
        src = _read("streamlit_app.py")
        service = _read("analysis_service.py")
        self.assertGreaterEqual(src.count("analyze_one("), 2)
        self.assertIn("return analyze_ticker(", src)
        self.assertIn("r = analyze_one(t, None, db, user_id)", src)
        self.assertIn("r = analyze_one(current, as_of, db, user_id)", src)
        self.assertEqual(service.count("blend = valuate("), 1)

    def test_model_version_constant(self):
        self.assertEqual(MODEL_VERSION, "v4.2-exit-zone")

    def test_upsert_conflict_targets(self):
        src = _read("streamlit_app.py")
        self.assertIn('on_conflict="user_id,ticker,snapshot_date"', src)
        self.assertIn('on_conflict="user_id,ticker"', src)

    def test_error_helper_hides_traceback_for_users(self):
        src = _read("streamlit_app.py")
        self.assertNotIn("st.exception", src)
        self.assertIn("public_analysis_error", src)


class LiveValuateSanityTests(unittest.TestCase):
    """Optional Yahoo-backed checks. Marked skip unless explicitly enabled."""

    def test_specialized_fixture_does_not_emit_fair(self):
        blend = valuate("TSLA", {"forward_eps": 3, "shares": 3e9, "fcf": 1e9, "sector": "Consumer Cyclical", "industry": "Auto Manufacturers"})
        self.assertEqual(blend["confidence"], "SPECIALIZED")
        self.assertIsNone(blend["fair"])


if __name__ == "__main__":
    unittest.main()
