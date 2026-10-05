"""Normalized Event schema + UI label helpers (V5.4)."""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Sequence


IMPACT_LABEL_ZH = {
    "Positive": "正面",
    "Neutral": "中性",
    "Risk": "负面",
    "Strategic": "战略影响",
    "正面": "正面",
    "中性": "中性",
    "负面": "负面",
    "战略影响": "战略影响",
}

LAYER_UI_ZH = {
    "infrastructure": "基础设施",
    "cloud": "云 / 数据中心",
    "model_platform": "AI平台",
    "applications": "应用层",
}

INTERNAL_TERM_UI = {
    "applications": "应用层",
    "model_platform": "AI平台",
    "Strategic": "战略影响",
    "OPTIONALITY": "未来业务",
    "Optionality": "未来业务",
    "DIRECT": "直接变现",
    "INDIRECT": "间接受益",
    "EMERGING": "起步业务",
}

EVENT_TYPE_UI = {
    "earnings": "财报",
    "guidance": "业绩指引",
    "product": "产品",
    "capex": "资本开支",
    "partnership": "合作",
    "regulatory": "监管",
    "competition": "竞争",
    "management": "管理层",
    "M&A": "并购",
    "technology": "技术",
    "autonomy": "自动驾驶",
    "chip": "芯片",
    "cloud": "云业务",
    "AI infrastructure": "AI基础设施",
    "ai infrastructure": "AI基础设施",
}

AREA_UI = {
    "收入": "收入",
    "利润率": "利润率",
    "资本开支": "资本开支",
    "产品": "产品",
    "竞争": "竞争",
    "监管": "监管",
    "自动驾驶": "自动驾驶",
    "revenue": "收入",
    "margin": "利润率",
    "capex": "资本开支",
    "product": "产品",
    "competition": "竞争",
    "regulation": "监管",
}

_IMPORTANCE_RANK = {"重大": 0, "重要": 1, "一般": 2}


def parse_date(value: Any) -> Optional[date]:
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


def as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    text = str(value).strip()
    return [text] if text else []


def translate_ui_term(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text in INTERNAL_TERM_UI:
        return INTERNAL_TERM_UI[text]
    if text in LAYER_UI_ZH:
        return LAYER_UI_ZH[text]
    if text in IMPACT_LABEL_ZH:
        return IMPACT_LABEL_ZH[text]
    if text in EVENT_TYPE_UI:
        return EVENT_TYPE_UI[text]
    if text in AREA_UI:
        return AREA_UI[text]
    return text


def impact_to_importance(impact_label: Any) -> str:
    mapping = {
        "Strategic": "重大",
        "Risk": "重大",
        "Positive": "重要",
        "Neutral": "一般",
        "重大": "重大",
        "重要": "重要",
        "一般": "一般",
    }
    return mapping.get(str(impact_label or "").strip(), "一般")


def derive_impact_areas(ev: Dict[str, Any]) -> List[str]:
    existing = as_list(ev.get("impact_areas"))
    if existing:
        return [translate_ui_term(x) for x in existing]
    et = str(ev.get("event_type") or "").lower()
    blob = " ".join(
        [
            et,
            str(ev.get("headline") or ""),
            str(ev.get("what_happened") or ""),
            str(ev.get("summary") or ""),
            str(ev.get("why_it_matters") or ""),
            str(ev.get("financial_impact") or ""),
        ]
    ).lower()
    areas: List[str] = []
    if "regulat" in blob or "antitrust" in blob:
        areas.append("监管")
    if "capex" in et or "capex" in blob or "资本开支" in blob:
        areas.append("资本开支")
    if "margin" in blob or "利润率" in blob:
        areas.append("利润率")
    if "compet" in blob or "市场份额" in blob or "竞争" in blob:
        areas.append("竞争")
    if "autonomy" in et or "robotaxi" in blob or "自动驾驶" in blob:
        areas.append("自动驾驶")
    if et in {"product", "ai infrastructure"} or "roadmap" in blob or "产品" in blob:
        areas.append("产品")
    if "revenue" in blob or "收入" in blob or "growth" in blob or "demand" in blob:
        areas.append("收入")
    if not areas:
        areas.append(EVENT_TYPE_UI.get(ev.get("event_type") or "", "产品"))
    # de-dupe preserve order
    seen = set()
    out: List[str] = []
    for a in areas:
        lab = translate_ui_term(a)
        if lab and lab not in seen:
            seen.add(lab)
            out.append(lab)
    return out


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "").strip().lower())


