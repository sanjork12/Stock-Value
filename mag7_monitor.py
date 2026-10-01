
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

APP_DIR = Path(__file__).resolve().parent
SNAPSHOT_FILE = APP_DIR / "valuation_snapshots.json"

MAG7 = {"AAPL","MSFT","GOOGL","AMZN","NVDA","META","TSLA"}
GENERIC_ASSUMPTION = {"pe_range":[18,24], "norm_growth":0.12, "peg_target":1.5, "growth_pe_cap":30, "dcf_growth":0.10}

# These are intentionally editable assumptions, not "truth".
# They are the valuation framework used by this program.
ASSUMPTIONS = {
    "AAPL": {"pe_range":[28,32], "norm_growth":0.09, "peg_target":1.8, "growth_pe_cap":32, "dcf_growth":0.08},
    "MSFT": {"pe_range":[27,32], "norm_growth":0.18, "peg_target":1.7, "growth_pe_cap":34, "dcf_growth":0.16},
    "GOOGL":{"pe_range":[22,26], "norm_growth":0.18, "peg_target":1.5, "growth_pe_cap":30, "dcf_growth":0.16},
    "AMZN": {"pe_range":[27,32], "norm_growth":0.20, "peg_target":1.5, "growth_pe_cap":34, "dcf_growth":0.18},
    "NVDA": {"pe_range":[25,32], "norm_growth":0.24, "peg_target":1.4, "growth_pe_cap":38, "dcf_growth":0.22},
    "META": {"pe_range":[22,27], "norm_growth":0.16, "peg_target":1.5, "growth_pe_cap":30, "dcf_growth":0.15},
    "TSLA": {"pe_range":[60,100],"norm_growth":0.25, "peg_target":2.0, "growth_pe_cap":120,"dcf_growth":0.18},
}

WEIGHTS = {"pe":0.35, "dcf":0.40, "growth":0.25}
DISCOUNT_RATE = 0.09
TERMINAL_GROWTH = 0.03
MODEL_OUTLIER_THRESHOLD = 0.60
MIN_MODELS_FOR_BLEND = 2
SHARES_MIN = 1e8
SHARES_MAX = 1e11
MARKET_CAP_MIN = 1e9
MARKET_CAP_MAX = 1e14
FCF_WEIGHTS_3Y = (0.50, 0.30, 0.20)

OCF_ALIASES = (
    "Operating Cash Flow",
    "Total Cash From Operating Activities",
    "Cash Flow From Continuing Operating Activities",
)
CAPEX_ALIASES = (
    "Capital Expenditure",
    "Capital Expenditures",
    "Purchase Of PPE",
)
FCF_ALIASES = ("Free Cash Flow",)


def fnum(x):
    try:
        if x is None:
            return None
        x = float(x)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def get_history(ticker: str, as_of: Optional[str]) -> pd.DataFrame:
    # Need enough history for 200d SMA + volume profile.
    if as_of:
        end_dt = pd.Timestamp(as_of) + pd.Timedelta(days=1)
    else:
        end_dt = pd.Timestamp.today(tz=None) + pd.Timedelta(days=1)
    start_dt = end_dt - pd.Timedelta(days=800)
    df = yf.download(
        ticker,
        start=start_dt.strftime("%Y-%m-%d"),
        end=end_dt.strftime("%Y-%m-%d"),
        auto_adjust=False,
        progress=False,
        actions=False,
        threads=False,
    )
    if df.empty:
        raise RuntimeError(f"No price data returned for {ticker}.")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    return df.dropna(subset=["Close"])


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for n in (30,50,200):
        out[f"SMA{n}"] = out["Close"].rolling(n).mean()
    return out


def volume_profile_zone(df: pd.DataFrame, lookback=252, bins=24):
    d = df.tail(lookback).copy()
    if len(d) < 30 or "Volume" not in d or d["Volume"].fillna(0).sum() <= 0:
        return None
    typical = (d["High"] + d["Low"] + d["Close"]) / 3
    lo, hi = float(typical.min()), float(typical.max())
    if hi <= lo:
        return None
    edges = np.linspace(lo, hi, bins+1)
    idx = np.clip(np.digitize(typical.to_numpy(), edges)-1, 0, bins-1)
    vols = np.zeros(bins)
    for i, v in zip(idx, d["Volume"].fillna(0).to_numpy()):
        vols[i] += float(v)
    top = int(np.argmax(vols))
    return {
        "low": float(edges[top]),
        "high": float(edges[top+1]),
        "mid": float((edges[top]+edges[top+1])/2),
    }


