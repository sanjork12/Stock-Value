"""Load and query static industry datasets under data/industry/."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from industry.constants import (
    LAYER_MAP_ORDER,
    LAYER_SHORT,
    MAG7,
    PRIVATE_REFERENCE,
    REQUIRED_PUBLIC_UNIVERSE,
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
