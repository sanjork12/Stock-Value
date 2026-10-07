"""Latest officially reported company quarter helpers (V5.3)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional, Sequence
import json
from pathlib import Path
from zoneinfo import ZoneInfo

SUPPORTED_TICKERS = 'AAPL MSFT GOOG AMZN NVDA META TSLA MU AVGO ORCL PLTR JPM NFLX UBER BABA'.split()


def load_company_quarter_snapshots():
    return json.loads((Path(__file__).parent.parent / 'data/industry/company_quarter_snapshots.json').read_text(encoding='utf-8'))


def get_latest_reported_quarter(ticker, as_of_date=None):
    """Select an actually published quarter, never a fiscal label or estimate."""
    return get_latest_company_quarter(ticker, as_of=_parse_date(as_of_date))

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
    rd = _parse_date(row.get('report_date'))
    if pe and (not rd or pe <= rd):
        return pe
    label = str(row.get("fiscal_period") or row.get("latest_reported_period") or "").upper()
    # Only a calendar-year label can establish a calendar quarter end.
    import re

    if 'FY' in label:
        return None  # Fiscal calendars do not coincide with calendar quarters.
    m = re.search(r"(CY)?\s*(\d{4})\s*Q([1-4])", label)
    if not m:
        return None
    year = int(m.group(2))
    q = int(m.group(3))
    ends = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
    month, day = ends[q]
    inferred = date(year, month, day)
    return inferred if not rd or inferred <= rd else None


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

    today = as_of or datetime.now(ZoneInfo('Europe/London')).date()
    cid = str(ticker or "").strip().upper()
    if not cid:
        return None
    company = resolve_company(cid)
    keys = set(_aliases(company)) if company else {cid}
    keys.add(cid)
    if cid in {'GOOG', 'GOOGL'}:
        keys.update({'GOOG', 'GOOGL'})

    source_rows: List[Dict[str, Any]]
    if rows is not None:
        source_rows = [dict(r) for r in rows]
    else:
        source_rows = [
            dict(e)
            for e in [*load_company_quarter_snapshots(), *load_earnings()]
            if str(e.get("company_id") or "").upper() in keys
            or str(e.get("ticker") or "").upper() in keys
        ]

    candidates: List[tuple] = []
    for e in source_rows:
        if str(e.get('source_type') or '').lower() == 'finnhub':
            continue  # TTM basic metrics are reference data, not quarterly snapshots.
        identity = str(e.get('ticker') or e.get('company_id') or '').upper()
        if identity and identity not in keys:
            continue
        rd = _parse_date(e.get("report_date") or e.get("latest_report_date"))
        if rd is None:
            continue
        if rd > today:
            continue  # unpublished / future — never select
        pe = infer_period_end(e)
        priority = 1 if e.get('snapshot_collection') == 'company_quarter_snapshots' else 0
        candidates.append((rd, priority, pe or rd, e))

    if not candidates:
        return None

    candidates.sort(key=lambda t: t[:3], reverse=True)
    report_date, _, period_end, best = candidates[0]
    out = dict(best)
    period_label = (
        out.get("latest_reported_period")
        or out.get("fiscal_period")
        or ""
    )
    out["latest_reported_period"] = period_label
    out["latest_report_date"] = report_date.isoformat()
    if infer_period_end(best):
        out["period_end"] = period_end.isoformat()
    else:
        out['period_end'] = None
    age = (today - report_date).days
    out["data_age_days"] = age
    # Prefer explicit STALE flag; otherwise age-based guard.
    known_newer = any(str(e.get('ticker')) in keys and report_date < (_parse_date(e.get('report_date')) or date.min) <= today for e in load_company_quarter_snapshots())
    if known_newer or str(out.get("data_status") or "").upper() == "STALE_DATA" or age > STALE_EARNINGS_DAYS:
        out["data_status"] = "STALE_DATA"
    else:
        out["data_status"] = str(out.get("data_status") or "CURRENT")
    return out


def audit_earnings_freshness(*, as_of: Optional[date] = None) -> List[Dict[str, Any]]:
    """Compare historical storage to maintained, officially verified releases."""
    from industry.loader import load_earnings
    today = as_of or datetime.now(ZoneInfo('Europe/London')).date()
    historical = load_earnings()
    report = []
    for ticker in SUPPORTED_TICKERS:
        old = get_latest_company_quarter(ticker, as_of=today, rows=historical)
        latest = get_latest_reported_quarter(ticker, today)
        old_date = (old or {}).get('latest_report_date')
        new_date = (latest or {}).get('latest_report_date')
        report.append(dict(ticker=ticker,
            current_stored_latest_quarter=(old or {}).get('fiscal_period'),
            actual_latest_officially_reported_quarter=(latest or {}).get('fiscal_period'),
            historical_stale=not old_date or bool(new_date and old_date < new_date),
            latest_reported_period=(latest or {}).get('fiscal_period'),
            latest_report_date=new_date, data_age_days=(latest or {}).get('data_age_days'),
            data_status=(latest or {}).get('data_status'),
            source_url=(latest or {}).get('source_url'), as_of=today.isoformat()))
    return report
