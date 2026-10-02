from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis_service import analyze_ticker, fetch_historical_snapshot
from remember_session import seal_remember_payload, unseal_remember_payload
from test_v41_regression import _ohlcv


class FakeError(Exception):
    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.code = code

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRET = "unit-test-session-cookie-secret"
TOKEN = "sb-refresh-token-example-value"


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error

    def select(self, *args, **kwargs):
        return self

    def eq(self, *args, **kwargs):
        return self

    def lte(self, *args, **kwargs):
        return self

    def order(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def execute(self):
        if self._error is not None:
            raise self._error
        return FakeResult(self._result)


class FakeSB:
    def __init__(self, result=None, error=None):
        self._query = FakeQuery(result=result, error=error)

    def table(self, name):
        return self._query


class RememberSessionTests(unittest.TestCase):
    def test_cookie_does_not_contain_raw_refresh_token(self):
        sealed = seal_remember_payload(TOKEN, SECRET)
        self.assertIsNotNone(sealed)
        self.assertNotIn(TOKEN, sealed)

    def test_valid_payload_roundtrip(self):
        sealed = seal_remember_payload(TOKEN, SECRET)
        self.assertEqual(unseal_remember_payload(sealed, SECRET), TOKEN)

    def test_tampered_payload_fails(self):
        sealed = seal_remember_payload(TOKEN, SECRET)
        mutated = sealed[:-4] + ("A" if sealed[-4] != "A" else "B") + sealed[-3:]
        self.assertIsNone(unseal_remember_payload(mutated, SECRET))

    def test_wrong_secret_fails(self):
        sealed = seal_remember_payload(TOKEN, SECRET)
        self.assertIsNone(unseal_remember_payload(sealed, "different-secret-value"))

    def test_expired_payload_fails(self):
        past = datetime.now(timezone.utc) - timedelta(days=40)
        sealed = seal_remember_payload(TOKEN, SECRET, ttl_days=30, now=past)
        self.assertIsNone(unseal_remember_payload(sealed, SECRET))

    def test_missing_secret_disables_persist(self):
        self.assertIsNone(seal_remember_payload(TOKEN, None))
        self.assertIsNone(unseal_remember_payload("anything", None))


class HistoricalSnapshotTests(unittest.TestCase):
    def test_empty_result_returns_none(self):
        self.assertIsNone(fetch_historical_snapshot(FakeSB(result=[]), "user-1", "AAPL", "2026-10-01"))

    def test_schema_cache_error_raises(self):
        err = FakeError(
            "Could not find the 'reliability_score' column of 'valuation_snapshots' in the schema cache",
            "PGRST204",
        )
        with self.assertRaises(FakeError):
            fetch_historical_snapshot(FakeSB(error=err), "user-1", "AAPL", "2026-10-01")

    def test_rls_error_raises(self):
        err = FakeError("new row violates row-level security policy", "42501")
        with self.assertRaises(FakeError):
            fetch_historical_snapshot(FakeSB(error=err), "user-1", "AAPL", "2026-10-01")

    def test_empty_snapshot_note_vs_fetch_failure(self):
        empty = analyze_ticker(
            "AAPL",
            "2020-01-02",
            history_loader=lambda t, d: _ohlcv(100.0),
            snapshot_loader=lambda t, d: None,
        )
        self.assertIn("该日期没有历史估值快照", empty["note"])
        self.assertIsNone(empty.get("snapshot_error"))

        def boom(_t, _d):
            raise FakeError("schema cache", "PGRST204")

        failed = analyze_ticker(
            "AAPL",
            "2020-01-02",
            history_loader=lambda t, d: _ohlcv(100.0),
            snapshot_loader=boom,
        )
        self.assertEqual(failed["snapshot_error"], "历史估值暂时读取失败，请稍后重试。")
        self.assertNotIn("该日期没有历史估值快照", failed["note"])
        self.assertEqual(failed["price"], 100.0)

    def test_get_cloud_snapshot_does_not_swallow_schema_errors(self):
        with open(os.path.join(ROOT, "streamlit_app.py"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("return fetch_historical_snapshot(sb, current_user_id, ticker, as_of)", src)
        fn = src.split("def get_cloud_snapshot", 1)[1].split("def analyze_one", 1)[0]
        self.assertNotIn("return None", fn)

    def test_analyze_one_snapshot_loader_has_single_return_none(self):
        with open(os.path.join(ROOT, "streamlit_app.py"), encoding="utf-8") as fh:
            src = fh.read()
        fn = src.split("def analyze_one", 1)[1].split("def save_snapshot", 1)[0]
        self.assertEqual(fn.count("return None"), 1)


if __name__ == "__main__":
    unittest.main()
