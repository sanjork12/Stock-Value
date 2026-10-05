"""Latest officially reported company quarter helpers (V5.3)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional, Sequence

# Beyond ~one full quarter + buffer → warn UI that data may be stale.
STALE_EARNINGS_DAYS = 150


def _parse_date(value: Any) -> Optional[date]:
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


def infer_period_end(row: Dict[str, Any]) -> Optional[date]:
    """Prefer explicit period_end; else derive coarse CY quarter end from fiscal_period."""
    pe = _parse_date(row.get("period_end") or row.get("period_end_date"))
    if pe:
        return pe
    label = str(row.get("fiscal_period") or row.get("latest_reported_period") or "").upper()
    # CY2025 Q2 / FY2025 Q2 → calendar quarter end when possible
    import re

    m = re.search(r"(CY|FY)?\s*(\d{4})\s*Q([1-4])", label)
    if not m:
        return None
    year = int(m.group(2))
    q = int(m.group(3))
    ends = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
    month, day = ends[q]
    return date(year, month, day)


def get_latest_company_quarter(
    ticker: str,
    *,
    as_of: Optional[date] = None,
    rows: Optional[Sequence[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Return the newest *officially reported* quarter for a ticker.

    Rules:
    - report_date must exist and be <= as_of (no future / unpublished quarters)
    - choose max(report_date); tie-break by period_end
    - attach latest_reported_period, latest_report_date, data_age_days, data_status
    """
    from industry.loader import load_earnings, resolve_company, _aliases

    today = as_of or date.today()
    cid = str(ticker or "").strip().upper()
    if not cid:
        return None
    company = resolve_company(cid)
    keys = set(_aliases(company)) if company else {cid}

    source_rows: List[Dict[str, Any]]
    if rows is not None:
        source_rows = [dict(r) for r in rows]
    else:
        source_rows = [
            dict(e)
            for e in load_earnings()
            if str(e.get("company_id") or "").upper() in keys
            or str(e.get("ticker") or "").upper() in keys
        ]

    candidates: List[tuple] = []
    for e in source_rows:
        rd = _parse_date(e.get("report_date") or e.get("latest_report_date") or e.get("source_date"))
        if rd is None:
            continue
        if rd > today:
            continue  # unpublished / future — never select
        pe = infer_period_end(e)
        candidates.append((rd, pe or rd, e))

    if not candidates:
        return None

    candidates.sort(key=lambda t: (t[0], t[1]), reverse=True)
    report_date, period_end, best = candidates[0]
    out = dict(best)
    period_label = (
        out.get("latest_reported_period")
        or out.get("fiscal_period")
        or ""
    )
    out["latest_reported_period"] = period_label
    out["latest_report_date"] = report_date.isoformat()
    if period_end and not out.get("period_end"):
        out["period_end"] = period_end.isoformat()
    age = (today - report_date).days
    out["data_age_days"] = age
    # Prefer explicit STALE flag; otherwise age-based guard.
    if str(out.get("data_status") or "").upper() == "STALE_DATA" or age > STALE_EARNINGS_DAYS:
        out["data_status"] = "STALE_DATA"
    else:
        out["data_status"] = str(out.get("data_status") or "CURRENT")
    return out


def audit_earnings_freshness(*, as_of: Optional[date] = None) -> List[Dict[str, Any]]:
    """Report per-ticker latest quarter freshness (no invented numbers)."""
    from industry.loader import load_earnings

    today = as_of or date.today()
    by_ticker: Dict[str, List[Dict[str, Any]]] = {}
    for row in load_earnings():
        t = str(row.get("ticker") or row.get("company_id") or "").upper()
        if not t:
            continue
        by_ticker.setdefault(t, []).append(dict(row))

    report: List[Dict[str, Any]] = []
    for t, rows in sorted(by_ticker.items()):
        latest = get_latest_company_quarter(t, as_of=today, rows=rows)
        report.append(
            {
                "ticker": t,
                "latest_reported_period": (latest or {}).get("latest_reported_period"),
                "latest_report_date": (latest or {}).get("latest_report_date"),
                "data_age_days": (latest or {}).get("data_age_days"),
                "data_status": (latest or {}).get("data_status"),
                "available_periods": [r.get("fiscal_period") for r in rows],
            }
        )
    return report
