"""Company events provider — thin V5.3/V5.4 compatibility facade."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import Any, Dict, List, Optional, Sequence

from industry.news.schema import normalize_event as enrich_event_record
from industry.news.service import get_company_events as _service_get_company_events
from industry.news.service import range_bounds


class CompanyEventsProvider(ABC):
    """Legacy name kept for imports; prefer industry.news.NewsProvider."""

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
    """Delegates to the V5.4 news service (demo when NEWS_DEMO_MODE=true)."""

    def get_company_events(
        self,
        tickers: Sequence[Any],
        *,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        include_upcoming: bool = False,
        now: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        return _service_get_company_events(
            tickers,
            start_time=start_time,
            end_time=end_time,
            include_upcoming=include_upcoming,
            now=now,
        )


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
    range_key: Optional[str] = None,
    apply_limits: bool = True,
    material_only: bool = True,
) -> List[Dict[str, Any]]:
    """Public facade used by 头等大事 / single-stock teaser."""
    if provider is not None:
        return provider.get_company_events(
            tickers,
            start_time=start_time,
            end_time=end_time,
            include_upcoming=include_upcoming,
            now=now,
        )
    return _service_get_company_events(
        tickers,
        start_time=start_time,
        end_time=end_time,
        include_upcoming=include_upcoming,
        now=now,
        range_key=range_key,
        apply_limits=apply_limits,
        material_only=material_only,
    )


__all__ = [
    "CompanyEventsProvider",
    "StaticEventsProvider",
    "enrich_event_record",
    "get_events_provider",
    "get_company_events",
    "range_bounds",
]