def metric_field(value, source=None, period=None, unit="USD", raw=None):
    return {
        "value": fnum(value),
        "raw": raw if raw is not None else value,
        "source": source,
        "period": period,
        "unit": unit,
    }


def normalize_capex(raw_capex):
    """Return CapEx as a positive cash outflow."""
    value = fnum(raw_capex)
    if value is None:
        return None
    return abs(value)


def model_result(
    name,
    *,
    valid=True,
    low=None,
    mid=None,
    high=None,
    confidence="medium",
    reason=None,
    inputs=None,
    warnings=None,
    outlier=False,
    extra=None,
):
    result = {
        "name": name,
        "valid": bool(valid) and not outlier,
        "outlier": bool(outlier),
        "low": fnum(low),
        "mid": fnum(mid),
        "high": fnum(high),
        "confidence": "invalid" if not valid or outlier else confidence,
        "reason": reason,
        "inputs": inputs or {},
        "warnings": list(warnings or []),
    }
    if extra:
        result.update(extra)
    if result["valid"] and not range_is_ordered(result["low"], result["mid"], result["high"]):
        result["valid"] = False
        result["confidence"] = "invalid"
        result["reason"] = result["reason"] or "unordered_or_nonpositive_range"
    return result


def range_is_ordered(low, mid, high) -> bool:
    low, mid, high = fnum(low), fnum(mid), fnum(high)
    if low is None or mid is None or high is None:
        return False
    if min(low, mid, high) <= 0:
        return False
    if not all(math.isfinite(v) for v in (low, mid, high)):
        return False
    return low <= mid <= high


def structural_valid(model) -> bool:
    if not model:
        return False
    if model.get("valid") is False or model.get("outlier"):
        return False
    return range_is_ordered(model.get("low"), model.get("mid"), model.get("high"))


def _cashflow_row(df: pd.DataFrame, aliases, col):
    if df is None or df.empty:
        return None
    lowered = {str(idx).strip().lower(): idx for idx in df.index}
    for alias in aliases:
        key = lowered.get(str(alias).strip().lower())
        if key is not None:
            try:
                return fnum(df.loc[key, col])
            except Exception:
                return None
    return None


def _period_label(col) -> str:
    try:
        ts = pd.Timestamp(col)
        return f"FY{ts.year}"
    except Exception:
        return str(col)


def _yearly_cashflows(cf: pd.DataFrame) -> list[dict]:
    rows = []
    if cf is None or cf.empty:
        return rows
    for col in list(cf.columns)[:5]:
        ocf = _cashflow_row(cf, OCF_ALIASES, col)
        capex_raw = _cashflow_row(cf, CAPEX_ALIASES, col)
        capex_outflow = normalize_capex(capex_raw)
        fcf_reported = _cashflow_row(cf, FCF_ALIASES, col)
        fcf_computed = None
        if ocf is not None and capex_outflow is not None:
            fcf_computed = ocf - capex_outflow
        fcf = fcf_reported if fcf_reported is not None else fcf_computed
        if ocf is None and capex_raw is None and fcf is None:
            continue
        rows.append({
            "period": _period_label(col),
            "column": str(col),
            "operating_cash_flow": ocf,
            "capital_expenditure_raw": capex_raw,
            "capital_expenditure": capex_outflow,
            "free_cash_flow_reported": fcf_reported,
            "free_cash_flow_computed": fcf_computed,
            "free_cash_flow": fcf,
            "source": "ticker.cashflow",
        })
        if len(rows) >= 3:
            break
    return rows