def texts_too_similar(a: Any, b: Any, *, threshold: float = 0.85) -> bool:
    """True when why_it_matters ≈ summary / what_happened (low-quality content)."""
    sa, sb = _normalize_text(a), _normalize_text(b)
    if not sa or not sb:
        return False
    if sa == sb:
        return True
    if sa in sb or sb in sa:
        shorter, longer = (sa, sb) if len(sa) <= len(sb) else (sb, sa)
        if len(shorter) >= 12 and len(shorter) / max(len(longer), 1) >= threshold:
            return True
    # token Jaccard on character bigrams
    def bigrams(s: str) -> set:
        if len(s) < 2:
            return {s}
        return {s[i : i + 2] for i in range(len(s) - 1)}

    ba, bb = bigrams(sa), bigrams(sb)
    if not ba or not bb:
        return False
    j = len(ba & bb) / len(ba | bb)
    return j >= threshold


def is_material_importance(importance: Any) -> bool:
    return str(importance or "") in {"重大", "重要"}


def is_low_priority_headline(ev: Dict[str, Any]) -> bool:
    """Drop ordinary price-move / chatter style items from 头等大事."""
    blob = " ".join(
        [
            str(ev.get("headline") or ""),
            str(ev.get("what_happened") or ""),
            str(ev.get("event_type") or ""),
        ]
    ).lower()
    low_signals = (
        "股价涨跌",
        "盘中波动",
        "社交媒体",
        "分析师重申",
        "price target",
        "analyst reiterates",
        "stock moves",
    )
    return any(s in blob for s in low_signals)


