"""Headline news service: aggregate providers → normalized Events (V5.4)."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Sequence

from industry.news.providers import (
    NewsProvider,
    StaticDemoProvider,
    default_providers,
    has_configured_live_source,
    news_demo_mode_enabled,
)
from industry.news.schema import (
    PER_TICKER_LIMITS,
    apply_per_ticker_limits,
    importance_sort_key,
    is_low_priority_headline,
    is_material_importance,
    normalize_event,
    parse_date,
    texts_too_similar,
)


def range_bounds(range_key: str, *, now: Optional[date] = None) -> Dict[str, Any]:
    """Map UI range labels → start/end/include_upcoming."""
    today = now or date.today()
    key = str(range_key or "").strip()
    if key in {"即将发生", "upcoming", "UPCOMING"}:
        return {"start_time": None, "end_time": None, "include_upcoming": True}
    if key in {"过去24小时", "24h"}:
        start = today - timedelta(days=1)
        return {
            "start_time": start.isoformat(),
            "end_time": today.isoformat(),
            "include_upcoming": False,
        }
    if key in {"本周", "week"}:
        start = today - timedelta(days=today.weekday())
        return {
            "start_time": start.isoformat(),
            "end_time": today.isoformat(),
            "include_upcoming": False,
        }
    # 本季度
    q = (today.month - 1) // 3
    start = date(today.year, q * 3 + 1, 1)
    return {
        "start_time": start.isoformat(),
        "end_time": today.isoformat(),
        "include_upcoming": False,
    }


def _collect_raw(
    tickers: Sequence[str],
    *,
    start_time: Optional[str],
    end_time: Optional[str],
    providers: Sequence[NewsProvider],
) -> List[Dict[str, Any]]:
    raw_rows: List[Dict[str, Any]] = []
    for provider in providers:
        for t in tickers:
            try:
                items = provider.fetch_company_news(t, start_time, end_time)
            except Exception:
                items = []
            for item in items or []:
                row = dict(item)
                row.setdefault("ticker", t)
                row.setdefault("source_type", getattr(provider, "source_type", "unknown"))
                raw_rows.append(row)
    return raw_rows


def _in_range(
    ev: Dict[str, Any],
    *,
    start: Optional[date],
    end: Optional[date],
    include_upcoming: bool,
    today: date,
) -> bool:
    ed = parse_date(ev.get("event_time") or ev.get("event_date") or ev.get("published_at"))
    if ed is None:
        return False
    if include_upcoming:
        return ed > today
    if ed > today:
        return False
    if end is not None and ed > end:
        return False
    if start is not None and ed < start:
        return False
    return True


def get_company_events(
    tickers: Sequence[Any],
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    include_upcoming: bool = False,
    *,
    now: Optional[date] = None,
    providers: Optional[Sequence[NewsProvider]] = None,
    range_key: Optional[str] = None,
    apply_limits: bool = True,
    material_only: bool = True,
) -> List[Dict[str, Any]]:
    """
    Public facade used by 头等大事 / single-stock teaser.

    Past windows: start <= event_time <= now (never future).
    Upcoming: event_time > now only.
    """
    from industry.loader import normalize_watchlist_tickers

    today = now or date.today()
    tick_list = normalize_watchlist_tickers(tickers)
    if not tick_list:
        return []

    impls = list(providers) if providers is not None else default_providers()
    # When callers inject providers for tests, honor them as-is.
    raw_rows = _collect_raw(
        tick_list,
        start_time=start_time,
        end_time=end_time if not include_upcoming else None,
        providers=impls,
    )

    start = parse_date(start_time)
    end = parse_date(end_time) or today

    normalized: List[Dict[str, Any]] = []
    seen_ids = set()
    for raw in raw_rows:
        # Hide demo_static unless demo mode (even if a caller injected StaticDemoProvider)
        stype = str(raw.get("source_type") or "").strip()
        if stype == "demo_static" and not news_demo_mode_enabled():
            # Allow only when the injected provider list is solely for tests that
            # already set NEWS_DEMO_MODE — double-check env.
            continue
        ev = normalize_event(raw, now=today)
        if not ev.get("ticker"):
            continue
        if not _in_range(
            ev, start=start, end=end, include_upcoming=include_upcoming, today=today
        ):
            continue
        # Quality: require distinct summary vs why for material feed
        if material_only and texts_too_similar(ev.get("what_happened"), ev.get("why_it_matters")):
            ev["content_quality_ok"] = False
        eid = ev.get("event_id")
        if eid in seen_ids:
            continue
        seen_ids.add(eid)
        normalized.append(ev)

    if material_only:
        candidates = [
            e
            for e in normalized
            if is_material_importance(e.get("importance")) and e.get("content_quality_ok", True)
        ]
    else:
        candidates = list(normalized)

    limit = 0
    if apply_limits:
        key = range_key or ("upcoming" if include_upcoming else "quarter")
        limit = PER_TICKER_LIMITS.get(key, 5)
        candidates = apply_per_ticker_limits(candidates, per_ticker_limit=limit)
    else:
        candidates = [
            e
            for e in candidates
            if e.get("content_quality_ok", True) and not is_low_priority_headline(e)
        ]

    candidates.sort(key=lambda e: str(e.get("event_time") or ""), reverse=True)
    candidates.sort(key=importance_sort_key)
    return candidates


def news_source_status() -> Dict[str, Any]:
    """UI helper for empty-state messaging."""
    demo = news_demo_mode_enabled()
    live = has_configured_live_source()
    return {
        "demo_mode": demo,
        "live_configured": live,
        "showing_demo": demo,
        "message_if_empty": (
            None
            if (demo or live)
            else "当前未配置实时新闻源。"
        ),
    }


# Re-export for convenience
__all__ = [
    "get_company_events",
    "range_bounds",
    "news_source_status",
    "news_demo_mode_enabled",
    "StaticDemoProvider",
]