def _normalize_fcf(annual_rows: list[dict], ttm_fcf=None) -> dict:
    values = [row["free_cash_flow"] for row in annual_rows if fnum(row.get("free_cash_flow")) is not None]
    warnings = []
    if len(values) >= 3:
        median = float(np.median(values[:3]))
        weighted = sum(w * v for w, v in zip(FCF_WEIGHTS_3Y, values[:3]))
        latest = values[0]
        if latest is not None and median > 0 and latest < 0.5 * median:
            warnings.append("latest_fcf_well_below_history")
        # Median damps a single high-CapEx year without inventing a positive FCF.
        return {
            "value": median,
            "method": "median_3y_annual",
            "weighted_3y": weighted,
            "latest": latest,
            "source": "ticker.cashflow",
            "period": f"{annual_rows[2]['period']}-{annual_rows[0]['period']}",
            "warnings": warnings,
        }
    if len(values) == 2:
        weighted = 0.6 * values[0] + 0.4 * values[1]
        return {
            "value": weighted,
            "method": "weighted_2y_annual",
            "latest": values[0],
            "source": "ticker.cashflow",
            "period": f"{annual_rows[1]['period']}-{annual_rows[0]['period']}",
            "warnings": warnings,
        }
    if len(values) == 1:
        return {
            "value": values[0],
            "method": "latest_annual",
            "latest": values[0],
            "source": "ticker.cashflow",
            "period": annual_rows[0]["period"],
            "warnings": warnings + ["only_one_annual_fcf"],
        }
    if fnum(ttm_fcf) is not None:
        return {
            "value": fnum(ttm_fcf),
            "method": "yahoo_info_freeCashflow",
            "latest": fnum(ttm_fcf),
            "source": "ticker.info.freeCashflow",
            "period": "TTM",
            "warnings": warnings + ["fallback_ttm_info_freeCashflow"],
        }
    return {
        "value": None,
        "method": None,
        "source": None,
        "period": None,
        "warnings": warnings + ["missing_fcf"],
    }


def get_live_fundamentals(ticker: str):
    t = yf.Ticker(ticker)
    info = {}
    try:
        info = t.info or {}
    except Exception:
        info = {}

    current = fnum(info.get("currentPrice") or info.get("regularMarketPrice"))
    forward_eps = fnum(info.get("forwardEps"))
    trailing_eps = fnum(info.get("trailingEps"))
    shares = fnum(info.get("sharesOutstanding"))
    total_cash = fnum(info.get("totalCash"))
    total_debt = fnum(info.get("totalDebt"))
    market_cap = fnum(info.get("marketCap"))
    earnings_growth = fnum(info.get("earningsGrowth"))
    ttm_fcf = fnum(info.get("freeCashflow"))
    ttm_ocf = fnum(info.get("operatingCashflow"))
    book_value = fnum(info.get("bookValue"))
    roe = fnum(info.get("returnOnEquity"))
    ebitda = fnum(info.get("ebitda"))
    revenue = fnum(info.get("totalRevenue"))
    enterprise_value = fnum(info.get("enterpriseValue"))
    nta = fnum(info.get("netTangibleAssets"))
    tangible_bvps = nta / shares if nta and shares and shares > 0 else None
    dividend_rate = fnum(info.get("dividendRate"))
    beta = fnum(info.get("beta"))
    sector = info.get("sector")
    industry = info.get("industry")
    quote_type = info.get("quoteType")
    long_name = info.get("shortName") or info.get("longName")

    annual_rows = []
    try:
        annual_rows = _yearly_cashflows(t.cashflow)
    except Exception:
        annual_rows = []

    historical_eps = []
    try:
        inc = t.income_stmt
        if inc is not None and not inc.empty:
            for col in list(inc.columns)[:5]:
                net_income = _cashflow_row(inc, ("Net Income", "Net Income Common Stockholders"), col)
                share_count = _cashflow_row(inc, ("Diluted Average Shares", "Basic Average Shares"), col) or shares
                eps = None
                if net_income is not None and share_count:
                    eps = net_income / share_count
                if eps is None and net_income is None:
                    continue
                historical_eps.append({
                    "period": _period_label(col),
                    "net_income": net_income,
                    "shares": share_count,
                    "eps": fnum(eps),
                })
    except Exception:
        historical_eps = []

    latest_annual = annual_rows[0] if annual_rows else {}
    normalized = _normalize_fcf(annual_rows, ttm_fcf=ttm_fcf)
    cash = total_cash if total_cash is not None else 0.0
    debt = total_debt if total_debt is not None else 0.0
    if cash < 0:
        cash = 0.0
    if debt < 0:
        debt = 0.0

    return {
        "current_price": current,
        "forward_eps": forward_eps,
        "trailing_eps": trailing_eps,
        "shares": shares,
        "cash": cash,
        "debt": debt,
        "market_cap": market_cap,
        "earnings_growth": earnings_growth,
        "fcf": normalized.get("value"),
        "fcf_method": normalized.get("method"),
        "fcf_period": normalized.get("period"),
        "fcf_source": normalized.get("source"),
        "fcf_ttm_info": ttm_fcf,
        "operating_cash_flow": latest_annual.get("operating_cash_flow") or ttm_ocf,
        "capital_expenditure_raw": latest_annual.get("capital_expenditure_raw"),
        "capital_expenditure": latest_annual.get("capital_expenditure"),
        "annual_cashflows": annual_rows,
        "book_value_per_share": book_value,
        "tangible_book_value_per_share": tangible_bvps,
        "roe": roe,
        "ebitda": ebitda,
        "revenue": revenue,
        "enterprise_value": enterprise_value,
        "dividend_rate": dividend_rate,
        "beta": beta,
        "sector": sector,
        "industry": industry,
        "quote_type": quote_type,
        "long_name": long_name,
        "historical_eps": historical_eps,
        "normalized": {
            "forward_eps": metric_field(forward_eps, "ticker.info.forwardEps", unit="USD/share"),
            "trailing_eps": metric_field(trailing_eps, "ticker.info.trailingEps", unit="USD/share"),
            "operating_cash_flow": metric_field(
                latest_annual.get("operating_cash_flow") or ttm_ocf,
                "ticker.cashflow" if latest_annual else "ticker.info.operatingCashflow",
                latest_annual.get("period"),
            ),
            "capital_expenditure": metric_field(
                latest_annual.get("capital_expenditure"),
                "ticker.cashflow",
                latest_annual.get("period"),
                raw=latest_annual.get("capital_expenditure_raw"),
            ),
            "free_cash_flow": metric_field(
                normalized.get("value"),
                normalized.get("source"),
                normalized.get("period"),
            ),
            "total_cash": metric_field(cash, "ticker.info.totalCash"),
            "total_debt": metric_field(debt, "ticker.info.totalDebt"),
            "shares_outstanding": metric_field(shares, "ticker.info.sharesOutstanding", unit="shares"),
            "market_cap": metric_field(market_cap, "ticker.info.marketCap"),
            "earnings_growth": metric_field(earnings_growth, "ticker.info.earningsGrowth", unit="ratio"),
        },
        "warnings": list(normalized.get("warnings") or []),
        "data_source": "Yahoo Finance / yfinance",
    }


