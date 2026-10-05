"""V5.4 News Intelligence — provider architecture + headline feed."""
from industry.news.providers import (
    ExternalNewsProvider,
    IRProvider,
    NewsProvider,
    SECProvider,
    StaticDemoProvider,
    default_providers,
    external_news_configured,
    has_configured_live_source,
    news_demo_mode_enabled,
)
from industry.news.schema import (
    normalize_event,
    texts_too_similar,
    translate_ui_term,
)
from industry.news.service import get_company_events, news_source_status, range_bounds

__all__ = [
    "NewsProvider",
    "SECProvider",
    "IRProvider",
    "ExternalNewsProvider",
    "StaticDemoProvider",
    "default_providers",
    "get_company_events",
    "range_bounds",
    "news_source_status",
    "news_demo_mode_enabled",
    "external_news_configured",
    "has_configured_live_source",
    "normalize_event",
    "texts_too_similar",
    "translate_ui_term",
]
