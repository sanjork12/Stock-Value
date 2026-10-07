"""NewsProvider adapters: SEC / IR / External API / static demo (V5.4)."""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from datetime import date
from typing import Any, Dict, List, Optional, Sequence


def news_demo_mode_enabled() -> bool:
    return str(os.environ.get("NEWS_DEMO_MODE", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def external_news_configured() -> bool:
    from finnhub_service import get_finnhub_provider
    return get_finnhub_provider().configured()


class NewsProvider(ABC):
    """Fetch standardized raw news items for a ticker."""

    name: str = "base"
    source_type: str = "unknown"

    @abstractmethod
    def fetch_company_news(
        self,
        ticker: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Return raw items with at least:
          headline, published_at, source, url, summary/raw_text, ticker
        """
        raise NotImplementedError


class SECProvider(NewsProvider):
    """SEC EDGAR filings adapter (stub — wire EDGAR when credentials/network ready)."""

    name = "sec_edgar"
    source_type = "sec"

    def fetch_company_news(
        self,
        ticker: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        # V5.4: architecture only — no live EDGAR scrape this round.
        _ = (ticker, start_time, end_time)
        return []


class IRProvider(NewsProvider):
    """Company Investor Relations / RSS adapter (stub)."""

    name = "company_ir"
    source_type = "ir"

    def fetch_company_news(
        self,
        ticker: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        _ = (ticker, start_time, end_time)
        return []


class ExternalNewsProvider(NewsProvider):
    """Finnhub / Polygon / NewsAPI style market-news adapter."""

    name = "external_news"
    source_type = "market_api"

    def fetch_company_news(
        self,
        ticker: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        _ = (ticker, start_time, end_time)
        if not external_news_configured():
            return []
        from finnhub_service import get_finnhub_provider
        from industry.news.finnhub_live import normalize_finnhub_news
        from datetime import timedelta
        end = str(end_time or date.today().isoformat())[:10]
        start = str(start_time or (date.today() - timedelta(days=90)).isoformat())[:10]
        result = get_finnhub_provider().get_company_news(ticker, start, end)
        return [event for raw in result.get("data") or [] if (event := normalize_finnhub_news(raw, ticker))]


class StaticDemoProvider(NewsProvider):
    """Curated data/industry/events.json — demo only, never pretend to be live."""

    name = "static_demo"
    source_type = "demo_static"

    def fetch_company_news(
        self,
        ticker: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not news_demo_mode_enabled():
            return []
        from industry.loader import load_events, resolve_company, _aliases

        t = str(ticker or "").upper()
        aliases = {t}
        c = resolve_company(t)
        if c:
            aliases |= set(_aliases(c))

        out: List[Dict[str, Any]] = []
        for raw in load_events():
            ek = str(raw.get("company_id") or raw.get("ticker") or "").upper()
            tk = str(raw.get("ticker") or "").upper()
            if ek not in aliases and tk not in aliases:
                continue
            item = dict(raw)
            item["ticker"] = t
            item["source_type"] = "demo_static"
            # Service layer applies strict time bounds / upcoming split.
            _ = (start_time, end_time)
            out.append(item)
        return out


def default_providers() -> List[NewsProvider]:
    """Priority: SEC → IR → External API → (demo if enabled)."""
    providers: List[NewsProvider] = [SECProvider(), IRProvider(), ExternalNewsProvider()]
    if news_demo_mode_enabled():
        providers.append(StaticDemoProvider())
    return providers


def has_configured_live_source() -> bool:
    """True when a non-demo path is expected to produce data (API key present)."""
    return external_news_configured()