def get_assumption(ticker):
    return ASSUMPTIONS.get(ticker.upper(), GENERIC_ASSUMPTION.copy())


def pe_model(ticker, forward_eps):
    a = get_assumption(ticker)
    eps = fnum(forward_eps)
    if eps is None or eps <= 0 or not math.isfinite(eps):
        return model_result("P/E", valid=False, reason="missing_or_nonpositive_forward_eps", confidence="invalid")
    lo, hi = a["pe_range"]
    mid_pe = (lo + hi) / 2
    return model_result(
        "P/E",
        valid=True,
        low=eps * lo,
        mid=eps * mid_pe,
        high=eps * hi,
        confidence="high",
        inputs={"forward_eps": eps, "pe_low": lo, "pe_high": hi},
    )


def growth_model(ticker, forward_eps, live_growth=None):
    eps = fnum(forward_eps)
    if eps is None or eps <= 0 or not math.isfinite(eps):
        return model_result("Growth / PEG", valid=False, reason="missing_or_nonpositive_forward_eps", confidence="invalid")
    a = get_assumption(ticker)
    g = a["norm_growth"]
    warnings = []
    live = fnum(live_growth)
    if live is not None and 0 < live < 1:
        g = 0.5 * g + 0.5 * live
    elif live is not None:
        warnings.append("live_earnings_growth_ignored_as_unrealistic")
    growth_pct = g * 100
    fair_pe = growth_pct * a["peg_target"]
    fair_pe = max(12, min(fair_pe, a["growth_pe_cap"]))
    return model_result(
        "Growth / PEG",
        valid=True,
        low=eps * fair_pe * 0.88,
        mid=eps * fair_pe,
        high=eps * fair_pe * 1.12,
        confidence="medium",
        inputs={
            "forward_eps": eps,
            "growth_used": g,
            "peg_target": a["peg_target"],
            "fair_pe": fair_pe,
        },
        warnings=warnings,
        extra={"fair_pe": fair_pe, "growth_used": g},
    )