def make_event_id(ev: Dict[str, Any]) -> str:
    if ev.get("event_id"):
        return str(ev["event_id"])
    raw = "|".join(
        [
            str(ev.get("ticker") or ev.get("company_id") or ""),
            str(ev.get("published_at") or ev.get("event_date") or ""),
            str(ev.get("headline") or ""),
            str(ev.get("source_url") or ""),
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def normalize_event(raw: Dict[str, Any], *, now: Optional[date] = None) -> Dict[str, Any]:
    """Unify provider / static rows into the V5.4 Event schema."""
    today = now or date.today()
    ed = parse_date(
        raw.get("event_time") or raw.get("event_date") or raw.get("published_at")
    )
    status = str(raw.get("event_status") or "").upper()
    if status not in {"PAST", "UPCOMING"}:
        status = "UPCOMING" if (ed and ed > today) else "PAST"

    what = (
        raw.get("what_happened")
        or raw.get("short_summary")
        or raw.get("summary")
        or ""
    )
    why = raw.get("why_it_matters") or raw.get("strategic_impact") or ""
    # Prefer explicit why; never silently copy what_happened
    if texts_too_similar(why, what):
        why = raw.get("financial_impact") or why
        if texts_too_similar(why, what):
            why = ""

    impact_summary = raw.get("impact_summary")
    if not isinstance(impact_summary, dict):
        impact_summary = {}
        # soft map from legacy sentiment
        label = IMPACT_LABEL_ZH.get(str(raw.get("impact_label") or ""), "")
        for key in ("收入", "利润率", "CapEx", "竞争格局", "长期估值"):
            if key in (raw.get("impact_summary") or {}):
                impact_summary[key] = raw["impact_summary"][key]
        if label and not impact_summary:
            # leave empty rather than invent; UI shows only present keys
            pass

    watch_next = as_list(raw.get("watch_next"))
    impact_areas = derive_impact_areas(raw)
    importance = raw.get("importance") or impact_to_importance(
        raw.get("impact_label") or raw.get("importance")
    )
    source_type = str(raw.get("source_type") or "unknown").strip() or "unknown"

    # Never store copyrighted full article bodies
    full_article = raw.get("full_article") or raw.get("article_body") or raw.get("full_text")
    if full_article:
        # drop — structured summary only
        pass

    detailed = raw.get("detailed_summary")
    if isinstance(detailed, str):
        detailed = [detailed]
    detailed = list(detailed or [])
    if not detailed and what:
        detailed = [str(what)]

    pub = str(raw.get("published_at") or (ed.isoformat() if ed else "") or "")[:10]
    event_date = ed.isoformat() if ed else pub

    return {
        "event_id": make_event_id(raw),
        "ticker": str(raw.get("ticker") or raw.get("company_id") or "").upper(),
        "headline": str(raw.get("headline") or "").strip(),
        "published_at": pub,
        "event_date": event_date,
        "event_time": event_date,
        "event_status": status,
        "event_type": raw.get("event_type") or "product",
        "importance": importance,
        "what_happened": str(what).strip(),
        "why_it_matters": str(why).strip(),
        "impact_summary": impact_summary if isinstance(impact_summary, dict) else {},
        "impact_areas": impact_areas,
        "impact_area": impact_areas[0] if impact_areas else "产品",
        "watch_next": watch_next,
        "source_name": str(raw.get("source_name") or raw.get("source") or "").strip(),
        "source_url": str(raw.get("source_url") or "").strip(),
        "source_type": source_type,
        # backward-compatible aliases used by older UI / tests
        "short_summary": str(what).strip(),
        "summary": str(what).strip(),
        "detailed_summary": detailed,
        "sentiment_or_impact": translate_ui_term(
            raw.get("impact_label") or raw.get("sentiment_or_impact") or ""
        ),
        "layer_impact": [
            translate_ui_term(x) for x in as_list(raw.get("layer_impact"))
        ],
        "content_quality_ok": bool(what)
        and bool(why)
        and not texts_too_similar(what, why)
        and bool(str(raw.get("source_url") or "").strip() or source_type == "demo_static"),
    }


def importance_sort_key(ev: Dict[str, Any]) -> tuple:
    """Primary: importance (重大 first). Secondary handled by stable time sort."""
    return (_IMPORTANCE_RANK.get(str(ev.get("importance") or "一般"), 9),)


def apply_per_ticker_limits(
    events: Sequence[Dict[str, Any]],
    *,
    per_ticker_limit: int,
) -> List[Dict[str, Any]]:
    """Keep up to N events per ticker after importance/time sort; drop filler."""
    if per_ticker_limit <= 0:
        return list(events)
    ranked = sorted(events, key=lambda e: str(e.get("event_time") or ""), reverse=True)
    ranked.sort(key=importance_sort_key)
    counts: Dict[str, int] = {}
    out: List[Dict[str, Any]] = []
    for ev in ranked:
        # Skip low-quality duplicates
        if not ev.get("content_quality_ok", True):
            continue
        if is_low_priority_headline(ev):
            continue
        if not is_material_importance(ev.get("importance")):
            continue
        t = str(ev.get("ticker") or "").upper()
        n = counts.get(t, 0)
        if n >= per_ticker_limit:
            continue
        counts[t] = n + 1
        out.append(ev)
    return out


PER_TICKER_LIMITS = {
    "过去24小时": 2,
    "24h": 2,
    "本周": 3,
    "week": 3,
    "本季度": 5,
    "quarter": 5,
    "即将发生": 3,
    "upcoming": 3,
}
