"""Company events provider interface + static JSON adapter (V5.3)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence


def _parse_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()[:10]
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value if str(x).strip()]
    text = str(value).strip()
    return [text] if text else []


def enrich_event_record(ev: Dict[str, Any], *, now: Optional[date] = None) -> Dict[str, Any]:
    """Normalize a raw event dict into the provider schema."""
    from industry.loader import derive_impact_area, impact_to_importance

    today = now or date.today()
    ed = _parse_date(ev.get("event_time") or ev.get("event_date") or ev.get("published_at"))
    status = str(ev.get("event_status") or "").upper()
    if status not in {"PAST", "UPCOMING"}:
        status = "UPCOMING" if (ed and ed > today) else "PAST"
    detailed = ev.get("detailed_summary")
    if not detailed:
        detailed = [
            x
            for x in [
                ev.get("summary"),
                ev.get("financial_impact"),
                ev.get("strategic_impact"),
            ]
            if x
        ]
    if isinstance(detailed, str):
        detailed = [detailed]
    impact_areas = ev.get("impact_areas")
    if not impact_areas:
        area = derive_impact_area(ev)
        impact_areas = [area] if area else []
    return {
        "event_id": ev.get("event_id")
        or f"{ev.get('ticker') or ev.get('company_id')}-{ev.get('event_date')}-{ev.get('event_type')}",
        "ticker": str(ev.get("ticker") or ev.get("company_id") or "").upper(),
        "event_time": (ed.isoformat() if ed else str(ev.get("event_date") or "")[:10]),
        "event_date": (ed.isoformat() if ed else str(ev.get("event_date") or "")[:10]),
        "event_status": status,
        "event_type": ev.get("event_type") or "product",
        "importance": impact_to_importance(ev.get("impact_label") or ev.get("importance")),
        "headline": ev.get("headline") or "",
        "short_summary": ev.get("summary") or ev.get("short_summary") or "",
        "detailed_summary": list(detailed or []),
        "why_it_matters": ev.get("why_it_matters")
        or ev.get("strategic_impact")
        or ev.get("financial_impact")
        or "",
        "impact_areas": _as_list(impact_areas),
        "impact_area": (_as_list(impact_areas)[0] if _as_list(impact_areas) else derive_impact_area(ev)),
        "sentiment_or_impact": ev.get("impact_label") or ev.get("sentiment_or_impact") or "Neutral",
        "source_name": ev.get("source_name") or ev.get("source") or "",
        "source_url": ev.get("source_url") or "",
        "published_at": str(ev.get("published_at") or ev.get("event_date") or "")[:10],
        "layer_impact": list(ev.get("layer_impact") or []),
    }


class CompanyEventsProvider(ABC):
    """Future adapters: SEC EDGAR / Company IR / Finnhub / NewsAPI."""

    @abstractmethod
    def get_company_events(
        self,
        tickers: Sequence[Any],
        *,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        include_upcoming: bool = False,
        now: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError


class StaticEventsProvider(CompanyEventsProvider):
    """V5.3 default: curated data/industry/events.json."""

    def get_company_events(
        self,
        tickers: Sequence[Any],
        *,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        include_upcoming: bool = False,
        now: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        from industry.loader import (
            load_events,
            normalize_watchlist_tickers,
            resolve_company,
            watchlist_keys,
        )

        today = now or date.today()
        tick_list = normalize_watchlist_tickers(tickers)
        if not tick_list:
            return []

        start = _parse_date(start_time)
        end = _parse_date(end_time) or today

        keys = watchlist_keys(tick_list)
        alias_to_display: Dict[str, str] = {}
        for t in tick_list:
            alias_to_display[t] = t
            c = resolve_company(t)
            if c:
                from industry.loader import _aliases

                for a in _aliases(c):
                    alias_to_display[a] = t

        out: List[Dict[str, Any]] = []
        for raw in load_events():
            enriched = enrich_event_record(raw, now=today)
            ek = str(raw.get("company_id") or raw.get("ticker") or "").upper()
            tk = str(raw.get("ticker") or "").upper()
            match_key = ek if ek in keys else (tk if tk in keys else None)
            if not match_key:
                continue
            ed = _parse_date(enriched.get("event_time"))
            if ed is None:
                continue
            if include_upcoming:
                if ed <= today:
                    continue
            else:
                if ed > today:
                    continue
                if ed > end:
                    continue
                if start is not None and ed < start:
                    continue
            enriched["ticker"] = alias_to_display.get(match_key) or alias_to_display.get(tk) or match_key
            out.append(enriched)
        out.sort(key=lambda r: str(r.get("event_time") or ""), reverse=True)
        return out


_DEFAULT_PROVIDER: Optional[CompanyEventsProvider] = None


def get_events_provider() -> CompanyEventsProvider:
    global _DEFAULT_PROVIDER
    if _DEFAULT_PROVIDER is None:
        _DEFAULT_PROVIDER = StaticEventsProvider()
    return _DEFAULT_PROVIDER


def get_company_events(
    tickers: Sequence[Any],
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    include_upcoming: bool = False,
    *,
    now: Optional[date] = None,
    provider: Optional[CompanyEventsProvider] = None,
) -> List[Dict[str, Any]]:
    """Public facade used by 头等大事 / single-stock teaser."""
    impl = provider or get_events_provider()
    return impl.get_company_events(
        tickers,
        start_time=start_time,
        end_time=end_time,
        include_upcoming=include_upcoming,
        now=now,
    )


def range_bounds(range_key: str, *, now: Optional[date] = None) -> Dict[str, Any]:
    """Map UI range labels → start/end/include_upcoming."""
    today = now or date.today()
    key = str(range_key or "").strip()
    if key in {"即将发生", "upcoming", "UPCOMING"}:
        return {"start_time": None, "end_time": None, "include_upcoming": True}
    if key in {"过去24小时", "24h"}:
        start = today - timedelta(days=1)
        return {"start_time": start.isoformat(), "end_time": today.isoformat(), "include_upcoming": False}
    if key in {"本周", "week"}:
        # Monday-start week through today
        start = today - timedelta(days=today.weekday())
        return {"start_time": start.isoformat(), "end_time": today.isoformat(), "include_upcoming": False}
    # 本季度
    q = (today.month - 1) // 3
    start = date(today.year, q * 3 + 1, 1)
    return {"start_time": start.isoformat(), "end_time": today.isoformat(), "include_upcoming": False}