def _dcf_input_errors(fcf, shares, cash, debt, market_cap=None) -> list[str]:
    errors = []
    fcf, shares, cash, debt = fnum(fcf), fnum(shares), fnum(cash), fnum(debt)
    if fcf is None or not math.isfinite(fcf):
        errors.append("fcf_not_finite")
    elif fcf <= 0:
        errors.append("negative_or_unreliable_normalized_fcf")
    if shares is None or shares <= 0 or not math.isfinite(shares):
        errors.append("invalid_shares_outstanding")
    elif not (SHARES_MIN <= shares <= SHARES_MAX):
        errors.append("shares_outstanding_out_of_range")
    if cash is None or cash < 0 or not math.isfinite(cash):
        errors.append("invalid_cash")
    if debt is None or debt < 0 or not math.isfinite(debt):
        errors.append("invalid_debt")
    if DISCOUNT_RATE <= 0:
        errors.append("invalid_discount_rate")
    if TERMINAL_GROWTH >= DISCOUNT_RATE:
        errors.append("terminal_growth_gte_discount_rate")
    mcap = fnum(market_cap)
    if mcap is not None and not (MARKET_CAP_MIN <= mcap <= MARKET_CAP_MAX):
        errors.append("market_cap_out_of_range")
    return errors


def dcf_model(ticker, fcf, shares, cash, debt, extras=None):
    """Simplified FCFF (unlevered free cash flow) model.

    Enterprise value = PV(5-year FCFF) + PV(terminal value)
    Equity value     = Enterprise value + cash - debt
    Fair value/share = Equity value / diluted shares outstanding
    """
    extras = extras or {}
    warnings = list(extras.get("warnings") or [])
    errors = _dcf_input_errors(fcf, shares, cash, debt, extras.get("market_cap"))
    inputs = {
        "normalized_fcf": fnum(fcf),
        "shares": fnum(shares),
        "cash": fnum(cash),
        "debt": fnum(debt),
        "discount_rate": DISCOUNT_RATE,
        "terminal_growth": TERMINAL_GROWTH,
        "fcf_method": extras.get("fcf_method"),
        "fcf_period": extras.get("fcf_period"),
        "operating_cash_flow": extras.get("operating_cash_flow"),
        "capital_expenditure_raw": extras.get("capital_expenditure_raw"),
        "capital_expenditure": extras.get("capital_expenditure"),
    }
    if errors:
        return model_result(
            "DCF",
            valid=False,
            reason=errors[0],
            confidence="invalid",
            inputs=inputs,
            warnings=warnings + errors,
        )

    g = extras.get("dcf_growth_override")
    if g is None:
        g = get_assumption(ticker)["dcf_growth"]
    mature = max(0.06, min(0.10, g * 0.45))
    flows = []
    cur = float(fcf)
    for year in range(1, 6):
        gy = min(g + (mature - g) * (year - 1) / 4, 0.40)
        cur *= (1 + gy)
        if not math.isfinite(cur):
            return model_result("DCF", valid=False, reason="projected_cashflow_not_finite", inputs=inputs, warnings=warnings)
        flows.append(cur)
    pv = sum(cf / ((1 + DISCOUNT_RATE) ** i) for i, cf in enumerate(flows, start=1))
    terminal = flows[-1] * (1 + TERMINAL_GROWTH) / (DISCOUNT_RATE - TERMINAL_GROWTH)
    pv_terminal = terminal / ((1 + DISCOUNT_RATE) ** 5)
    enterprise = pv + pv_terminal
    equity = enterprise + float(cash) - float(debt)
    per_share = equity / float(shares)
    inputs.update({
        "enterprise_value": enterprise,
        "equity_value": equity,
        "dcf_growth": g,
        "fcf_used": float(fcf),
    })
    if per_share is None or not math.isfinite(per_share) or per_share <= 0:
        return model_result(
            "DCF",
            valid=False,
            reason="negative_equity_value",
            confidence="invalid",
            inputs=inputs,
            warnings=warnings,
            extra={"fcf_used": float(fcf)},
        )
    confidence = "medium"
    if extras.get("fcf_method") in {None, "yahoo_info_freeCashflow", "latest_annual"}:
        confidence = "low"
        warnings.append("limited_fcf_history")
    return model_result(
        "DCF",
        valid=True,
        low=per_share * 0.85,
        mid=per_share,
        high=per_share * 1.15,
        confidence=confidence,
        inputs=inputs,
        warnings=warnings,
        extra={"fcf_used": float(fcf)},
    )


