"""Load and query static industry datasets under data/industry/."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from industry.constants import (
    CLOUD_TICKERS,
    COMPANY_INSIGHTS,
    COMPUTE_TICKERS,
    LAYER_MAP_ORDER,
    LAYER_SHORT,
    LAYER_SHORT_ZH,
    MAG7,
    MEMORY_TICKERS,
    REQUIRED_PUBLIC_UNIVERSE,
    TREND_LABEL,
)
from industry.models import has_source, require_keys, segment_pct_sum

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "industry"


def _read_json(name: str) -> Any:
    path = DATA_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Industry dataset missing: {path}")
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def load_meta() -> Dict[str, Any]:
    return dict(_read_json("meta.json"))


@lru_cache(maxsize=1)
def load_companies() -> List[Dict[str, Any]]:
    rows = _read_json("companies.json")
    if not isinstance(rows, list):
        raise ValueError("companies.json must be a list")
    return [dict(r) for r in rows]


@lru_cache(maxsize=1)
def load_earnings() -> List[Dict[str, Any]]:
    rows = _read_json("earnings.json")
    if not isinstance(rows, list):
        raise ValueError("earnings.json must be a list")
    return [dict(r) for r in rows]


@lru_cache(maxsize=1)
def load_market_share() -> List[Dict[str, Any]]:
    rows = _read_json("market_share.json")
    if not isinstance(rows, list):
        raise ValueError("market_share.json must be a list")
    return [dict(r) for r in rows]


@lru_cache(maxsize=1)
def load_market_snapshot() -> Dict[str, Any]:
    raw = _read_json("market_snapshot.json")
    if not isinstance(raw, dict):
        raise ValueError("market_snapshot.json must be an object")
    return dict(raw)


@lru_cache(maxsize=1)
def load_events() -> List[Dict[str, Any]]:
    rows = _read_json("events.json")
    if not isinstance(rows, list):
        raise ValueError("events.json must be a list")
    return [dict(r) for r in rows]


@lru_cache(maxsize=1)
def load_accelerator_ecosystem() -> List[Dict[str, Any]]:
    rows = _read_json("accelerator_ecosystem.json")
    if not isinstance(rows, list):
        raise ValueError("accelerator_ecosystem.json must be a list")
    return [dict(r) for r in rows]


def clear_industry_cache() -> None:
    load_meta.cache_clear()
    load_companies.cache_clear()
    load_earnings.cache_clear()
    load_market_share.cache_clear()
    load_market_snapshot.cache_clear()
    load_events.cache_clear()
    load_accelerator_ecosystem.cache_clear()


def _aliases(company: Dict[str, Any]) -> List[str]:
    keys = [str(company.get("company_id") or "").upper()]
    t = company.get("ticker")
    if t:
        keys.append(str(t).upper())
    for a in company.get("ticker_aliases") or []:
        keys.append(str(a).upper())
    return [k for k in keys if k]


def resolve_company(query: str) -> Optional[Dict[str, Any]]:
    q = str(query or "").strip().upper()
    if not q:
        return None
    # GOOG / GOOGL → Alphabet profile
    if q in {"GOOG", "GOOGL"}:
        q = "GOOG"
    for row in load_companies():
        if q in _aliases(row):
            return dict(row)
        if str(row.get("company_name") or "").upper() == q:
            return dict(row)
    return None


def valuation_ticker_for(company_or_ticker: str) -> Optional[str]:
    """Ticker used to open Stock Analysis. Private / non-valued refs return None."""
    c = resolve_company(company_or_ticker)
    if not c:
        raw = str(company_or_ticker or "").strip().upper()
        return raw or None
    if c.get("public_private") == "private":
        return None
    if c.get("include_in_valuation") is False:
        return None
    vt = c.get("valuation_ticker") or c.get("ticker")
    return str(vt).upper() if vt else None


def mag7_companies() -> List[Dict[str, Any]]:
    out = []
    for tid in MAG7:
        c = resolve_company(tid)
        if c:
            out.append(c)
    return out


def companies_by_primary_layer(layer: str) -> List[Dict[str, Any]]:
    return [c for c in load_companies() if c.get("primary_layer") == layer]


def companies_touching_layer(layer: str) -> List[Dict[str, Any]]:
    rows = []
    for c in load_companies():
        presence = (c.get("layer_presence") or {}).get(layer)
        if presence and int(presence.get("stars") or 0) > 0:
            rows.append(c)
            continue
        layers = [c.get("primary_layer")] + list(c.get("secondary_layers") or [])
        if layer in layers:
            rows.append(c)
    return rows


def latest_earnings(company_id: str) -> Optional[Dict[str, Any]]:
    cid = str(company_id or "").upper()
    c = resolve_company(cid)
    keys = set(_aliases(c)) if c else {cid}
    matches = [
        e
        for e in load_earnings()
        if str(e.get("company_id") or "").upper() in keys
        or str(e.get("ticker") or "").upper() in keys
    ]
    if not matches:
        return None
    matches.sort(key=lambda r: str(r.get("report_date") or r.get("fiscal_period") or ""), reverse=True)
    return dict(matches[0])


def events_for(
    company_id: str,
    *,
    limit: int = 5,
    range_key: str = "current_quarter",
) -> List[Dict[str, Any]]:
    from datetime import date, timedelta

    c = resolve_company(company_id)
    keys = set(_aliases(c)) if c else {str(company_id).upper()}
    today = date.today()
    if range_key == "30D":
        start = today - timedelta(days=30)
    elif range_key == "90D":
        start = today - timedelta(days=90)
    elif range_key == "YTD":
        start = date(today.year, 1, 1)
    else:
        # Current quarter to date
        q = (today.month - 1) // 3
        start = date(today.year, q * 3 + 1, 1)

    rows = []
    for ev in load_events():
        ek = str(ev.get("company_id") or ev.get("ticker") or "").upper()
        if ek not in keys and str(ev.get("ticker") or "").upper() not in keys:
            continue
        ed = str(ev.get("event_date") or "")[:10]
        try:
            d = date.fromisoformat(ed)
        except ValueError:
            continue
        if d < start or d > today:
            continue
        rows.append(dict(ev))
    rows.sort(key=lambda r: str(r.get("event_date") or ""), reverse=True)
    return rows[:limit]


def market_share_rows(market: str) -> List[Dict[str, Any]]:
    m = str(market or "").strip()
    rows = [dict(r) for r in load_market_share() if r.get("market") == m]
    rows.sort(key=lambda r: (r.get("rank") is None, r.get("rank") or 999))
    return rows


def market_snapshot_block(key: str) -> Dict[str, Any]:
    """Return one market block from market_snapshot.json (cloud / dram / hbm)."""
    snap = load_market_snapshot()
    block = snap.get(str(key or "").strip().lower())
    if not isinstance(block, dict):
        return {}
    return dict(block)


def validate_market_snapshot(snap: Optional[Dict[str, Any]] = None) -> List[str]:
    """Validate latest-quarter market snapshot. Empty list means OK."""
    data = snap if snap is not None else load_market_snapshot()
    errors: List[str] = []
    if not isinstance(data, dict):
        return ["market_snapshot must be an object"]

    def _fnum(v: Any) -> Optional[float]:
        try:
            if v is None:
                return None
            return float(v)
        except (TypeError, ValueError):
            return None

    for key in ("cloud", "dram"):
        block = data.get(key)
        if not isinstance(block, dict):
            errors.append(f"{key}: missing block")
            continue
        if not str(block.get("period") or "").strip():
            errors.append(f"{key}: period is required")
        if not str(block.get("previous_period") or "").strip():
            errors.append(f"{key}: previous_period is required")
        if not str(block.get("source") or "").strip():
            errors.append(f"{key}: source is required")
        companies = block.get("companies")
        if not isinstance(companies, list) or not companies:
            errors.append(f"{key}: companies must be a non-empty list")
            continue
        total = 0.0
        for i, c in enumerate(companies):
            ctx = f"{key}.companies[{i}]"
            if not isinstance(c, dict):
                errors.append(f"{ctx}: must be an object")
                continue
            if not str(c.get("name") or "").strip():
                errors.append(f"{ctx}: name is required")
            share = _fnum(c.get("share"))
            prev = _fnum(c.get("previous_share"))
            chg = _fnum(c.get("change_pp"))
            if share is None or not (0.0 <= share <= 100.0):
                errors.append(f"{ctx}: share must be in 0–100")
            else:
                total += share
            if prev is None or not (0.0 <= prev <= 100.0):
                errors.append(f"{ctx}: previous_share must be in 0–100")
            if share is not None and prev is not None and chg is not None:
                if abs((share - prev) - chg) > 0.051:
                    errors.append(f"{ctx}: change_pp must equal share - previous_share")
            rank = c.get("rank")
            if rank is not None:
                try:
                    ri = int(rank)
                    if ri < 1:
                        errors.append(f"{ctx}: rank must be positive or null")
                except (TypeError, ValueError):
                    errors.append(f"{ctx}: rank must be positive integer or null")
        if abs(total - 100.0) > 1.5:
            errors.append(f"{key}: company share sum {total:.1f} not near 100%")

    hbm = data.get("hbm")
    if not isinstance(hbm, dict):
        errors.append("hbm: missing block")
    else:
        if not str(hbm.get("period") or "").strip():
            errors.append("hbm: period is required")
        if not str(hbm.get("source") or "").strip():
            errors.append("hbm: source is required")
        roles = hbm.get("roles")
        if not isinstance(roles, list) or not roles:
            errors.append("hbm: roles must be a non-empty list")
        else:
            for i, r in enumerate(roles):
                if not isinstance(r, dict) or not r.get("name") or not r.get("role"):
                    errors.append(f"hbm.roles[{i}]: name and role required")
                elif r.get("share") is not None:
                    errors.append(f"hbm.roles[{i}]: must not invent share percentage")
    return errors


def validate_datasets() -> List[str]:
    """Return list of validation errors (empty if OK)."""
    errors: List[str] = []
    companies = load_companies()
    by_id = {str(c.get("company_id") or "").upper(): c for c in companies}

    for tid in REQUIRED_PUBLIC_UNIVERSE:
        if tid == "GOOG":
            if "GOOG" not in by_id and "GOOGL" not in by_id:
                errors.append("Missing Mag7/Universe profile for GOOG/Alphabet")
            continue
        if tid not in by_id and not resolve_company(tid):
            errors.append(f"Missing IndustryCompanyProfile for {tid}")

    for mid in MAG7:
        c = resolve_company(mid)
        if not c:
            errors.append(f"Mag7 missing profile: {mid}")
            continue
        for field in (
            "company_id",
            "company_name",
            "public_private",
            "primary_layer",
            "current_profit_layers",
            "future_expansion_layers",
            "main_revenue_engine",
            "ai_exposure_type",
            "ai_monetization_status",
        ):
            if field not in c:
                errors.append(f"{mid}: missing {field}")
        # Separation of current vs future
        cur = set(c.get("current_profit_layers") or [])
        fut = set(c.get("future_expansion_layers") or [])
        if not cur:
            errors.append(f"{mid}: current_profit_layers empty")

    for e in load_earnings():
        ctx = f"earnings:{e.get('ticker')}:{e.get('fiscal_period')}"
        try:
            require_keys(
                e,
                ["ticker", "fiscal_period", "report_date", "segments", "source_urls", "data_quality"],
                ctx=ctx,
            )
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not has_source(e):
            errors.append(f"{ctx}: missing source metadata")
        segs = e.get("segments") or []
        if segs:
            s = segment_pct_sum(segs)
            if abs(s - 100.0) > 2.5:
                errors.append(f"{ctx}: segment % sum={s:.1f} (expected ~100)")

    for row in load_market_share():
        ctx = f"share:{row.get('market')}:{row.get('company')}"
        if not has_source(row):
            errors.append(f"{ctx}: missing source")
        share = row.get("share_pct")
        if share is not None:
            try:
                v = float(share)
            except (TypeError, ValueError):
                errors.append(f"{ctx}: share_pct not numeric")
                continue
            if v < 0 or v > 100:
                errors.append(f"{ctx}: share_pct out of range {v}")
            if not has_source(row):
                errors.append(f"{ctx}: percentage without source")

    for market in ("cloud_infrastructure", "dram"):
        rows = market_share_rows(market)
        if not rows:
            errors.append(f"No market share rows for {market}")
        else:
            if not any(r.get("period") for r in rows):
                errors.append(f"{market}: missing period")
            if not any(has_source(r) for r in rows):
                errors.append(f"{market}: missing sources")

    for ev in load_events():
        ctx = f"event:{ev.get('ticker')}:{ev.get('event_date')}"
        if not has_source(ev) and not ev.get("source_url"):
            errors.append(f"{ctx}: missing source")
        if ev.get("impact_label") and ev.get("impact_label") not in {
            "Positive",
            "Neutral",
            "Risk",
            "Strategic",
        }:
            errors.append(f"{ctx}: bad impact_label")

    return errors


def build_industry_map_export() -> Dict[str, Any]:
    """PPT/image-ready structured export (V5.5 stub payload)."""
    meta = load_meta()
    companies = load_companies()
    layers = []
    for layer in LAYER_MAP_ORDER:
        layers.append(
            {
                "id": layer,
                "label": LAYER_SHORT.get(layer, layer),
                "companies": [
                    {
                        "company_id": c.get("company_id"),
                        "ticker": c.get("ticker"),
                        "name": c.get("company_name"),
                        "presence": (c.get("layer_presence") or {}).get(layer),
                        "profit_tag": ((c.get("layer_presence") or {}).get(layer) or {}).get("profit_tag"),
                    }
                    for c in companies_touching_layer(layer)
                ],
            }
        )
    return {
        "schema_version": meta.get("schema_version", "v5.1"),
        "data_through": meta.get("data_through"),
        "last_refreshed_at": meta.get("last_refreshed_at"),
        "layers": layers,
        "companies": companies,
        "positions": {
            c.get("company_id"): {
                "primary_layer": c.get("primary_layer"),
                "secondary_layers": c.get("secondary_layers"),
                "layer_presence": c.get("layer_presence"),
            }
            for c in companies
        },
        "current_profit": {c.get("company_id"): c.get("current_profit_layers") for c in companies},
        "future_expansion": {c.get("company_id"): c.get("future_expansion_layers") for c in companies},
        "market_share": load_market_share(),
        "revenue_mix": [
            {
                "ticker": e.get("ticker"),
                "fiscal_period": e.get("fiscal_period"),
                "segments": e.get("segments"),
            }
            for e in load_earnings()
        ],
        "events": load_events(),
        "accelerator_ecosystem": load_accelerator_ecosystem(),
    }


def stars_to_text(stars: int) -> str:
    n = max(0, min(5, int(stars or 0)))
    return "★" * n + "☆" * (5 - n)


def normalize_watchlist_tickers(raw: Any) -> List[str]:
    """Accept list[str] or list[dict with ticker]; return unique upper tickers."""
    out: List[str] = []
    seen = set()
    for item in raw or []:
        if isinstance(item, dict):
            t = str(item.get("ticker") or "").strip().upper()
        else:
            t = str(item or "").strip().upper()
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def display_ticker_for_company(company: Dict[str, Any]) -> str:
    cid = str(company.get("company_id") or "")
    if cid == "SAMSUNG":
        return "Samsung"
    if cid == "SKHYNIX":
        return "SK hynix"
    if cid == "OPENAI":
        return "OpenAI"
    if cid == "ANTHROPIC":
        return "Anthropic"
    if cid == "GOOG":
        return "GOOG"
    t = company.get("valuation_ticker") or company.get("ticker") or cid
    return str(t)


def layer_map_labels(layer: str) -> List[str]:
    """Compact ticker/name labels for one industry layer (no stars)."""
    labels = []
    seen = set()
    for c in companies_touching_layer(layer):
        label = display_ticker_for_company(c)
        key = label.upper()
        if key in seen:
            continue
        seen.add(key)
        labels.append(label)
    return labels


def watchlist_keys(watchlist_tickers: List[str]) -> set[str]:
    keys = {str(t).upper() for t in watchlist_tickers or []}
    # Alphabet aliases
    if "GOOG" in keys or "GOOGL" in keys:
        keys.update({"GOOG", "GOOGL"})
    return keys


def company_in_watchlist(company: Dict[str, Any], watch_keys: set[str]) -> bool:
    for a in _aliases(company):
        if a in watch_keys:
            return True
    return False


def ticker_in_watchlist(ticker: str, watch_keys: set[str]) -> bool:
    t = str(ticker or "").upper()
    if t in watch_keys:
        return True
    c = resolve_company(t)
    return bool(c and company_in_watchlist(c, watch_keys))


def insight_for(ticker: str) -> Dict[str, str]:
    t = str(ticker or "").upper()
    hit = COMPANY_INSIGHTS.get(t) or COMPANY_INSIGHTS.get(
        str((resolve_company(t) or {}).get("company_id") or "").upper()
    )
    if not hit:
        return {
            "catalyst": "—",
            "risk": "—",
            "quarter_trend": "stable",
            "quarter_reason": "暂无季度变化备注",
        }
    return dict(hit)


def trend_label(trend_key: str) -> str:
    return TREND_LABEL.get(str(trend_key or "").lower(), "→ 稳定")


def layer_label_for_profile(company: Optional[Dict[str, Any]]) -> str:
    if not company:
        return "其他 / 未分类"
    primary = company.get("primary_layer")
    secondary = list(company.get("secondary_layers") or [])
    parts = [LAYER_SHORT_ZH.get(primary, primary)] if primary else []
    for s in secondary:
        lab = LAYER_SHORT_ZH.get(s, s)
        if lab and lab not in parts:
            parts.append(lab)
    return " + ".join(str(p) for p in parts if p) or "其他 / 未分类"


def show_cloud_module(watchlist_tickers: List[str]) -> bool:
    keys = watchlist_keys(watchlist_tickers)
    return bool(keys & CLOUD_TICKERS)


def show_memory_module(watchlist_tickers: List[str]) -> bool:
    keys = watchlist_keys(watchlist_tickers)
    return bool(keys & MEMORY_TICKERS) or "MU" in keys


def show_compute_module(watchlist_tickers: List[str]) -> bool:
    keys = watchlist_keys(watchlist_tickers)
    return bool(keys & COMPUTE_TICKERS)


# impact_label → 头等大事 Importance (V5.2 MVP; static dataset reuse)
_IMPACT_TO_IMPORTANCE = {
    "Risk": "重大",
    "Strategic": "重大",
    "Positive": "重要",
    "Neutral": "一般",
}


def impact_to_importance(impact_label: Any) -> str:
    return _IMPACT_TO_IMPORTANCE.get(str(impact_label or "").strip(), "一般")


def derive_impact_area(ev: Dict[str, Any]) -> str:
    """
    Map existing event fields → 影响领域（仅 UI 展示，不改源 JSON）。
    之一：收入 / 利润率 / 资本开支 / 竞争 / 监管 / 产品
    """
    et = str(ev.get("event_type") or "").lower()
    blob = " ".join(
        [
            et,
            str(ev.get("headline") or ""),
            str(ev.get("summary") or ""),
            str(ev.get("strategic_impact") or ""),
            str(ev.get("financial_impact") or ""),
        ]
    ).lower()
    layers = [str(x).lower() for x in (ev.get("layer_impact") or [])]

    if "regulat" in blob or "antitrust" in blob or "sec " in blob:
        return "监管"
    if "capex" in et or "capex" in blob or "capacity" in blob:
        return "资本开支"
    if "margin" in blob or "operating margin" in blob:
        return "利润率"
    if "compet" in blob or "rival" in blob or "share" in blob:
        return "竞争"
    if et in {"product", "ai infrastructure"} or "roadmap" in blob or "feature" in blob:
        if "infrastructure" in et or "capex" in blob or "capacity" in blob:
            return "资本开支"
        return "产品"
    if "revenue" in blob or "growth" in blob or "demand" in blob or "monetiz" in blob:
        return "收入"
    if "infrastructure" in layers or "cloud" in layers:
        return "资本开支"
    if "applications" in layers:
        return "收入"
    return "产品"


def get_watchlist_events(
    tickers: Sequence[Any],
    start_date: Optional[str] = None,
    importance: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Watchlist-scoped events for 头等大事 / single-stock.

    Returns dicts with:
      ticker, event_date, headline, summary, importance,
      why_it_matters, impact_area, source, source_url
    """
    from datetime import date

    tick_list = normalize_watchlist_tickers(tickers)
    if not tick_list:
        return []

    start = None
    if start_date:
        try:
            start = date.fromisoformat(str(start_date)[:10])
        except ValueError:
            start = None

    keys = watchlist_keys(tick_list)
    # Map each alias key back to a display ticker from the watchlist
    alias_to_display: Dict[str, str] = {}
    for t in tick_list:
        alias_to_display[t] = t
        c = resolve_company(t)
        if c:
            for a in _aliases(c):
                alias_to_display[a] = t

    out: List[Dict[str, Any]] = []
    for ev in load_events():
        ek = str(ev.get("company_id") or ev.get("ticker") or "").upper()
        tk = str(ev.get("ticker") or "").upper()
        match_key = ek if ek in keys else (tk if tk in keys else None)
        if not match_key:
            continue
        ed = str(ev.get("event_date") or "")[:10]
        try:
            d = date.fromisoformat(ed)
        except ValueError:
            continue
        if start is not None and d < start:
            continue
        imp = impact_to_importance(ev.get("impact_label"))
        if importance and imp != importance:
            continue
        display = alias_to_display.get(match_key) or alias_to_display.get(tk) or match_key
        out.append(
            {
                "ticker": display,
                "event_date": ed,
                "headline": ev.get("headline") or "",
                "summary": ev.get("summary") or ev.get("financial_impact") or "",
                "importance": imp,
                "why_it_matters": ev.get("strategic_impact")
                or ev.get("financial_impact")
                or ev.get("summary")
                or "",
                "impact_area": derive_impact_area(ev),
                "source": ev.get("source") or ev.get("source_name") or "",
                "source_url": ev.get("source_url") or "",
            }
        )
    out.sort(key=lambda r: str(r.get("event_date") or ""), reverse=True)
    return out
