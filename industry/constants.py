"""V5.1 industry constants, labels, and short catalyst/risk notes."""
from __future__ import annotations

LAYERS = (
    "infrastructure",
    "cloud",
    "model_platform",
    "applications",
)

LAYER_SHORT = {
    "infrastructure": "Infrastructure",
    "cloud": "Cloud / Data Center",
    "model_platform": "Model / Platform",
    "applications": "Applications",
}

LAYER_SHORT_ZH = {
    "infrastructure": "基础设施",
    "cloud": "云 / 数据中心",
    "model_platform": "模型 / 平台",
    "applications": "应用层",
}

LAYER_MAP_ORDER = (
    "applications",
    "model_platform",
    "cloud",
    "infrastructure",
)

MONETIZATION_STATUS = ("DIRECT", "INDIRECT", "EMERGING", "OPTIONALITY")

CAPEX_INTENSITY_LABEL = {
    "very_low": "Low",
    "low": "Low",
    "medium": "Medium",
    "high": "High",
    "very_high": "Very High",
}

EVENT_IMPACT_LABELS = ("Positive", "Neutral", "Risk", "Strategic")

MAG7 = ("AAPL", "MSFT", "GOOG", "AMZN", "NVDA", "META", "TSLA")

REQUIRED_PUBLIC_UNIVERSE = (
    "AAPL",
    "MSFT",
    "GOOG",
    "AMZN",
    "NVDA",
    "META",
    "TSLA",
    "MU",
    "AVGO",
    "ANET",
    "ORCL",
    "PLTR",
)

# Cloud / memory / compute relevance for dynamic Tab 4
CLOUD_TICKERS = {"AMZN", "MSFT", "GOOG", "GOOGL", "ORCL"}
MEMORY_TICKERS = {"MU", "SAMSUNG", "SKHYNIX", "005930.KS", "000660.KS"}
COMPUTE_TICKERS = {"NVDA", "AVGO", "ANET", "AMD"}

# Short research notes (not investment advice)
COMPANY_INSIGHTS = {
    "NVDA": {
        "catalyst": "Rubin ramp / AI cluster demand",
        "risk": "Hyperscaler self-designed chips",
        "quarter_trend": "improving",
        "quarter_reason": "Data Center demand remains the profit engine",
    },
    "AMZN": {
        "catalyst": "AWS growth / Trainium",
        "risk": "AI CapEx / cloud competition",
        "quarter_trend": "improving",
        "quarter_reason": "AWS growth accelerating",
    },
    "MSFT": {
        "catalyst": "Azure AI / Copilot attach",
        "risk": "Elevated CapEx vs FCF timing",
        "quarter_trend": "improving",
        "quarter_reason": "Intelligent Cloud growth with high CapEx",
    },
    "GOOG": {
        "catalyst": "Gemini distribution + Cloud AI backlog",
        "risk": "Search disruption / CapEx intensity",
        "quarter_trend": "stable",
        "quarter_reason": "Ads cash flow funds Cloud/AI spend",
    },
    "GOOGL": {
        "catalyst": "Gemini distribution + Cloud AI backlog",
        "risk": "Search disruption / CapEx intensity",
        "quarter_trend": "stable",
        "quarter_reason": "Ads cash flow funds Cloud/AI spend",
    },
    "META": {
        "catalyst": "AI ads efficiency / Llama ecosystem",
        "risk": "Reality Labs losses / CapEx spike",
        "quarter_trend": "improving",
        "quarter_reason": "Advertising remains cash engine",
    },
    "AAPL": {
        "catalyst": "Apple Intelligence / Services attach",
        "risk": "iPhone cycle / AI monetization lag",
        "quarter_trend": "stable",
        "quarter_reason": "Services mix supportive; AI still indirect",
    },
    "TSLA": {
        "catalyst": "Robotaxi / Optimus narrative",
        "risk": "Auto demand / execution of autonomy",
        "quarter_trend": "weakening",
        "quarter_reason": "Automotive still dominates; autonomy is optionality",
    },
    "MU": {
        "catalyst": "HBM / cloud memory ramp",
        "risk": "Memory cycle / pricing volatility",
        "quarter_trend": "improving",
        "quarter_reason": "HBM and cloud memory mix rising",
    },
    "ORCL": {
        "catalyst": "OCI AI capacity deals",
        "risk": "Very high CapEx / execution risk",
        "quarter_trend": "improving",
        "quarter_reason": "Cloud backlog narrative with CapEx ramp",
    },
    "PLTR": {
        "catalyst": "US Commercial AIP expansion",
        "risk": "Valuation / concentration / competition",
        "quarter_trend": "improving",
        "quarter_reason": "US Commercial growth accelerating",
    },
    "AVGO": {
        "catalyst": "Custom XPUs / AI networking",
        "risk": "Customer concentration / cycle",
        "quarter_trend": "improving",
        "quarter_reason": "AI semiconductor demand commentary strong",
    },
    "ANET": {
        "catalyst": "AI cluster networking demand",
        "risk": "Cloud CapEx pauses / competition",
        "quarter_trend": "improving",
        "quarter_reason": "Product growth tied to AI clusters",
    },
    "CRM": {
        "catalyst": "Agentforce monetization",
        "risk": "AI attach slower than expected",
        "quarter_trend": "stable",
        "quarter_reason": "Core CRM still the profit engine",
    },
    "NOW": {
        "catalyst": "Now Assist / workflow agents",
        "risk": "Enterprise IT spend cycles",
        "quarter_trend": "stable",
        "quarter_reason": "Subscription platform remains core",
    },
    "SNOW": {
        "catalyst": "Cortex / AI Data Cloud",
        "risk": "Consumption volatility / competition",
        "quarter_trend": "stable",
        "quarter_reason": "Data cloud consumption is primary",
    },
    "ADBE": {
        "catalyst": "Firefly / GenStudio",
        "risk": "Creative GenAI competition",
        "quarter_trend": "stable",
        "quarter_reason": "Creative subscriptions still core",
    },
    "CRWD": {
        "catalyst": "Charlotte AI / AI SOC",
        "risk": "Security competition / incident risk",
        "quarter_trend": "stable",
        "quarter_reason": "Security cloud subscriptions dominate",
    },
}

TREND_LABEL = {
    "improving": "↑ Improving",
    "stable": "→ Stable",
    "weakening": "↓ Weakening",
}