def load_snapshots():
    if not SNAPSHOT_FILE.exists():
        return []
    return json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8"))


def nearest_snapshot(ticker: str, as_of: str):
    target = pd.Timestamp(as_of).date()
    candidates = []
    for s in load_snapshots():
        if s.get("ticker") != ticker:
            continue
        try:
            d = pd.Timestamp(s["date"]).date()
            if d <= target:
                candidates.append((d,s))
        except Exception:
            pass
    if not candidates:
        return None
    return max(candidates, key=lambda x:x[0])[1]


def classify_price(price, fair):
    if fair is None or fair <= 0:
        return "N/A"
    ratio = price/fair
    if ratio <= 0.80:
        return "Deep-value zone"
    if ratio <= 0.90:
        return "Attractive zone"
    if ratio <= 1.00:
        return "Fair-to-attractive"
    if ratio <= 1.10:
        return "Near fair value"
    return "Above fair value / observe"


def _model_mid(model):
    return fnum((model or {}).get("mid"))


def apply_outlier_flags(pe, dcf, growth):
    models = {"pe": pe, "dcf": dcf, "growth": growth}
    candidates = {
        name: obj
        for name, obj in models.items()
        if obj and obj.get("valid") is not False and not obj.get("outlier") and range_is_ordered(obj.get("low"), obj.get("mid"), obj.get("high"))
    }
    if len(candidates) < 3:
        return models
    mids = {name: _model_mid(obj) for name, obj in candidates.items()}
    mids = {name: mid for name, mid in mids.items() if mid is not None}
    if len(mids) < 3:
        return models
    consensus = float(np.median(list(mids.values())))
    if consensus <= 0:
        return models
    for name, obj in candidates.items():
        mid = mids.get(name)
        if mid is None:
            continue
        if abs(mid - consensus) / consensus > MODEL_OUTLIER_THRESHOLD:
            flagged = dict(obj)
            flagged["outlier"] = True
            flagged["valid"] = False
            flagged["confidence"] = "invalid"
            flagged["reason"] = flagged.get("reason") or "outlier_vs_other_models"
            flagged["warnings"] = list(obj.get("warnings") or []) + [
                f"outlier_vs_other_models mid={mid:.2f} others_median={consensus:.2f}"
            ]
            models[name] = flagged
    return models


def blend_models(pe, dcf, growth):
    models = apply_outlier_flags(pe, dcf, growth)
    included = []
    excluded = []
    weighted_sum = 0.0
    weight_total = 0.0
    weights_used = {}
    for name, obj in (("pe", models.get("pe")), ("dcf", models.get("dcf")), ("growth", models.get("growth"))):
        if structural_valid(obj):
            included.append(name)
            weighted_sum += float(obj["mid"]) * WEIGHTS[name]
            weight_total += WEIGHTS[name]
            weights_used[name] = WEIGHTS[name]
        else:
            excluded.append({
                "name": name,
                "reason": (obj or {}).get("reason") or "missing",
                "outlier": bool((obj or {}).get("outlier")),
            })
    if len(included) < MIN_MODELS_FOR_BLEND or weight_total <= 0:
        return {
            "fair": None,
            "included": included,
            "excluded": excluded,
            "weights_used": {},
            "insufficient_models": True,
            "confidence": "invalid",
            "models": models,
        }
    weights_used = {name: WEIGHTS[name] / weight_total for name in included}
    confidence = "high" if len(included) == 3 else "medium"
    return {
        "fair": weighted_sum / weight_total,
        "included": included,
        "excluded": excluded,
        "weights_used": weights_used,
        "insufficient_models": False,
        "confidence": confidence,
        "models": models,
    }


def blended_fair(pe, dcf, growth):
    return blend_models(pe, dcf, growth).get("fair")


