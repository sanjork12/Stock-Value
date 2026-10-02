"""Financial data normalization: EPS provenance, currency gates, canonical shares.

This layer does not change PE ranges, growth caps, DCF formulas, or valuation classes.
It only labels sources and blocks unsafe unit mixing before models run.
"""
from __future__ import annotations

from valuation_primitives import fnum

SHARE_MISMATCH_THRESHOLD = 0.10
STATEMENT_EPS_SOURCES = {
    "statement_derived",
    "statement_trailing_eps",
    "income_statement_diluted_eps",
    "ni_over_diluted_shares",
    "historical_eps",
}
YAHOO_TRAILING_SOURCES = {
    "trailingEps",
    "ticker.info.trailingEps",
    "yahoo_trailing_eps",
    "trailing_eps",
}
FORWARD_EPS_SOURCES = {
    "forwardEps",
    "ticker.info.forwardEps",
    "epsForward",
    "earnings_estimate",
    "price/forwardPE",
    "forward_eps",
}
CURRENCY_MISMATCH_REASON = "currency_mismatch_without_fx_conversion"
CLASS_SPECIFIC_SHARES = "class_specific_shares_detected"


def _ccy(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    return text or None


def currency_mismatch(financials: dict | None) -> bool:
    data = financials or {}
    quote = _ccy(data.get("quote_currency"))
    fin = _ccy(data.get("financial_currency") or data.get("eps_currency"))
    return bool(quote and fin and quote != fin)


def currencies_known_and_aligned(financials: dict | None) -> bool:
    data = financials or {}
    quote = _ccy(data.get("quote_currency"))
    fin = _ccy(data.get("financial_currency"))
    if not quote or not fin:
        return True
    return quote == fin


def is_statement_eps_source(source: str | None) -> bool:
    if not source:
        return False
    return str(source) in STATEMENT_EPS_SOURCES


def statement_inputs_currency_safe(financials: dict | None) -> bool:
    """False when statement-denominated totals/EPS must not enter quote-currency valuation."""
    data = financials or {}
    if data.get("fx_converted"):
        return True
    if currency_mismatch(data):
        return False
    return True


def _positive(value) -> float | None:
    number = fnum(value)
    if number is None or number <= 0:
        return None
    return number


def _mcap_implied_shares(financials: dict) -> float | None:
    price = _positive(financials.get("current_price") or financials.get("price"))
    market_cap = _positive(financials.get("market_cap"))
    if not price or not market_cap:
        return None
    return market_cap / price


def _diluted_shares(financials: dict) -> float | None:
    explicit = _positive(financials.get("diluted_average_shares"))
    if explicit:
        return explicit
    hist = financials.get("historical_eps") or []
    if hist:
        return _positive(hist[0].get("shares"))
    return None


def _gap(left: float, right: float) -> float:
    if not right:
        return 0.0
    return abs(left - right) / abs(right)


def resolve_canonical_shares(financials: dict) -> dict:
    outstanding = _positive(financials.get("shares_outstanding"))
    if outstanding is None:
        outstanding = _positive(financials.get("shares"))
    implied = _positive(
        financials.get("implied_shares_outstanding")
        or financials.get("implied_shares")
        or financials.get("impliedSharesOutstanding")
    )
    mcap_implied = _mcap_implied_shares(financials)
    diluted = _diluted_shares(financials)
    warnings: list[str] = []
    class_specific = False
    reference = implied or mcap_implied
    if outstanding and reference and _gap(outstanding, reference) > SHARE_MISMATCH_THRESHOLD:
        class_specific = True
        warnings.append(CLASS_SPECIFIC_SHARES)
        warnings.append("share_count_warning")

    canonical = None
    source = None
    if implied:
        canonical, source = implied, "impliedSharesOutstanding"
        if mcap_implied and _gap(implied, mcap_implied) > SHARE_MISMATCH_THRESHOLD:
            canonical, source = mcap_implied, "marketCap/price"
    elif mcap_implied:
        canonical, source = mcap_implied, "marketCap/price"
    elif diluted:
        canonical, source = diluted, "diluted_average_shares"
    elif outstanding and not class_specific:
        canonical, source = outstanding, "sharesOutstanding"
    elif outstanding and class_specific:
        # Dual-class / class-specific count is not a valid enterprise denominator.
        canonical, source = None, None
        warnings.append("sharesOutstanding_rejected_as_enterprise_denominator")

    return {
        "canonical_shares": canonical,
        "canonical_shares_source": source,
        "shares_outstanding": outstanding,
        "implied_shares_outstanding": implied,
        "market_cap_over_price": mcap_implied,
        "diluted_average_shares": diluted,
        "class_specific_shares": class_specific,
        "warnings": warnings,
    }


def _latest_statement_eps(financials: dict) -> tuple[float | None, str | None]:
    explicit = _positive(financials.get("statement_eps"))
    if explicit:
        source = financials.get("statement_eps_source") or "income_statement_diluted_eps"
        return explicit, source
    hist = financials.get("historical_eps") or []
    if not hist:
        return None, None
    row = hist[0] or {}
    eps = _positive(row.get("diluted_eps") if row.get("diluted_eps") is not None else row.get("eps"))
    if eps is None:
        return None, None
    if row.get("diluted_eps") is not None:
        return eps, "income_statement_diluted_eps"
    return eps, "ni_over_diluted_shares"


def _yahoo_forward_eps(financials: dict) -> tuple[float | None, str | None]:
    value = fnum(financials.get("forward_eps"))
    if value is not None and value <= 0:
        value = None
    if value:
        source = financials.get("forward_eps_source")
        if source and is_statement_eps_source(source):
            return None, None
        return value, source or "forward_eps"
    return None, None


def _yahoo_trailing_eps(financials: dict) -> tuple[float | None, str | None]:
    value = fnum(financials.get("trailing_eps"))
    if value is not None and value <= 0:
        value = None
    source = financials.get("trailing_eps_source")
    if value and is_statement_eps_source(source):
        return None, None
    if value:
        return value, source or "trailing_eps"
    return None, None


def normalize_financials(financials: dict | None) -> dict:
    """Attach EPS provenance, currency gate, and canonical shares. Idempotent."""
    data = dict(financials or {})
    warnings = [w for w in (data.get("warnings") or []) if w]

    quote_ccy = _ccy(data.get("quote_currency"))
    fin_ccy = _ccy(data.get("financial_currency"))
    data["quote_currency"] = quote_ccy
    data["financial_currency"] = fin_ccy
    data["fx_converted"] = bool(data.get("fx_converted"))
    mismatch = currency_mismatch(data)
    data["currency_mismatch"] = mismatch
    statement_safe = statement_inputs_currency_safe(data)
    data["statement_inputs_currency_safe"] = statement_safe
    if mismatch and not data["fx_converted"]:
        if CURRENCY_MISMATCH_REASON not in warnings:
            warnings.append(CURRENCY_MISMATCH_REASON)

    forward, forward_source = _yahoo_forward_eps(data)
    if forward is None:
        data["forward_eps"] = None
        data["forward_eps_source"] = None
    else:
        data["forward_eps"] = forward
        data["forward_eps_source"] = forward_source

    yahoo_trailing, yahoo_trailing_source = _yahoo_trailing_eps(data)
    statement_eps, statement_source = _latest_statement_eps(data)
    data["statement_eps"] = statement_eps
    data["statement_eps_source"] = statement_source
    data["statement_eps_currency"] = fin_ccy
    data["eps_currency"] = fin_ccy

    trailing = yahoo_trailing
    trailing_source = yahoo_trailing_source
    if trailing is None and statement_eps and statement_safe:
        trailing = statement_eps
        trailing_source = "statement_derived"
    elif trailing is None and statement_eps and not statement_safe:
        trailing = None
        trailing_source = None
        if "statement_eps_blocked_currency_mismatch" not in warnings:
            warnings.append("statement_eps_blocked_currency_mismatch")
    data["trailing_eps"] = trailing
    data["trailing_eps_source"] = trailing_source

    data["eps_proxy"] = None
    data["eps_proxy_source"] = None
    data["eps_proxy_currency_safe"] = False
    if data["forward_eps"] is None:
        if yahoo_trailing:
            data["eps_proxy"] = yahoo_trailing
            data["eps_proxy_source"] = "trailing_eps"
            data["eps_proxy_currency_safe"] = True
        elif statement_eps and statement_safe:
            data["eps_proxy"] = statement_eps
            data["eps_proxy_source"] = "statement_trailing_eps"
            data["eps_proxy_currency_safe"] = True
        elif statement_eps and not statement_safe:
            if CURRENCY_MISMATCH_REASON not in warnings:
                warnings.append(CURRENCY_MISMATCH_REASON)
        if data["eps_proxy"]:
            for code in ("forward_eps_unavailable", "using_trailing_eps_proxy"):
                if code not in warnings:
                    warnings.append(code)
            if data["eps_proxy_source"] == "statement_trailing_eps" and "using_statement_derived_trailing_eps_proxy" not in warnings:
                warnings.append("using_statement_derived_trailing_eps_proxy")

    share_info = resolve_canonical_shares(data)
    for code in share_info["warnings"]:
        if code not in warnings:
            warnings.append(code)
    data["shares_outstanding"] = share_info["shares_outstanding"]
    data["implied_shares_outstanding"] = share_info["implied_shares_outstanding"]
    data["market_cap_over_price"] = share_info["market_cap_over_price"]
    data["diluted_average_shares"] = share_info["diluted_average_shares"]
    data["canonical_shares"] = share_info["canonical_shares"]
    data["canonical_shares_source"] = share_info["canonical_shares_source"]
    data["class_specific_shares"] = share_info["class_specific_shares"]
    if share_info["canonical_shares"]:
        data["shares"] = share_info["canonical_shares"]
    elif share_info["class_specific_shares"]:
        data["shares"] = None
    elif fnum(data.get("shares")) is None and share_info["diluted_average_shares"]:
        data["shares"] = share_info["diluted_average_shares"]
        data["canonical_shares"] = data["shares"]
        data["canonical_shares_source"] = "diluted_average_shares"

    bv = fnum(data.get("tangible_book_value_per_share")) or fnum(data.get("book_value_per_share"))
    trailing_for_roe = yahoo_trailing or (trailing if statement_safe else None)
    if fnum(data.get("roe")) is None and bv and bv > 0 and trailing_for_roe and statement_safe:
        data["roe"] = trailing_for_roe / bv
        if "roe_fallback_eps_over_bvps" not in warnings:
            warnings.append("roe_fallback_eps_over_bvps")

    data["warnings"] = warnings
    data["provenance"] = {
        "quote_currency": quote_ccy,
        "financial_currency": fin_ccy,
        "forward_eps": {"value": data.get("forward_eps"), "source": data.get("forward_eps_source")},
        "trailing_eps": {"value": data.get("trailing_eps"), "source": data.get("trailing_eps_source")},
        "statement_eps": {
            "value": data.get("statement_eps"),
            "currency": data.get("statement_eps_currency"),
            "source": data.get("statement_eps_source"),
        },
        "eps_proxy": {
            "value": data.get("eps_proxy"),
            "source": data.get("eps_proxy_source"),
            "currency_safe": bool(data.get("eps_proxy_currency_safe")),
        },
        "shares": {
            "sharesOutstanding": share_info["shares_outstanding"],
            "impliedSharesOutstanding": share_info["implied_shares_outstanding"],
            "marketCap/price": share_info["market_cap_over_price"],
            "diluted_average_shares": share_info["diluted_average_shares"],
            "canonical_shares": data.get("canonical_shares"),
            "canonical_source": data.get("canonical_shares_source"),
        },
        "currency_mismatch": mismatch,
        "fx_converted": bool(data.get("fx_converted")),
    }
    return data


def quote_currency_eps_for_conversion(financials: dict) -> tuple[float | None, str | None]:
    """Earnings figure used for FCF conversion. Never statement-derived FY EPS."""
    data = financials or {}
    forward = _positive(data.get("forward_eps"))
    if forward and not is_statement_eps_source(data.get("forward_eps_source")):
        return forward, data.get("forward_eps_source") or "forward_eps"
    trailing = _positive(data.get("trailing_eps"))
    source = data.get("trailing_eps_source")
    if trailing and not is_statement_eps_source(source):
        return trailing, source or "trailing_eps"
    return None, None


def has_statement_only_eps(financials: dict) -> bool:
    data = financials or {}
    quote_eps, _ = quote_currency_eps_for_conversion(data)
    if quote_eps:
        return False
    proxy_source = data.get("eps_proxy_source")
    trailing_source = data.get("trailing_eps_source")
    return bool(
        _positive(data.get("statement_eps"))
        or is_statement_eps_source(proxy_source)
        or is_statement_eps_source(trailing_source)
    )
