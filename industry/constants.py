"""V5 industry constants and layer taxonomy."""
from __future__ import annotations

LAYERS = (
    "infrastructure",
    "cloud",
    "model_platform",
    "applications",
)

LAYER_LABELS = {
    "infrastructure": "LAYER 1 · Infrastructure / 基础设施",
    "cloud": "LAYER 2 · Cloud / Data Center",
    "model_platform": "LAYER 3 · AI Model / Platform",
    "applications": "LAYER 4 · Applications",
}

LAYER_SHORT = {
    "infrastructure": "Infrastructure",
    "cloud": "Cloud",
    "model_platform": "Model / Platform",
    "applications": "Applications",
}

# Display order top → bottom on map (Applications on top)
LAYER_MAP_ORDER = (
    "applications",
    "model_platform",
    "cloud",
    "infrastructure",
)

MONETIZATION_STATUS = ("DIRECT", "INDIRECT", "EMERGING", "OPTIONALITY")

PROFIT_TAGS = {
    "current": "$$$ Current Profit Engine",
    "emerging": "$$ Emerging Revenue",
    "investment": "→ Investment / Future Optionality",
}

EVENT_IMPACT_LABELS = ("Positive", "Neutral", "Risk", "Strategic")

PRESENCE_LEVELS = ("very_low", "low", "medium", "high", "very_high")

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

REFERENCE_NON_US = ("SAMSUNG", "SKHYNIX")
PRIVATE_REFERENCE = ("OPENAI", "ANTHROPIC")