def buy_zones(fair, technical_mid=None, sma200=None):
    fair = fnum(fair)
    if fair is None or fair <= 0:
        return None
    # Fundamental anchors.
    first = (fair*0.88, fair*0.94)
    core = (fair*0.78, fair*0.86)
    deep = (fair*0.68, fair*0.76)

    # Pull first/core zones toward nearby technical supports if close.
    anchors = [x for x in [technical_mid, sma200] if x and x > 0]
    if anchors:
        nearest = min(anchors, key=lambda x:abs(x-fair*0.9))
        if abs(nearest-fair*0.9)/fair < 0.15:
            width = fair*0.025
            first = (min(first[0], nearest-width), max(first[1], nearest+width))
    return {"first":first,"core":core,"deep":deep}


def value_from_financials(ticker: str, financials: dict):
    from valuation_engine import valuate

    blend = valuate(ticker, financials)
    models = blend.get("models") or {}
    pe = models.get("forward_pe") or models.get("normalized_pe")
    dcf = models.get("normalized_fcf_dcf")
    growth = models.get("growth_adjusted_pe")
    return pe, dcf, growth, blend


def sanity_snapshot(ticker: str) -> dict:
    ticker = ticker.upper().strip()
    df = add_indicators(get_history(ticker, None))
    row = df.iloc[-1]
    price = float(row["Close"])
    f = get_live_fundamentals(ticker)
    from valuation_engine import can_emit_buy_zones

    pe, dcf, growth, blend = value_from_financials(ticker, f)
    fair = blend.get("fair")
    zones = buy_zones(fair, None, fnum(row.get("SMA200"))) if can_emit_buy_zones(blend) else None
    return {
        "ticker": ticker,
        "price": price,
        "pe_mid": _model_mid(pe) if structural_valid(pe) else None,
        "dcf_mid": _model_mid(dcf) if structural_valid(dcf) else None,
        "dcf_status": (dcf or {}).get("reason") or ((dcf or {}).get("confidence") if structural_valid(dcf) else "invalid"),
        "growth_mid": _model_mid(growth) if structural_valid(growth) else None,
        "blended_fair": fair,
        "models_included": blend.get("included"),
        "buy_zones": zones,
        "warnings": f.get("warnings") or [],
        "financials": f,
        "pe": pe,
        "dcf": dcf,
        "growth": growth,
        "blend": blend,
        "valuation_class": (blend.get("profile") or {}).get("valuation_class"),
        "confidence": blend.get("confidence"),
    }


def money(x):
    return "N/A" if x is None or not math.isfinite(float(x)) else f"${x:,.2f}"


def pct(a,b):
    if a is None or b in (None,0):
        return None
    return (a/b-1)*100


