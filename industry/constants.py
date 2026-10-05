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
    "model_platform": "AI平台",
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
    "very_low": "低",
    "low": "低",
    "medium": "中",
    "high": "高",
    "very_high": "极高",
}

MONETIZATION_ZH = {
    "DIRECT": "直接变现",
    "INDIRECT": "间接受益",
    "EMERGING": "起步业务",
    "OPTIONALITY": "未来业务",
}

TREND_LABEL = {
    "improving": "↑ 改善",
    "stable": "→ 稳定",
    "weakening": "↓ 转弱",
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

# Short research notes (not investment advice) — Chinese UI
COMPANY_INSIGHTS = {
    "NVDA": {
        "catalyst": "Rubin 爬坡 / AI 集群需求",
        "risk": "云厂商自研芯片",
        "quarter_trend": "improving",
        "quarter_reason": "数据中心需求仍是利润引擎",
    },
    "AMZN": {
        "catalyst": "AWS 增长 / Trainium",
        "risk": "AI 资本开支 / 云竞争",
        "quarter_trend": "improving",
        "quarter_reason": "AWS 增长加速",
    },
    "MSFT": {
        "catalyst": "Azure AI / Copilot 渗透",
        "risk": "资本开支相对自由现金流节奏偏高",
        "quarter_trend": "improving",
        "quarter_reason": "智能云增长伴随高资本开支",
    },
    "GOOG": {
        "catalyst": "Gemini 分发 + 云 AI 订单",
        "risk": "搜索扰动 / 资本开支强度",
        "quarter_trend": "stable",
        "quarter_reason": "广告现金流支撑云与 AI 投入",
    },
    "GOOGL": {
        "catalyst": "Gemini 分发 + 云 AI 订单",
        "risk": "搜索扰动 / 资本开支强度",
        "quarter_trend": "stable",
        "quarter_reason": "广告现金流支撑云与 AI 投入",
    },
    "META": {
        "catalyst": "AI 广告效率 / Llama 生态",
        "risk": "Reality Labs 亏损 / 资本开支飙升",
        "quarter_trend": "improving",
        "quarter_reason": "广告仍是现金引擎",
    },
    "AAPL": {
        "catalyst": "Apple Intelligence / 服务附着",
        "risk": "iPhone 周期 / AI 变现滞后",
        "quarter_trend": "stable",
        "quarter_reason": "服务占比支撑；AI 仍偏间接",
    },
    "TSLA": {
        "catalyst": "Robotaxi / Optimus 叙事",
        "risk": "汽车需求 / 自动驾驶落地",
        "quarter_trend": "weakening",
        "quarter_reason": "汽车仍占主导；自动驾驶偏期权",
    },
    "MU": {
        "catalyst": "HBM / 云内存爬坡",
        "risk": "存储周期 / 价格波动",
        "quarter_trend": "improving",
        "quarter_reason": "HBM 与云内存占比上升",
    },
    "ORCL": {
        "catalyst": "OCI AI 产能订单",
        "risk": "极高资本开支 / 执行风险",
        "quarter_trend": "improving",
        "quarter_reason": "云订单叙事伴随资本开支爬坡",
    },
    "PLTR": {
        "catalyst": "美国商业 AIP 扩张",
        "risk": "估值 / 客户集中 / 竞争",
        "quarter_trend": "improving",
        "quarter_reason": "美国商业增长加速",
    },
    "AVGO": {
        "catalyst": "定制 XPU / AI 网络",
        "risk": "客户集中 / 周期",
        "quarter_trend": "improving",
        "quarter_reason": "AI 半导体需求评述偏强",
    },
    "ANET": {
        "catalyst": "AI 集群网络需求",
        "risk": "云资本开支暂停 / 竞争",
        "quarter_trend": "improving",
        "quarter_reason": "产品增长与 AI 集群绑定",
    },
    "CRM": {
        "catalyst": "Agentforce 变现",
        "risk": "AI 附着慢于预期",
        "quarter_trend": "stable",
        "quarter_reason": "核心 CRM 仍是利润引擎",
    },
    "NOW": {
        "catalyst": "Now Assist / 工作流智能体",
        "risk": "企业 IT 支出周期",
        "quarter_trend": "stable",
        "quarter_reason": "订阅平台仍是核心",
    },
    "SNOW": {
        "catalyst": "Cortex / AI 数据云",
        "risk": "用量波动 / 竞争",
        "quarter_trend": "stable",
        "quarter_reason": "数据云用量是主业",
    },
    "ADBE": {
        "catalyst": "Firefly / GenStudio",
        "risk": "创意生成式 AI 竞争",
        "quarter_trend": "stable",
        "quarter_reason": "创意订阅仍是核心",
    },
    "CRWD": {
        "catalyst": "Charlotte AI / AI SOC",
        "risk": "安全竞争 / 事故风险",
        "quarter_trend": "stable",
        "quarter_reason": "安全云订阅占主导",
    },
}
