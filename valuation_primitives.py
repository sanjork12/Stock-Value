from __future__ import annotations

import math

GENERIC_ASSUMPTION = {"pe_range": [18, 24], "norm_growth": 0.12, "peg_target": 1.5, "growth_pe_cap": 30, "dcf_growth": 0.10}

# These are intentionally editable assumptions, not "truth".
# They are the valuation framework used by this program.
ASSUMPTIONS = {
    "AAPL": {"pe_range": [28, 32], "norm_growth": 0.09, "peg_target": 1.8, "growth_pe_cap": 32, "dcf_growth": 0.08},
    "MSFT": {"pe_range": [27, 32], "norm_growth": 0.18, "peg_target": 1.7, "growth_pe_cap": 34, "dcf_growth": 0.16},
    "GOOGL": {"pe_range": [22, 26], "norm_growth": 0.18, "peg_target": 1.5, "growth_pe_cap": 30, "dcf_growth": 0.16},
    "AMZN": {"pe_range": [27, 32], "norm_growth": 0.20, "peg_target": 1.5, "growth_pe_cap": 34, "dcf_growth": 0.18},
    "NVDA": {"pe_range": [25, 32], "norm_growth": 0.24, "peg_target": 1.4, "growth_pe_cap": 38, "dcf_growth": 0.22},
    "META": {"pe_range": [22, 27], "norm_growth": 0.16, "peg_target": 1.5, "growth_pe_cap": 30, "dcf_growth": 0.15},
    "TSLA": {"pe_range": [60, 100], "norm_growth": 0.25, "peg_target": 2.0, "growth_pe_cap": 120, "dcf_growth": 0.18},
}

DISCOUNT_RATE = 0.09
TERMINAL_GROWTH = 0.03
MODEL_OUTLIER_THRESHOLD = 0.60
MIN_MODELS_FOR_BLEND = 2
SHARES_MIN = 1e8
SHARES_MAX = 1e11
MARKET_CAP_MIN = 1e9
MARKET_CAP_MAX = 1e14


def fnum(x):
    try:
        if x is None:
            return None
        x = float(x)
        return x if math.isfinite(x) else None
    except Exception:
        return None


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


def get_assumption(ticker):
    return ASSUMPTIONS.get(str(ticker).upper(), GENERIC_ASSUMPTION.copy())


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
        "pv_explicit": pv,
        "pv_terminal": pv_terminal,
        "terminal_value_share": (pv_terminal / enterprise) if enterprise else None,
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