def run(ticker, as_of=None):
    ticker = ticker.upper().strip()
    df = add_indicators(get_history(ticker, as_of))
    row = df.iloc[-1]
    trade_date = pd.Timestamp(df.index[-1]).date().isoformat()
    price = float(row["Close"])
    sma30 = fnum(row["SMA30"])
    sma50 = fnum(row["SMA50"])
    sma200 = fnum(row["SMA200"])
    vp = volume_profile_zone(df)

    historical = as_of is not None and pd.Timestamp(as_of).date() < date.today()

    pe = dcf = growth = None
    fair = None
    valuation_note = ""
    blend = None

    if historical:
        snap = nearest_snapshot(ticker, as_of)
        if snap:
            pe = snap.get("models",{}).get("pe")
            dcf = snap.get("models",{}).get("dcf")
            growth = snap.get("models",{}).get("growth")
            fair = snap.get("blended_fair_value")
            valuation_note = f"Using nearest saved valuation snapshot on/before {as_of}: {snap['date']}"
        else:
            valuation_note = (
                "No point-in-time valuation snapshot exists on/before this date. "
                "Technical comparison is valid, but historical fair value is intentionally left blank "
                "to avoid look-ahead bias."
            )
    else:
        from valuation_engine import can_emit_buy_zones
        f = get_live_fundamentals(ticker)
        pe, dcf, growth, blend = value_from_financials(ticker, f)
        fair = blend.get("fair")
        valuation_note = f"V4 {blend.get('profile', {}).get('valuation_class_label') or ''} | confidence={blend.get('confidence')}"
        if blend.get("excluded"):
            reasons = ", ".join(f"{item['name']}={item['reason']}" for item in blend["excluded"])
            valuation_note += f" Excluded models: {reasons}."
        if blend.get("warnings"):
            valuation_note += " " + ", ".join(blend["warnings"])

    if historical:
        zones = buy_zones(fair, vp["mid"] if vp else None, sma200) if fair else None
    else:
        from valuation_engine import can_emit_buy_zones
        zones = buy_zones(fair, vp["mid"] if vp else None, sma200) if can_emit_buy_zones(blend) else None

    print("\n" + "="*72)
    print(f"{ticker}  |  price date: {trade_date}")
    print("="*72)
    print(f"Close:   {money(price)}")
    print(f"SMA30:   {money(sma30)}   distance: {pct(price,sma30):+.2f}%" if sma30 else "SMA30: N/A")
    print(f"SMA50:   {money(sma50)}   distance: {pct(price,sma50):+.2f}%" if sma50 else "SMA50: N/A")
    print(f"SMA200:  {money(sma200)}   distance: {pct(price,sma200):+.2f}%" if sma200 else "SMA200: N/A")
    if vp:
        print(f"1Y volume-density zone (approx.): {money(vp['low'])} - {money(vp['high'])}")

    print("\nValuation")
    print("-"*72)
    def _print_model(label, obj):
        if obj and obj.get("valid") and range_is_ordered(obj.get("low"), obj.get("mid"), obj.get("high")):
            print(f"{label:<16}{money(obj['low'])} / {money(obj['mid'])} / {money(obj['high'])}")
        elif obj:
            print(f"{label:<16}N/A  ({obj.get('reason') or 'invalid'})")
        else:
            print(f"{label:<16}N/A")
    _print_model("P/E model:", pe)
    _print_model("DCF model:", dcf)
    _print_model("Growth model:", growth)
    if blend and blend.get("model_list"):
        for obj in blend["model_list"]:
            _print_model(f"{obj.get('name')}:", obj)
    print(f"Blended fair:   {money(fair)}")
    if blend:
        print(f"Class/confidence: {blend.get('profile', {}).get('valuation_class')} / {blend.get('confidence')}")
    if fair:
        print(f"Price vs fair:  {pct(price,fair):+.2f}%")
        print(f"Valuation state: {classify_price(price,fair)}")

    if zones:
        print("\nSuggested valuation zones (not trading advice)")
        print("-"*72)
        print(f"First-entry:    {money(zones['first'][0])} - {money(zones['first'][1])}")
        print(f"Core-buy:       {money(zones['core'][0])} - {money(zones['core'][1])}")
        print(f"Deep-value:     {money(zones['deep'][0])} - {money(zones['deep'][1])}")

    print("\nNotes")
    print("-"*72)
    print(valuation_note)
    print("Volume-density zone is an estimate from daily price/volume bars, not actual investor cost basis.")
    print("Fair value is a model output, not Investing.com's proprietary Fair Value.")
    print("="*72 + "\n")


def main():
    p = argparse.ArgumentParser(description="Magnificent Seven valuation + technical monitor")
    p.add_argument("ticker", nargs="?", help="AAPL MSFT GOOGL AMZN NVDA META TSLA")
    p.add_argument("--date", help="Historical date, YYYY-MM-DD")
    p.add_argument("--sanity", action="store_true", help="Run MAG7 valuation sanity check")
    args = p.parse_args()

    if args.sanity:
        print(f"{'ticker':<7} {'price':>10} {'class':<24} {'conf':<12} {'fair':>10} included")
        for ticker in ("AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"):
            snap = sanity_snapshot(ticker)
            print(
                f"{snap['ticker']:<7} {money(snap['price']):>10} {str(snap.get('valuation_class') or '-'):<24} "
                f"{str(snap.get('confidence') or '-'):<12} {money(snap['blended_fair']):>10} "
                f"{','.join(snap['models_included'] or [])}"
            )
        return

    ticker = args.ticker or input("Ticker (AAPL/MSFT/GOOGL/AMZN/NVDA/META/TSLA): ").strip()
    as_of = args.date
    if as_of is None:
        d = input("Date YYYY-MM-DD (press Enter for latest): ").strip()
        as_of = d or None
    run(ticker, as_of)


if __name__ == "__main__":
    main()
