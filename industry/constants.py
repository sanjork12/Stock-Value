"""V5 industry constants and layer taxonomy."""
from __future__ import annotations

LAYERS = (
    "infrastructure",
    "cloud",
    "model_platform",
    "applications",
)

LAYER_LABELS = {
    "infrastructure": "第1层 · 基础设施",
    "cloud": "第2层 · 云 / 数据中心",
    "model_platform": "第3层 · AI 模型 / 平台",
    "applications": "第4层 · 应用层",
}

LAYER_SHORT = {
    "infrastructure": "基础设施",
    "cloud": "云 / 数据中心",
    "model_platform": "模型 / 平台",
    "applications": "应用层",
}

# Display order top → bottom on map (Applications on top)
LAYER_MAP_ORDER = (
    "applications",
    "model_platform",
    "cloud",
    "infrastructure",
)

MONETIZATION_STATUS = ("DIRECT", "INDIRECT", "EMERGING", "OPTIONALITY")

MONETIZATION_ZH = {
    "DIRECT": "直接变现",
    "INDIRECT": "间接变现",
    "EMERGING": "新兴变现",
    "OPTIONALITY": "期权式叙事",
}

PROFIT_TAGS = {
    "current": "$$$ 当前利润引擎",
    "emerging": "$$ 新兴收入",
    "investment": "→ 投入 / 未来期权",
}

PRESENCE_ZH = {
    "very_low": "极低",
    "low": "低",
    "medium": "中",
    "high": "高",
    "very_high": "极高",
}

CAPEX_INTENSITY_ZH = {
    "very_low": "极低",
    "low": "低",
    "medium": "中",
    "high": "高",
    "very_high": "极高",
}

EVENT_IMPACT_ZH = {
    "Positive": "偏正面",
    "Neutral": "中性",
    "Risk": "风险",
    "Strategic": "战略",
}

EVENT_TYPE_ZH = {
    "earnings": "财报",
    "product": "产品",
    "AI infrastructure": "AI 基础设施",
    "capex": "资本开支",
    "M&A": "并购",
    "partnership": "合作",
    "chip": "芯片",
    "cloud": "云",
    "management": "管理层",
    "regulatory": "监管",
    "robotics": "机器人",
    "autonomy": "自动驾驶",
}

MARKET_ZH = {
    "cloud_infrastructure": "云基础设施",
    "dram": "DRAM",
    "hbm": "HBM",
    "ai_accelerator": "AI 加速器",
    "enterprise_ai_platform": "企业 AI 平台",
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

PAGE_TITLE = "AI 产业链"
