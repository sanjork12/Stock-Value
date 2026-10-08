from __future__ import annotations
from copy import deepcopy

import logging
import math
import re
from dataclasses import dataclass, field

from financial_normalization import (
    CURRENCY_MISMATCH_REASON,
    FORWARD_AND_TRAILING_UNAVAILABLE,
    has_statement_only_eps,
    is_statement_eps_source,
    normalize_financials,
    quote_currency_eps_for_conversion,
    statement_inputs_currency_safe,
)
from valuation_primitives import (
    DISCOUNT_RATE,
    MODEL_OUTLIER_THRESHOLD,
    MIN_MODELS_FOR_BLEND,
    TERMINAL_GROWTH,
    dcf_model,
    fnum,
    model_result,
    range_is_ordered,
    structural_valid,
)

MODEL_VERSION = "v4.2.1-exit-reliability"
TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
COST_OF_EQUITY_DEFAULT = 0.10
logger = logging.getLogger("stock_fair_value_monitor")

CLASS_LABELS = {
    "mega_cap_tech": "Mega-Cap Tech",
    "mature_growth": "Mature Growth",
    "semiconductor_growth": "Semiconductor Growth",
    "cyclical_semiconductor": "Cyclical Semiconductor",
    "bank": "Bank",
    "fintech_exchange": "Fintech Exchange",
    "crypto_treasury": "Crypto Treasury",
    "high_growth_software": "High-Growth Software",
    "pre_profit_growth": "Pre-Profit Growth",
    "space_optionality": "Space Optionality",
    "auto_optionality": "Auto Optionality",
    "consumer_platform": "Consumer Platform",
    "generic_profitable": "Generic Profitable",
    "unsupported_specialized": "Specialized / Unsupported",
}

SPECIALIZED_CLASSES = {
    "crypto_treasury",
    "space_optionality",
    "auto_optionality",
    "unsupported_specialized",
}

VALUATION_PROFILE_OVERRIDES = {
    "AAPL": "mega_cap_tech",
    "MSFT": "mega_cap_tech",
    "GOOGL": "mega_cap_tech",
    "GOOG": "mega_cap_tech",
    "AMZN": "mega_cap_tech",
    "META": "mega_cap_tech",
    "NVDA": "semiconductor_growth",
    "AVGO": "semiconductor_growth",
    "MU": "cyclical_semiconductor",
    "JPM": "bank",
    "BAC": "bank",
    "WFC": "bank",
    "C": "bank",
    "COIN": "fintech_exchange",
    "BMNR": "crypto_treasury",
    "MSTR": "crypto_treasury",
    "PLTR": "high_growth_software",
    "SNOW": "high_growth_software",
    "SPCX": "space_optionality",
    "TSLA": "auto_optionality",
    "TEM": "pre_profit_growth",
    "NFLX": "consumer_platform",
    "UBER": "mature_growth",
    "BABA": "consumer_platform",
    "ORCL": "mature_growth",
}

CLASS_SPECS = {
    "mega_cap_tech": {
        "preferred": ["forward_pe", "normalized_fcf_dcf", "growth_adjusted_pe"],
        "excluded": [],
        "weights": {"forward_pe": 0.35, "normalized_fcf_dcf": 0.40, "growth_adjusted_pe": 0.25},
        "pe_range": (24, 32),
        "norm_growth": 0.12,
        "peg_target": 1.6,
        "growth_pe_cap": 32,
        "dcf_growth": 0.12,
        "max_sustainable_growth": 0.16,
        "confidence_policy": "medium_high",
        "ev_ebitda_range": (14, 22),
        "sales_multiple_range": (4, 8),
    },
    "mature_growth": {
        "preferred": ["forward_pe", "normalized_fcf_dcf", "growth_adjusted_pe"],
        "excluded": [],
        "weights": {"forward_pe": 0.40, "normalized_fcf_dcf": 0.35, "growth_adjusted_pe": 0.25},
        "pe_range": (18, 26),
        "norm_growth": 0.10,
        "peg_target": 1.5,
        "growth_pe_cap": 28,
        "dcf_growth": 0.10,
        "max_sustainable_growth": 0.14,
        "confidence_policy": "medium",
        "ev_ebitda_range": (10, 16),
        "sales_multiple_range": (3, 6),
    },
    "semiconductor_growth": {
        "preferred": ["forward_pe", "growth_adjusted_pe", "normalized_fcf_dcf"],
        "excluded": [],
        "weights": {"forward_pe": 0.35, "growth_adjusted_pe": 0.30, "normalized_fcf_dcf": 0.35},
        "pe_range": (20, 28),
        "norm_growth": 0.16,
        "peg_target": 1.3,
        "growth_pe_cap": 28,
        "dcf_growth": 0.12,
        "max_sustainable_growth": 0.18,
        "confidence_policy": "medium",
        "ev_ebitda_range": (16, 24),
        "sales_multiple_range": (8, 14),
    },
    "cyclical_semiconductor": {
        "preferred": ["normalized_pe", "normalized_cycle_earnings", "ev_ebitda", "normalized_fcf_dcf"],
        "excluded": ["growth_adjusted_pe"],
        "weights": {
            "normalized_pe": 0.30,
            "normalized_cycle_earnings": 0.30,
            "ev_ebitda": 0.20,
            "normalized_fcf_dcf": 0.20,
        },
        "pe_range": (10, 16),
        "norm_growth": 0.06,
        "peg_target": 1.2,
        "growth_pe_cap": 16,
        "dcf_growth": 0.06,
        "max_sustainable_growth": 0.08,
        "confidence_policy": "medium",
        "ev_ebitda_range": (6, 10),
        "sales_multiple_range": (2, 4),
    },
    "bank": {
        "preferred": ["price_to_book_roe", "normalized_pe", "residual_income"],
        "excluded": ["normalized_fcf_dcf"],
        "weights": {"price_to_book_roe": 0.40, "normalized_pe": 0.35, "residual_income": 0.25},
        "pe_range": (9, 13),
        "norm_growth": 0.04,
        "peg_target": 1.2,
        "growth_pe_cap": 14,
        "dcf_growth": 0.04,
        "max_sustainable_growth": 0.06,
        "confidence_policy": "medium",
        "cost_of_equity": 0.10,
    },
    "fintech_exchange": {
        "preferred": ["normalized_pe", "ev_ebitda", "revenue_multiple"],
        "excluded": ["normalized_fcf_dcf"],
        "weights": {"normalized_pe": 0.35, "ev_ebitda": 0.35, "revenue_multiple": 0.30},
        "pe_range": (12, 20),
        "norm_growth": 0.10,
        "peg_target": 1.3,
        "growth_pe_cap": 22,
        "dcf_growth": 0.08,
        "max_sustainable_growth": 0.12,
        "confidence_policy": "low",
        "ev_ebitda_range": (8, 16),
        "sales_multiple_range": (4, 8),
    },
    "crypto_treasury": {
        "preferred": [],
        "excluded": ["forward_pe", "normalized_fcf_dcf", "growth_adjusted_pe"],
        "weights": {},
        "confidence_policy": "specialized",
        "fair_policy": "specialized",
    },
    "high_growth_software": {
        "preferred": ["forward_pe", "revenue_multiple", "normalized_fcf_dcf", "growth_adjusted_pe"],
        "excluded": [],
        "weights": {
            "forward_pe": 0.30,
            "revenue_multiple": 0.25,
            "normalized_fcf_dcf": 0.25,
            "growth_adjusted_pe": 0.20,
        },
        "pe_range": (28, 48),
        "norm_growth": 0.20,
        "peg_target": 1.6,
        "growth_pe_cap": 50,
        "dcf_growth": 0.16,
        "max_sustainable_growth": 0.22,
        "confidence_policy": "low",
        "ev_ebitda_range": (20, 35),
        "sales_multiple_range": (8, 16),
    },
    "pre_profit_growth": {
        "preferred": ["revenue_multiple"],
        "excluded": ["forward_pe", "normalized_fcf_dcf", "growth_adjusted_pe"],
        "weights": {"revenue_multiple": 1.0},
        "confidence_policy": "specialized",
        "fair_policy": "specialized_if_unprofitable",
        "sales_multiple_range": (4, 10),
    },
    "space_optionality": {
        "preferred": [],
        "excluded": ["forward_pe", "normalized_fcf_dcf", "growth_adjusted_pe"],
        "weights": {},
        "confidence_policy": "specialized",
        "fair_policy": "specialized",
    },
    "auto_optionality": {
        "preferred": [],
        "excluded": ["forward_pe", "normalized_fcf_dcf", "growth_adjusted_pe"],
        "weights": {},
        "confidence_policy": "specialized",
        "fair_policy": "specialized",
    },
    "consumer_platform": {
        "preferred": ["forward_pe", "normalized_fcf_dcf", "growth_adjusted_pe"],
        "excluded": [],
        "weights": {"forward_pe": 0.40, "normalized_fcf_dcf": 0.35, "growth_adjusted_pe": 0.25},
        "pe_range": (20, 30),
        "norm_growth": 0.12,
        "peg_target": 1.5,
        "growth_pe_cap": 32,
        "dcf_growth": 0.11,
        "max_sustainable_growth": 0.16,
        "confidence_policy": "medium",
        "sales_multiple_range": (3, 7),
    },
    "generic_profitable": {
        "preferred": ["forward_pe", "normalized_fcf_dcf", "growth_adjusted_pe"],
        "excluded": [],
        "weights": {"forward_pe": 0.40, "normalized_fcf_dcf": 0.35, "growth_adjusted_pe": 0.25},
        "pe_range": (14, 22),
        "norm_growth": 0.08,
        "peg_target": 1.4,
        "growth_pe_cap": 22,
        "dcf_growth": 0.08,
        "max_sustainable_growth": 0.12,
        "confidence_policy": "low",
        "ev_ebitda_range": (8, 14),
        "sales_multiple_range": (2, 5),
    },
    "unsupported_specialized": {
        "preferred": [],
        "excluded": ["forward_pe", "normalized_fcf_dcf", "growth_adjusted_pe"],
        "weights": {},
        "confidence_policy": "specialized",
        "fair_policy": "specialized",
    },
}

TICKER_SPEC_OVERLAYS = {
    "AAPL": {"pe_range": (26, 32), "norm_growth": 0.08, "growth_pe_cap": 30, "dcf_growth": 0.07, "max_sustainable_growth": 0.10},
    "MSFT": {"pe_range": (26, 32), "norm_growth": 0.12, "growth_pe_cap": 32, "dcf_growth": 0.11, "max_sustainable_growth": 0.14},
    "GOOGL": {"pe_range": (20, 26), "norm_growth": 0.12, "dcf_growth": 0.11},
    "GOOG": {"pe_range": (20, 26), "norm_growth": 0.12, "dcf_growth": 0.11},
    "AMZN": {"pe_range": (26, 32), "norm_growth": 0.14, "dcf_growth": 0.12, "max_sustainable_growth": 0.16},
    "META": {"pe_range": (20, 26), "norm_growth": 0.12, "dcf_growth": 0.11},
    "NVDA": {"pe_range": (20, 28), "norm_growth": 0.16, "growth_pe_cap": 28, "dcf_growth": 0.12, "max_sustainable_growth": 0.18},
}


@dataclass
class ValuationProfile:
    ticker: str
    sector: str | None = None
    industry: str | None = None
    business_model: str | None = None
    valuation_class: str = "generic_profitable"
    profitability_state: str = "unknown"
    cyclicality: str = "low"
    optionality_level: str = "low"
    preferred_models: list[str] = field(default_factory=list)
    excluded_models: list[str] = field(default_factory=list)
    model_weights: dict[str, float] = field(default_factory=dict)
    confidence_policy: str = "medium"
    spec: dict = field(default_factory=dict)
    source: str = "inferred"

    @property
    def label(self) -> str:
        return CLASS_LABELS.get(self.valuation_class, self.valuation_class)

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "sector": self.sector,
            "industry": self.industry,
            "business_model": self.business_model,
            "valuation_class": self.valuation_class,
            "valuation_class_label": self.label,
            "profitability_state": self.profitability_state,
            "cyclicality": self.cyclicality,
            "optionality_level": self.optionality_level,
            "preferred_models": self.preferred_models,
            "excluded_models": self.excluded_models,
            "model_weights": self.model_weights,
            "confidence_policy": self.confidence_policy,
            "source": self.source,
        }


def normalize_ticker(raw: str | None) -> str | None:
    if not raw:
        return None
    ticker = str(raw).strip().upper()
    if not TICKER_RE.match(ticker):
        return None
    return ticker


def _quote_trailing_eps(financials: dict) -> float | None:
    trailing = fnum(financials.get("trailing_eps"))
    if trailing is None or trailing <= 0:
        return None
    if is_statement_eps_source(financials.get("trailing_eps_source")):
        return None
    return trailing


def _multiple_eps(financials: dict) -> tuple[float | None, str, bool]:
    """Return (eps, source, is_proxy). Never mutates forward_eps. Never uses FX-unsafe statement EPS."""
    forward = fnum(financials.get("forward_eps"))
    if forward is not None and forward > 0 and not is_statement_eps_source(financials.get("forward_eps_source")):
        return forward, str(financials.get("forward_eps_source") or "forward_eps"), False
    safe = statement_inputs_currency_safe(financials)
    proxy = fnum(financials.get("eps_proxy"))
    proxy_source = str(financials.get("eps_proxy_source") or "")
    if proxy is not None and proxy > 0:
        if is_statement_eps_source(proxy_source) and not safe:
            proxy = None
        elif financials.get("eps_proxy_currency_safe") is False:
            proxy = None
        else:
            return proxy, proxy_source or "trailing_eps", True
    trailing = fnum(financials.get("trailing_eps"))
    trailing_source = str(financials.get("trailing_eps_source") or "trailing_eps")
    if trailing is not None and trailing > 0:
        if is_statement_eps_source(trailing_source) and not safe:
            return None, "", False
        return trailing, trailing_source, True
    return None, "", False


def _enterprise_shares(financials: dict) -> float | None:
    return fnum(financials.get("canonical_shares")) or fnum(financials.get("shares"))


def _currency_blocks_enterprise(financials: dict) -> tuple[bool, str, str]:
    if not statement_inputs_currency_safe(financials):
        return True, CURRENCY_MISMATCH_REASON, "报表货币与报价货币不一致，且没有 FX conversion，企业级模型不适用。"
    return False, "", ""


def _profitability_state(financials: dict) -> str:
    eps = fnum(financials.get("forward_eps")) or fnum(financials.get("eps_proxy")) or fnum(financials.get("trailing_eps"))
    fcf = fnum(financials.get("fcf"))
    if (eps is None or eps <= 0) and (fcf is None or fcf <= 0):
        return "unprofitable"
    if (eps is not None and eps > 0) and (fcf is not None and fcf > 0):
        return "profitable"
    return "mixed"


def infer_valuation_class(ticker: str, financials: dict | None = None) -> str:
    ticker = (ticker or "").upper()
    financials = financials or {}
    if ticker in VALUATION_PROFILE_OVERRIDES:
        return VALUATION_PROFILE_OVERRIDES[ticker]
    sector = str(financials.get("sector") or "").lower()
    industry = str(financials.get("industry") or "").lower()
    state = _profitability_state(financials)
    if state == "unprofitable":
        return "pre_profit_growth"
    if "bank" in industry or (sector == "financial services" and "bank" in industry):
        return "bank"
    if "semiconductor" in industry:
        if any(token in industry for token in ("memory", "dram", "equipment")):
            return "cyclical_semiconductor"
        growth = fnum(financials.get("earnings_growth")) or 0
        if growth > 0.35:
            return "semiconductor_growth"
        return "cyclical_semiconductor"
    if "software" in industry:
        return "high_growth_software"
    if "capital markets" in industry or "financial data" in industry or "exchange" in industry:
        return "fintech_exchange"
    if "internet" in industry or "consumer" in sector:
        return "consumer_platform"
    return "generic_profitable"


def build_profile(ticker: str, financials: dict | None = None) -> ValuationProfile:
    ticker = (ticker or "").upper()
    financials = financials or {}
    override = ticker in VALUATION_PROFILE_OVERRIDES
    vclass = infer_valuation_class(ticker, financials)
    spec = dict(CLASS_SPECS.get(vclass) or CLASS_SPECS["generic_profitable"])
    spec.update(TICKER_SPEC_OVERLAYS.get(ticker, {}))
    cyclicality = "high" if "cyclical" in vclass else ("medium" if "semi" in vclass or "fintech" in vclass else "low")
    optionality = "high" if vclass in SPECIALIZED_CLASSES or vclass == "pre_profit_growth" else "low"
    return ValuationProfile(
        ticker=ticker,
        sector=financials.get("sector"),
        industry=financials.get("industry"),
        business_model=vclass,
        valuation_class=vclass,
        profitability_state=_profitability_state(financials),
        cyclicality=cyclicality,
        optionality_level=optionality,
        preferred_models=list(spec.get("preferred") or []),
        excluded_models=list(spec.get("excluded") or []),
        model_weights=dict(spec.get("weights") or {}),
        confidence_policy=spec.get("confidence_policy") or "medium",
        spec=spec,
        source="override" if override else "inferred",
    )


def _implied_forward_growth(financials: dict) -> float | None:
    forward = fnum(financials.get("forward_eps"))
    trailing = fnum(financials.get("trailing_eps"))
    if forward is None or trailing is None or trailing <= 0 or forward <= 0:
        return None
    g = forward / trailing - 1
    if g <= -0.5 or g >= 1:
        return None
    return g


def _cap_growth(raw, spec: dict, financials: dict | None = None) -> float:
    cap = fnum(spec.get("max_sustainable_growth")) or 0.16
    base = fnum(spec.get("norm_growth")) or 0.10
    live = fnum(raw)
    implied = _implied_forward_growth(financials or {})
    samples = [base]
    if live is not None and 0 < live < 1:
        samples.append(min(live, 0.50))
    if implied is not None and implied > 0:
        samples.append(implied)
    return min(sum(samples) / len(samples), cap)


def _positive_history_eps(financials: dict) -> list[float]:
    if not statement_inputs_currency_safe(financials):
        return []
    history = [fnum(row.get("eps")) for row in (financials.get("historical_eps") or [])]
    values = [v for v in history if v is not None and v > 0]
    if not values:
        return []
    median_hist = float(sorted(values)[len(values) // 2])
    ref = _quote_trailing_eps(financials) or fnum(financials.get("forward_eps"))
    if ref and median_hist > 0:
        ratio = ref / median_hist
        if ratio > 5 or ratio < 0.2:
            return []
    return values


def _cycle_eps(financials: dict) -> tuple[float | None, str]:
    forward = fnum(financials.get("forward_eps"))
    if forward is not None and (forward <= 0 or is_statement_eps_source(financials.get("forward_eps_source"))):
        forward = None
    trailing = _quote_trailing_eps(financials)
    history = _positive_history_eps(financials)
    growth = fnum(financials.get("earnings_growth"))
    rebound = growth is not None and growth > 1
    if history:
        median_hist = float(sorted(history)[len(history) // 2])
        if forward and forward > 0:
            if rebound:
                return 0.35 * forward + 0.65 * median_hist, "rebound_capped_blend"
            return 0.40 * forward + 0.60 * median_hist, "forward_history_blend"
        if trailing:
            if rebound:
                return 0.35 * trailing + 0.65 * median_hist, "rebound_capped_ttm"
            return trailing, "trailing_eps"
        return median_hist, "history_median"
    if forward and trailing and trailing > 0:
        if rebound:
            return 0.35 * forward + 0.65 * trailing, "rebound_capped_ttm"
        return 0.50 * forward + 0.50 * trailing, "forward_ttm_blend"
    if trailing and trailing > 0:
        return trailing, "trailing_eps"
    if forward and forward > 0:
        if rebound:
            return forward * 0.25, "forward_rebound_haircut"
        return forward, "forward_eps"
    return None, "missing_eps"


def _cycle_median_eps(financials: dict) -> tuple[float | None, str]:
    history = _positive_history_eps(financials)
    if history:
        return float(sorted(history)[len(history) // 2]), "history_median"
    trailing = _quote_trailing_eps(financials)
    if trailing and trailing > 0:
        return trailing, "trailing_eps"
    return _cycle_eps(financials)


def _has_quote_currency_eps(financials: dict) -> bool:
    forward = fnum(financials.get("forward_eps"))
    if forward and forward > 0 and not is_statement_eps_source(financials.get("forward_eps_source")):
        return True
    return _quote_trailing_eps(financials) is not None


def _statement_derived_proxy_in_use(financials: dict) -> bool:
    if _has_quote_currency_eps(financials):
        return False
    source = financials.get("eps_proxy_source") or financials.get("trailing_eps_source")
    return is_statement_eps_source(source)


def _blocks_official_statement_proxy(profile: ValuationProfile, financials: dict) -> bool:
    if _has_quote_currency_eps(financials):
        return False
    return profile.valuation_class in STATEMENT_PROXY_BLOCKS_OFFICIAL


def model_forward_pe(profile: ValuationProfile, financials: dict) -> dict:
    spec = profile.spec
    eps, source, is_proxy = _multiple_eps(financials)
    if eps is None or eps <= 0:
        return model_result("Forward P/E", valid=False, reason="missing_or_nonpositive_forward_eps", extra={"model_id": "forward_pe", "applicable": True})
    lo, hi = spec.get("pe_range") or (16, 22)
    name = "Trailing EPS Proxy P/E" if is_proxy else "Forward P/E"
    warnings = ["forward_eps_unavailable", "using_trailing_eps_proxy"] if is_proxy else []
    if is_proxy and is_statement_eps_source(source):
        warnings.append("using_statement_derived_trailing_eps_proxy")
    return model_result(
        name,
        valid=True,
        low=eps * lo,
        mid=eps * (lo + hi) / 2,
        high=eps * hi,
        confidence="low" if is_proxy else ("high" if profile.confidence_policy == "medium_high" else "medium"),
        inputs={
            "forward_eps": fnum(financials.get("forward_eps")),
            "eps_used": eps,
            "eps_source": source,
            "eps_proxy": True if is_proxy else False,
            "uses_proxy": bool(is_proxy),
            "proxy_source": source if is_proxy else None,
            "pe_low": lo,
            "pe_high": hi,
            "currency": financials.get("quote_currency"),
        },
        warnings=warnings,
        extra={
            "model_id": "forward_pe",
            "applicable": True,
            "valuation_class": profile.valuation_class,
            "eps_proxy": is_proxy,
            "uses_proxy": bool(is_proxy),
            "proxy_source": source if is_proxy else None,
        },
    )


def model_normalized_pe(profile: ValuationProfile, financials: dict) -> dict:
    spec = profile.spec
    eps, method = _cycle_eps(financials)
    if eps is None or eps <= 0:
        return model_result("Normalized P/E", valid=False, reason="missing_cycle_eps", extra={"model_id": "normalized_pe", "applicable": True})
    lo, hi = spec.get("pe_range") or (12, 18)
    return model_result(
        "Normalized P/E",
        valid=True,
        low=eps * lo,
        mid=eps * (lo + hi) / 2,
        high=eps * hi,
        confidence="medium",
        inputs={"normalized_eps": eps, "eps_method": method, "pe_low": lo, "pe_high": hi},
        extra={"model_id": "normalized_pe", "applicable": True, "valuation_class": profile.valuation_class},
    )


def model_growth_adjusted_pe(profile: ValuationProfile, financials: dict) -> dict:
    spec = profile.spec
    eps, source, is_proxy = _multiple_eps(financials)
    if eps is None or eps <= 0:
        return model_result("Growth-adjusted P/E", valid=False, reason="missing_or_nonpositive_forward_eps", extra={"model_id": "growth_adjusted_pe", "applicable": True})
    g = _cap_growth(financials.get("earnings_growth"), spec, financials)
    floor = (spec.get("pe_range") or (10, 22))[0]
    fair_pe = max(floor, min(g * 100 * spec.get("peg_target", 1.5), spec.get("growth_pe_cap", 28)))
    name = "Growth-adjusted P/E (trailing proxy)" if is_proxy else "Growth-adjusted P/E"
    warnings = ["forward_eps_unavailable", "using_trailing_eps_proxy"] if is_proxy else []
    if is_proxy and is_statement_eps_source(source):
        warnings.append("using_statement_derived_trailing_eps_proxy")
    return model_result(
        name,
        valid=True,
        low=eps * fair_pe * 0.88,
        mid=eps * fair_pe,
        high=eps * fair_pe * 1.12,
        confidence="low" if is_proxy else "medium",
        inputs={
            "forward_eps": fnum(financials.get("forward_eps")),
            "eps_used": eps,
            "eps_source": source,
            "eps_proxy": True if is_proxy else False,
            "uses_proxy": bool(is_proxy),
            "proxy_source": source if is_proxy else None,
            "growth_used": g,
            "fair_pe": fair_pe,
            "peg_target": spec.get("peg_target"),
            "currency": financials.get("quote_currency"),
        },
        warnings=warnings,
        extra={
            "model_id": "growth_adjusted_pe",
            "applicable": True,
            "fair_pe": fair_pe,
            "growth_used": g,
            "valuation_class": profile.valuation_class,
            "eps_proxy": is_proxy,
            "uses_proxy": bool(is_proxy),
            "proxy_source": source if is_proxy else None,
        },
    )


def model_normalized_fcf_dcf(profile: ValuationProfile, financials: dict) -> dict:
    spec = profile.spec
    result = dcf_model(
        profile.ticker,
        financials.get("fcf"),
        _enterprise_shares(financials),
        financials.get("cash"),
        financials.get("debt"),
        extras={
            "market_cap": financials.get("market_cap"),
            "warnings": financials.get("warnings") or [],
            "fcf_method": financials.get("fcf_method"),
            "fcf_period": financials.get("fcf_period"),
            "operating_cash_flow": financials.get("operating_cash_flow"),
            "capital_expenditure_raw": financials.get("capital_expenditure_raw"),
            "capital_expenditure": financials.get("capital_expenditure"),
            "dcf_growth_override": spec.get("dcf_growth"),
            "canonical_shares_source": financials.get("canonical_shares_source"),
            "quote_currency": financials.get("quote_currency"),
            "financial_currency": financials.get("financial_currency"),
        },
    )
    result["name"] = "Normalized FCF DCF"
    result["model_id"] = "normalized_fcf_dcf"
    result["applicable"] = True
    result["valuation_class"] = profile.valuation_class
    inputs = dict(result.get("inputs") or {})
    inputs["canonical_shares_source"] = financials.get("canonical_shares_source")
    inputs["currency"] = financials.get("quote_currency")
    result["inputs"] = inputs
    return result


def model_price_to_book_roe(profile: ValuationProfile, financials: dict) -> dict:
    spec = profile.spec
    bvps = fnum(financials.get("tangible_book_value_per_share")) or fnum(financials.get("book_value_per_share"))
    roe = fnum(financials.get("roe"))
    r = fnum(spec.get("cost_of_equity")) or COST_OF_EQUITY_DEFAULT
    g = min(fnum(spec.get("norm_growth")) or 0.03, r - 0.01)
    if bvps is None or bvps <= 0 or roe is None or roe <= 0:
        return model_result("P/B × ROE", valid=False, reason="missing_book_or_roe", extra={"model_id": "price_to_book_roe", "applicable": True})
    if roe <= g:
        pb = max(0.8, roe / r)
    else:
        pb = (roe - g) / (r - g)
    pb = max(0.6, min(pb, 3.5))
    mid = pb * bvps
    return model_result(
        "P/B × ROE",
        valid=True,
        low=mid * 0.88,
        mid=mid,
        high=mid * 1.12,
        confidence="medium",
        inputs={"bvps": bvps, "roe": roe, "cost_of_equity": r, "g": g, "justified_pb": pb},
        extra={"model_id": "price_to_book_roe", "applicable": True, "valuation_class": profile.valuation_class},
    )


def model_residual_income(profile: ValuationProfile, financials: dict) -> dict:
    spec = profile.spec
    bvps = fnum(financials.get("tangible_book_value_per_share")) or fnum(financials.get("book_value_per_share"))
    roe = fnum(financials.get("roe"))
    r = fnum(spec.get("cost_of_equity")) or COST_OF_EQUITY_DEFAULT
    g = min(fnum(spec.get("norm_growth")) or 0.03, r - 0.01)
    if bvps is None or bvps <= 0 or roe is None:
        return model_result("Residual Income", valid=False, reason="missing_book_or_roe", extra={"model_id": "residual_income", "applicable": True})
    mid = bvps + ((roe - r) * bvps) / (r - g)
    if mid is None or mid <= 0 or not math.isfinite(mid):
        return model_result("Residual Income", valid=False, reason="nonpositive_residual_income", extra={"model_id": "residual_income", "applicable": True})
    return model_result(
        "Residual Income",
        valid=True,
        low=mid * 0.88,
        mid=mid,
        high=mid * 1.12,
        confidence="medium",
        inputs={"bvps": bvps, "roe": roe, "cost_of_equity": r, "g": g},
        extra={"model_id": "residual_income", "applicable": True, "valuation_class": profile.valuation_class},
    )


def model_ev_ebitda(profile: ValuationProfile, financials: dict) -> dict:
    spec = profile.spec
    ebitda = fnum(financials.get("ebitda"))
    shares = _enterprise_shares(financials)
    cash = fnum(financials.get("cash")) or 0.0
    debt = fnum(financials.get("debt")) or 0.0
    if ebitda is None or ebitda <= 0 or shares is None or shares <= 0:
        return model_result("EV/EBITDA", valid=False, reason="missing_ebitda_or_shares", extra={"model_id": "ev_ebitda", "applicable": True})
    lo, hi = spec.get("ev_ebitda_range") or (8, 14)
    def _per_share(multiple):
        equity = ebitda * multiple + cash - debt
        return equity / shares
    low, mid, high = _per_share(lo), _per_share((lo + hi) / 2), _per_share(hi)
    if min(low, mid, high) <= 0:
        return model_result("EV/EBITDA", valid=False, reason="nonpositive_ev_ebitda_equity", extra={"model_id": "ev_ebitda", "applicable": True})
    return model_result(
        "EV/EBITDA",
        valid=True,
        low=low,
        mid=mid,
        high=high,
        confidence="medium",
        inputs={"ebitda": ebitda, "multiple_low": lo, "multiple_high": hi, "cash": cash, "debt": debt, "shares": shares, "currency": financials.get("quote_currency"), "canonical_shares_source": financials.get("canonical_shares_source")},
        extra={"model_id": "ev_ebitda", "applicable": True, "valuation_class": profile.valuation_class},
    )


def model_revenue_multiple(profile: ValuationProfile, financials: dict) -> dict:
    spec = profile.spec
    revenue = fnum(financials.get("revenue"))
    shares = _enterprise_shares(financials)
    cash = fnum(financials.get("cash")) or 0.0
    debt = fnum(financials.get("debt")) or 0.0
    if revenue is None or revenue <= 0 or shares is None or shares <= 0:
        return model_result("Revenue Multiple", valid=False, reason="missing_revenue_or_shares", extra={"model_id": "revenue_multiple", "applicable": True})
    lo, hi = spec.get("sales_multiple_range") or (2, 5)
    def _per_share(multiple):
        return (revenue * multiple + cash - debt) / shares
    low, mid, high = _per_share(lo), _per_share((lo + hi) / 2), _per_share(hi)
    if min(low, mid, high) <= 0:
        return model_result("Revenue Multiple", valid=False, reason="nonpositive_sales_equity", extra={"model_id": "revenue_multiple", "applicable": True})
    return model_result(
        "Revenue Multiple",
        valid=True,
        low=low,
        mid=mid,
        high=high,
        confidence="low",
        inputs={"revenue": revenue, "multiple_low": lo, "multiple_high": hi, "shares": shares, "currency": financials.get("quote_currency"), "canonical_shares_source": financials.get("canonical_shares_source")},
        extra={"model_id": "revenue_multiple", "applicable": True, "valuation_class": profile.valuation_class},
    )


def model_normalized_cycle_earnings(profile: ValuationProfile, financials: dict) -> dict:
    spec = profile.spec
    eps, method = _cycle_median_eps(financials)
    if eps is None or eps <= 0:
        return model_result("Cycle-normalized Earnings", valid=False, reason="missing_cycle_eps", extra={"model_id": "normalized_cycle_earnings", "applicable": True})
    lo, hi = spec.get("pe_range") or (10, 16)
    return model_result(
        "Cycle-normalized Earnings",
        valid=True,
        low=eps * lo,
        mid=eps * (lo + hi) / 2,
        high=eps * hi,
        confidence="medium",
        inputs={"cycle_eps": eps, "eps_method": method, "pe_low": lo, "pe_high": hi},
        extra={"model_id": "normalized_cycle_earnings", "applicable": True, "valuation_class": profile.valuation_class},
    )


MODEL_RUNNERS = {
    "forward_pe": model_forward_pe,
    "normalized_pe": model_normalized_pe,
    "growth_adjusted_pe": model_growth_adjusted_pe,
    "normalized_fcf_dcf": model_normalized_fcf_dcf,
    "price_to_book_roe": model_price_to_book_roe,
    "residual_income": model_residual_income,
    "ev_ebitda": model_ev_ebitda,
    "revenue_multiple": model_revenue_multiple,
    "normalized_cycle_earnings": model_normalized_cycle_earnings,
}

MODEL_DISPLAY_NAMES = {
    "forward_pe": "Forward P/E",
    "normalized_pe": "Normalized P/E",
    "growth_adjusted_pe": "Growth-adjusted P/E",
    "normalized_fcf_dcf": "Normalized FCF DCF",
    "price_to_book_roe": "P/B × ROE",
    "residual_income": "Residual Income",
    "ev_ebitda": "EV/EBITDA",
    "revenue_multiple": "Revenue Multiple",
    "normalized_cycle_earnings": "Cycle-normalized Earnings",
    "unsupported": "Unsupported / specialized",
}

PEG_DISABLED_CLASSES = {"cyclical_semiconductor", "fintech_exchange"}
STATEMENT_PROXY_BLOCKS_OFFICIAL = {
    "semiconductor_growth",
    "high_growth_software",
    "cyclical_semiconductor",
    "fintech_exchange",
}
STATEMENT_PROXY_ALLOWED_LOW = {
    "mega_cap_tech",
    "mature_growth",
    "consumer_platform",
    "generic_profitable",
    "bank",
}


@dataclass
class ReliabilityResult:
    overall_confidence: str
    reliability_score: int | None
    data_quality_score: int | None = None
    model_count_total: int = 0
    model_count_valid: int = 0
    model_count_included: int = 0
    model_count_excluded: int = 0
    dispersion_pct: float | None = None
    dispersion_band: str | None = None
    applicability_warnings: list = field(default_factory=list)
    model_warnings: list = field(default_factory=list)
    excluded_models: list = field(default_factory=list)
    data_quality: str = "unknown"
    valuation_stability: str = "unknown"
    explanation: str = ""
    penalties: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "overall_confidence": self.overall_confidence,
            "reliability_score": self.reliability_score,
            "data_quality_score": self.data_quality_score,
            "model_count_total": self.model_count_total,
            "model_count_valid": self.model_count_valid,
            "model_count_included": self.model_count_included,
            "model_count_excluded": self.model_count_excluded,
            "dispersion_pct": self.dispersion_pct,
            "dispersion_band": self.dispersion_band,
            "applicability_warnings": self.applicability_warnings,
            "model_warnings": self.model_warnings,
            "excluded_models": self.excluded_models,
            "data_quality": self.data_quality,
            "valuation_stability": self.valuation_stability,
            "explanation": self.explanation,
            "penalties": self.penalties,
        }


def _not_applicable(model_id: str, reason: str, why: str, diagnostics: dict | None = None) -> dict:
    return model_result(
        MODEL_DISPLAY_NAMES.get(model_id, model_id),
        valid=False,
        reason=reason,
        extra={
            "model_id": model_id,
            "applicable": False,
            "applicability_reason": reason,
            "why_applicable": why,
            "executed": False,
            "diagnostics": diagnostics or {},
        },
    )


def _fcf_observations(financials: dict) -> tuple[list[float], list[float]]:
    rows = financials.get("annual_cashflows") or []
    values = [fnum(row.get("free_cash_flow")) for row in rows]
    values = [v for v in values if v is not None]
    ttm = fnum(financials.get("fcf_ttm_info"))
    observations = list(values)
    if ttm is not None:
        if not observations or abs(ttm - observations[0]) / max(abs(observations[0]), 1) > 0.02:
            observations.append(ttm)
    return values, observations


def check_forward_pe_applicable(profile: ValuationProfile, financials: dict) -> tuple[bool, str, str, dict]:
    eps, source, is_proxy = _multiple_eps(financials)
    trailing = fnum(financials.get("trailing_eps"))
    diag = {
        "forward_eps": fnum(financials.get("forward_eps")),
        "trailing_eps": trailing,
        "eps_proxy": fnum(financials.get("eps_proxy")),
        "eps_source": source,
        "is_proxy": is_proxy,
        "proxy_source": source if is_proxy else None,
        "currency": financials.get("quote_currency"),
        "financial_currency": financials.get("financial_currency"),
    }
    if eps is None or eps <= 0:
        if financials.get("statement_eps") and not statement_inputs_currency_safe(financials):
            return False, CURRENCY_MISMATCH_REASON, "报表 EPS 与报价货币不一致，且没有 FX conversion。", diag
        return False, "missing_or_nonpositive_forward_eps", "Forward EPS 缺失或非正，且没有可用的 currency-safe trailing EPS proxy。", diag
    if eps < 0.05:
        return False, "forward_eps_near_zero", "EPS 接近 0，倍数估值不稳定。", diag
    if is_proxy:
        if is_statement_eps_source(source) and profile.valuation_class in STATEMENT_PROXY_BLOCKS_OFFICIAL:
            return False, FORWARD_AND_TRAILING_UNAVAILABLE, "Forward 与 Yahoo trailing EPS 均缺失，statement-derived EPS 不能用于该估值类型的正式估值。", diag
        why = "Forward EPS unavailable. Using trailing EPS proxy."
        if is_statement_eps_source(source):
            why = "Forward EPS unavailable. Using statement-derived trailing EPS proxy."
        return True, "applicable_proxy", why, diag
    if trailing and trailing > 0 and eps / trailing > 5:
        return False, "eps_forecast_anomalous", "Forward EPS 相对 trailing 变化过大，预测可能异常。", diag
    why = "盈利为正，forward EPS 数据完整。"
    if trailing and trailing > 0 and abs(eps / trailing - 1) > 1:
        why += " 预测变化较大，已降低该模型置信度。"
    return True, "applicable", why, diag


def check_normalized_pe_applicable(profile: ValuationProfile, financials: dict) -> tuple[bool, str, str, dict]:
    if not _has_quote_currency_eps(financials):
        reason = CURRENCY_MISMATCH_REASON if not statement_inputs_currency_safe(financials) else "missing_quote_currency_eps"
        why = (
            "报表货币与报价货币不一致，周期 EPS 不能直接用于估值。"
            if reason == CURRENCY_MISMATCH_REASON
            else "缺少 Yahoo trailing / forward EPS，不能把单年报表 FY EPS 当作周期 TTM。"
        )
        return False, reason, why, {"method": "missing_quote_currency_eps"}
    eps, method = _cycle_eps(financials)
    hist = _positive_history_eps(financials)
    diag = {"normalized_eps": eps, "method": method, "history_points": len(hist)}
    if eps is None or eps <= 0:
        return False, "missing_cycle_eps", "缺少可用于周期标准化的 EPS。", diag
    why = "使用 cycle-normalized EPS，而非当前峰值/谷值 EPS。"
    return True, "applicable", why, diag


def check_growth_applicable(profile: ValuationProfile, financials: dict) -> tuple[bool, str, str, dict]:
    if profile.valuation_class in PEG_DISABLED_CLASSES:
        return False, "peg_disabled_for_class", "周期或交易型业务默认禁用普通 PEG。", {"valuation_class": profile.valuation_class}
    eps, source, is_proxy = _multiple_eps(financials)
    if eps is None or eps <= 0:
        if financials.get("statement_eps") and not statement_inputs_currency_safe(financials):
            return False, CURRENCY_MISMATCH_REASON, "报表 EPS 与报价货币不一致，Growth 模型不适用。", {"eps_source": source, "is_proxy": is_proxy}
        return False, "missing_or_nonpositive_forward_eps", "缺少正的 Forward EPS 或 currency-safe trailing EPS proxy，Growth 模型不适用。", {"eps_source": source, "is_proxy": is_proxy}
    if is_proxy and is_statement_eps_source(source) and profile.valuation_class in STATEMENT_PROXY_BLOCKS_OFFICIAL:
        return (
            False,
            FORWARD_AND_TRAILING_UNAVAILABLE,
            "Forward 与 Yahoo trailing EPS 均缺失，statement-derived EPS 不能用于该估值类型的正式估值。",
            {"eps_source": source, "is_proxy": is_proxy, "valuation_class": profile.valuation_class},
        )
    live = fnum(financials.get("earnings_growth"))
    why = "使用规范化远期增长率，而非单年爆发增长。"
    if is_proxy:
        why = "Forward EPS unavailable. Using trailing EPS proxy + normalized growth. This is not an analyst-forward model."
        if is_statement_eps_source(source):
            why = "Forward EPS unavailable. Using statement-derived trailing EPS proxy + normalized growth."
    elif live is not None and live > 1:
        why = "当前 EPS 增长属于 rebound/cycle effect，已忽略单年增速，改用 normalized growth。"
    return True, "applicable_proxy" if is_proxy else "applicable", why, {"earnings_growth": live, "eps_source": source, "is_proxy": is_proxy}


def check_dcf_applicable(profile: ValuationProfile, financials: dict) -> tuple[bool, str, str, dict]:
    blocked, reason, why = _currency_blocks_enterprise(financials)
    if blocked:
        return False, reason, why, {"financial_currency": financials.get("financial_currency"), "quote_currency": financials.get("quote_currency")}
    annual, observations = _fcf_observations(financials)
    norm = fnum(financials.get("fcf"))
    latest = annual[0] if annual else fnum(financials.get("fcf_ttm_info"))
    diag = {
        "observation_count": len(observations),
        "annual_count": len(annual),
        "normalized_fcf": norm,
        "latest_fcf": latest,
        "shares": _enterprise_shares(financials),
        "canonical_shares_source": financials.get("canonical_shares_source"),
        "quote_currency": financials.get("quote_currency"),
        "financial_currency": financials.get("financial_currency"),
    }
    if len(observations) < 3:
        return False, "insufficient_fcf_history", "可用年度/TTM FCF 观测不足 3 个，DCF 不适用。", diag
    if annual and sum(1 for v in annual if v <= 0) > len(annual) / 2:
        return False, "mostly_negative_fcf", "多数年份 FCF 为负，DCF 不适用。", diag
    if norm is None or norm <= 0:
        return False, "normalized_fcf_nonpositive", "Normalized FCF 非正，DCF 不适用。", diag
    if len(annual) >= 2:
        mean = sum(annual) / len(annual)
        var = sum((v - mean) ** 2 for v in annual) / len(annual)
        cv = math.sqrt(var) / abs(mean) if mean else float("inf")
        diag["fcf_cv"] = cv
        if cv > 1.2:
            return False, "normalized_fcf_not_stable_enough", "FCF 波动过大，DCF 不适用。", diag
    revenue = fnum(financials.get("revenue"))
    if revenue and revenue > 0 and norm:
        diag["fcf_margin"] = norm / revenue
    if latest is not None and norm:
        gap = abs(latest - norm) / abs(norm)
        diag["latest_vs_normalized"] = gap
        if gap > 2.0:
            return False, "fcf_latest_vs_normalized_extreme", "最新 FCF 与 normalized FCF 差异过大，可能存在 CapEx 扭曲。", diag
        if latest < 0.5 * abs(norm) and norm > 0:
            return False, "capex_or_fcf_distortion", "最新 FCF 显著低于 normalized FCF，CapEx/FCF 扭曲过高。", diag
    shares = _enterprise_shares(financials)
    quote_eps, eps_src = quote_currency_eps_for_conversion(financials)
    diag["eps_for_conversion"] = quote_eps
    diag["eps_for_conversion_source"] = eps_src
    if shares and shares > 0 and quote_eps and quote_eps > 0 and norm:
        conversion = (norm / shares) / quote_eps
        diag["fcf_eps_conversion"] = conversion
        if conversion < 0.25:
            return False, "fcf_conversion_too_low", "Normalized FCF 相对 EPS 过低，DCF 不能可靠代表盈利能力。", diag
    elif has_statement_only_eps(financials) and shares and shares > 0 and norm:
        return False, "fcf_conversion_unverified", "缺少 quote-currency Forward/Yahoo trailing EPS，不能用报表 FY EPS 验证 FCF conversion。", diag
    return True, "applicable", "有足够年度 FCF 且波动可接受。", diag


def check_pb_roe_applicable(profile: ValuationProfile, financials: dict) -> tuple[bool, str, str, dict]:
    blocked, reason, why = _currency_blocks_enterprise(financials)
    if blocked:
        return False, reason, why, {"bvps": financials.get("book_value_per_share")}
    bvps = fnum(financials.get("tangible_book_value_per_share")) or fnum(financials.get("book_value_per_share"))
    roe = fnum(financials.get("roe"))
    if bvps is None or bvps <= 0 or roe is None or roe <= 0:
        return False, "missing_book_or_roe", "缺少账面价值或 ROE，银行估值模型不适用。", {"bvps": bvps, "roe": roe}
    return True, "applicable", "账面价值与 ROE 数据完整。", {"bvps": bvps, "roe": roe}


def check_residual_income_applicable(profile: ValuationProfile, financials: dict) -> tuple[bool, str, str, dict]:
    return check_pb_roe_applicable(profile, financials)


def check_ev_ebitda_applicable(profile: ValuationProfile, financials: dict) -> tuple[bool, str, str, dict]:
    blocked, reason, why = _currency_blocks_enterprise(financials)
    if blocked:
        return False, reason, why, {"ebitda": financials.get("ebitda")}
    ebitda = fnum(financials.get("ebitda"))
    shares = _enterprise_shares(financials)
    if ebitda is None or ebitda <= 0 or shares is None or shares <= 0:
        return False, "missing_ebitda_or_shares", "缺少正的 EBITDA 或股本。", {"ebitda": ebitda, "shares": shares}
    return True, "applicable", "EBITDA 与股本数据完整。", {"ebitda": ebitda, "shares": shares}


def check_revenue_applicable(profile: ValuationProfile, financials: dict) -> tuple[bool, str, str, dict]:
    blocked, reason, why = _currency_blocks_enterprise(financials)
    if blocked:
        return False, reason, why, {"revenue": financials.get("revenue")}
    revenue = fnum(financials.get("revenue"))
    shares = _enterprise_shares(financials)
    if revenue is None or revenue <= 0 or shares is None or shares <= 0:
        return False, "missing_revenue_or_shares", "缺少收入或股本。", {"revenue": revenue, "shares": shares}
    return True, "applicable", "收入与股本数据完整。", {"revenue": revenue, "shares": shares}


def check_cycle_earnings_applicable(profile: ValuationProfile, financials: dict) -> tuple[bool, str, str, dict]:
    if not _has_quote_currency_eps(financials):
        reason = CURRENCY_MISMATCH_REASON if not statement_inputs_currency_safe(financials) else "missing_quote_currency_eps"
        why = (
            "报表货币与报价货币不一致，周期盈利模型不适用。"
            if reason == CURRENCY_MISMATCH_REASON
            else "缺少 Yahoo trailing / forward EPS，不能把单年报表 FY EPS 当作周期 TTM。"
        )
        return False, reason, why, {"method": "missing_quote_currency_eps"}
    eps, method = _cycle_median_eps(financials)
    if eps is None or eps <= 0:
        return False, "missing_cycle_eps", "缺少周期标准化 EPS。", {"method": method}
    return True, "applicable", "使用中周期盈利，而非当前周期峰值/谷值。", {"cycle_eps": eps, "method": method}


APPLICABILITY_GATES = {
    "forward_pe": check_forward_pe_applicable,
    "normalized_pe": check_normalized_pe_applicable,
    "growth_adjusted_pe": check_growth_applicable,
    "normalized_fcf_dcf": check_dcf_applicable,
    "price_to_book_roe": check_pb_roe_applicable,
    "residual_income": check_residual_income_applicable,
    "ev_ebitda": check_ev_ebitda_applicable,
    "revenue_multiple": check_revenue_applicable,
    "normalized_cycle_earnings": check_cycle_earnings_applicable,
}


def run_model(model_id: str, profile: ValuationProfile, financials: dict, *, _gate_result=None) -> dict:
    gate = APPLICABILITY_GATES.get(model_id)
    why = ""
    if gate:
        ok, reason, why, diag = _gate_result if _gate_result is not None else gate(profile, financials)
        if not ok:
            return _not_applicable(model_id, reason, why, diag)
    runner = MODEL_RUNNERS.get(model_id)
    if not runner:
        return _not_applicable(model_id, "unknown_model", "未知模型。", {})
    result = runner(profile, financials)
    result["executed"] = True
    result["applicable"] = result.get("applicable", True)
    result["applicability_reason"] = result.get("applicability_reason") or "applicable"
    result["why_applicable"] = result.get("why_applicable") or why or "模型通过适用性检查。"
    if model_id == "normalized_fcf_dcf":
        tv_share = fnum((result.get("inputs") or {}).get("terminal_value_share"))
        if tv_share is not None and tv_share > 0.95:
            result["valid"] = False
            result["confidence"] = "invalid"
            result["reason"] = "DCF_LOW_RELIABILITY"
            result["warnings"] = list(result.get("warnings") or []) + ["terminal_value_share_too_high"]
            result["why_applicable"] = "终值占企业价值过高，DCF 可靠性不足。"
        elif tv_share is not None and tv_share > 0.85:
            result["confidence"] = "low"
            result["warnings"] = list(result.get("warnings") or []) + ["high_terminal_value_share"]
    if model_id == "forward_pe":
        trailing = fnum(financials.get("trailing_eps"))
        forward = fnum(financials.get("forward_eps"))
        if trailing and trailing > 0 and forward and abs(forward / trailing - 1) > 1:
            result["confidence"] = "low"
            result["warnings"] = list(result.get("warnings") or []) + ["large_eps_forecast_change"]
    return result


def cycle_context(financials: dict, profile: ValuationProfile | None = None) -> dict:
    raw_hist = [fnum(row.get("eps")) for row in (financials.get("historical_eps") or [])]
    raw_hist = [v for v in raw_hist if v is not None and v > 0]
    hist_median = float(sorted(raw_hist)[len(raw_hist) // 2]) if raw_hist else None
    usable_hist = _positive_history_eps(financials)
    usable_median = float(sorted(usable_hist)[len(usable_hist) // 2]) if usable_hist else hist_median
    cycle_eps, cycle_method = _cycle_eps(financials)
    median_eps, median_method = _cycle_median_eps(financials)
    margins = [fnum(row.get("operating_margin")) for row in (financials.get("historical_margins") or [])]
    margins = [v for v in margins if v is not None]
    norm_margin = float(sorted(margins)[len(margins) // 2]) if margins else None
    spec = (profile.spec if profile else {}) or {}
    pe_range = spec.get("pe_range") or (10, 16)
    return {
        "current_eps": fnum(financials.get("trailing_eps")),
        "forward_eps": fnum(financials.get("forward_eps")),
        "cycle_normalized_eps": cycle_eps,
        "cycle_eps_method": cycle_method,
        "historical_eps_median": usable_median,
        "raw_historical_eps_median": hist_median,
        "current_operating_margin": fnum(financials.get("operating_margin")),
        "normalized_operating_margin": norm_margin,
        "normalized_fcf": fnum(financials.get("fcf")),
        "cycle_pe_range": pe_range,
        "note": "周期估值使用中周期盈利，而非当前周期峰值/谷值。",
    }


def dispersion_pct(models: list[dict]) -> float | None:
    mids = [fnum(m.get("mid")) for m in models]
    mids = [v for v in mids if v is not None]
    if len(mids) < 2:
        return None
    median = float(sorted(mids)[len(mids) // 2])
    if median <= 0:
        return None
    return (max(mids) - min(mids)) / median


def dispersion_band(disp: float | None) -> str | None:
    if disp is None:
        return None
    if disp < 0.15:
        return "LOW"
    if disp < 0.30:
        return "MODERATE"
    if disp < 0.50:
        return "HIGH"
    return "VERY HIGH"


def classify_volatility(vol: float | None) -> str | None:
    if vol is None:
        return None
    if vol < 0.25:
        return "LOW"
    if vol <= 0.45:
        return "MEDIUM"
    return "HIGH"


def margin_of_safety_profile(
    confidence: str,
    dispersion: float | None,
    volatility: float | None,
    cyclicality: str,
    valuation_class: str | None = None,
) -> dict:
    conf = (confidence or "MEDIUM").upper()
    if conf == "HIGH":
        first, core, deep = 0.08, 0.15, 0.22
    elif conf == "LOW":
        first, core, deep = 0.15, 0.25, 0.35
    else:
        first, core, deep = 0.10, 0.18, 0.27
    extras = []
    if cyclicality == "high" or "cyclical" in str(valuation_class or ""):
        first += 0.05
        core += 0.05
        deep += 0.05
        extras.append("cyclical")
    if dispersion is not None and dispersion > 0.50:
        first += 0.05
        core += 0.05
        deep += 0.05
        extras.append("very_high_dispersion")
    vol_band = classify_volatility(volatility)
    if vol_band == "HIGH":
        first += 0.04
        core += 0.04
        deep += 0.05
        extras.append("high_volatility")
    elif vol_band == "MEDIUM":
        first += 0.02
        core += 0.02
        deep += 0.03
        extras.append("medium_volatility")
    first = min(first, 0.20)
    core = min(core, 0.35)
    deep = min(deep, 0.45)
    return {
        "first_entry_discount": first,
        "core_discount": core,
        "deep_discount": deep,
        "volatility_band": vol_band,
        "adjustments": extras,
    }


def dynamic_buy_zones(
    fair_mid,
    mos: dict,
    technical_mid=None,
    sma200=None,
    low_confidence=False,
):
    fair_mid = fnum(fair_mid)
    if fair_mid is None or fair_mid <= 0 or not mos:
        return None
    band = 0.025
    first_anchor = fair_mid * (1 - mos["first_entry_discount"])
    core_anchor = fair_mid * (1 - mos["core_discount"])
    deep_anchor = fair_mid * (1 - mos["deep_discount"])
    max_adj = 0.05 * fair_mid
    anchors = [x for x in [technical_mid, sma200] if fnum(x)]
    if anchors:
        nearest = min(anchors, key=lambda x: abs(x - first_anchor))
        shift = max(-max_adj, min(max_adj, nearest - first_anchor))
        if abs(nearest - first_anchor) <= max_adj:
            first_anchor += shift
            core_anchor += shift * 0.5
    first = (first_anchor * (1 - band), first_anchor * (1 + band))
    core = (core_anchor * (1 - band), core_anchor * (1 + band))
    deep = (deep_anchor * (1 - band), deep_anchor * (1 + band))
    labels = {
        "first": "参考关注区" if low_confidence else "第一批区",
        "core": "参考折价区" if low_confidence else "核心买入区",
        "deep": "深度折价区" if low_confidence else "深度价值区",
    }
    return {
        "first": first,
        "core": core,
        "deep": deep,
        "labels": labels,
        "mos": mos,
        "low_confidence": low_confidence,
    }


def _class_exit_adjustment(valuation_class: str | None, confidence: str) -> tuple[float, str | None]:
    vclass = str(valuation_class or "")
    conf = (confidence or "").upper()
    if vclass == "bank":
        return -0.02, "bank_narrower"
    if vclass == "semiconductor_growth":
        return 0.05, "semiconductor_growth"
    if vclass == "cyclical_semiconductor":
        return 0.08, "cyclical_semiconductor"
    if vclass == "high_growth_software" and conf == "MEDIUM":
        return 0.08, "high_growth_software_medium"
    if vclass == "consumer_platform":
        return 0.03, "consumer_platform"
    return 0.0, None


def can_emit_exit_zones(blend: dict | None) -> bool:
    """True when a fair range exists for HIGH/MEDIUM — profile may still be qualitative."""
    if not blend:
        return False
    conf = str(blend.get("confidence") or blend.get("overall_confidence") or "").upper()
    if conf not in {"HIGH", "MEDIUM"}:
        return False
    mid = fnum(blend.get("blended_mid") if blend.get("blended_mid") is not None else blend.get("fair"))
    high = fnum(blend.get("blended_high") if blend.get("blended_high") is not None else blend.get("fair_high"))
    return mid is not None and mid > 0 and high is not None and high > 0


def compute_exit_reliability(
    confidence,
    reliability_score=None,
    dispersion_pct=None,
    blended_mid=None,
    blended_high=None,
) -> dict:
    """ExitReliabilityResult: gates precise exit prices separately from valuation confidence."""
    conf = str(confidence or "").upper()
    mid = fnum(blended_mid)
    high = fnum(blended_high)
    score = fnum(reliability_score)
    disp = fnum(dispersion_pct)
    reason_codes: list[str] = []
    warnings: list[str] = []

    if conf in {"SPECIALIZED", "UNAVAILABLE"} or mid is None or high is None:
        exit_conf = "UNAVAILABLE"
        display_mode = "unavailable"
        eligible = False
        if conf == "SPECIALIZED":
            reason_codes.append("specialized_valuation")
        elif conf == "UNAVAILABLE" or mid is None or high is None:
            reason_codes.append("insufficient_fair_value")
        return {
            "eligible_for_precise_exit": False,
            "exit_confidence": exit_conf,
            "exit_reliability_score": score,
            "exit_dispersion_pct": disp,
            "reason_codes": reason_codes,
            "warnings": warnings,
            "display_mode": display_mode,
        }

    if conf == "LOW":
        reason_codes.append("valuation_confidence_low")
        return {
            "eligible_for_precise_exit": False,
            "exit_confidence": "LOW",
            "exit_reliability_score": score,
            "exit_dispersion_pct": disp,
            "reason_codes": reason_codes,
            "warnings": warnings,
            "display_mode": "qualitative",
        }

    # HIGH / MEDIUM valuation confidence with a fair range.
    if score is None or score < 65:
        reason_codes.append("insufficient_exit_reliability")
    if disp is None:
        reason_codes.append("missing_dispersion")
    elif disp > 0.50:
        reason_codes.append("high_model_dispersion")
    elif disp > 0.30:
        reason_codes.append("elevated_model_dispersion")

    eligible = (
        conf in {"HIGH", "MEDIUM"}
        and mid is not None
        and high is not None
        and score is not None
        and score >= 65
        and disp is not None
        and disp <= 0.30
    )

    if eligible:
        display_mode = "precise"
        if conf == "HIGH" and score >= 85 and disp <= 0.15:
            exit_conf = "HIGH"
        else:
            exit_conf = "MEDIUM"
    else:
        display_mode = "qualitative"
        exit_conf = "LOW"
        if disp is not None and disp > 0.50:
            warnings.append("high_model_dispersion_blocks_precise_exit")
        elif score is not None and score < 65:
            warnings.append("insufficient_exit_reliability_blocks_precise_exit")
        elif disp is not None and disp > 0.30:
            warnings.append("elevated_dispersion_blocks_precise_exit")

    return {
        "eligible_for_precise_exit": eligible,
        "exit_confidence": exit_conf,
        "exit_reliability_score": score,
        "exit_dispersion_pct": disp,
        "reason_codes": reason_codes,
        "warnings": warnings,
        "display_mode": display_mode,
    }


def apply_exit_display_guard(profile: dict | None, reliability: dict | None) -> dict | None:
    """Attach ExitReliabilityResult; hide precise prices unless eligible."""
    if not isinstance(profile, dict):
        return None
    out = dict(profile)
    rel = reliability or compute_exit_reliability(
        confidence=out.get("confidence"),
        reliability_score=out.get("reliability_score"),
        dispersion_pct=out.get("dispersion_pct"),
        blended_mid=out.get("blended_mid"),
        blended_high=out.get("blended_high"),
    )
    out["exit_reliability"] = rel
    out["display_mode"] = rel.get("display_mode")
    out["exit_confidence"] = rel.get("exit_confidence")
    out["eligible_for_precise_exit"] = bool(rel.get("eligible_for_precise_exit"))
    out["reason_codes"] = list(rel.get("reason_codes") or [])
    out["exit_warnings"] = list(rel.get("warnings") or [])

    if out["eligible_for_precise_exit"] and out.get("display_mode") == "precise":
        out["internal_thresholds_disabled_by_reliability"] = False
        return out

    # Keep pct thresholds for diagnostics; null user-visible prices.
    out["hold_upper_price"] = None
    out["overvalued_price"] = None
    out["trim_price"] = None
    out["extreme_price"] = None
    out["internal_thresholds_disabled_by_reliability"] = True
    out["internal_hold_upper_pct"] = out.get("hold_upper_pct")
    out["internal_trim_pct"] = out.get("trim_pct")
    out["internal_extreme_pct"] = out.get("extreme_pct")
    return out


def build_exit_zone(
    blended_low,
    blended_mid,
    blended_high,
    confidence,
    reliability_score=None,
    dispersion_pct=None,
    volatility_1y=None,
    cyclicality: str | None = "low",
    valuation_class: str | None = None,
) -> dict | None:
    """Compute overvaluation profile then apply Exit Reliability Guard."""
    rel = compute_exit_reliability(
        confidence=confidence,
        reliability_score=reliability_score,
        dispersion_pct=dispersion_pct,
        blended_mid=blended_mid,
        blended_high=blended_high,
    )
    if rel.get("display_mode") == "unavailable":
        return {
            "display_mode": "unavailable",
            "exit_confidence": rel.get("exit_confidence"),
            "eligible_for_precise_exit": False,
            "exit_reliability": rel,
            "reason_codes": list(rel.get("reason_codes") or []),
            "hold_upper_price": None,
            "overvalued_price": None,
            "trim_price": None,
            "extreme_price": None,
            "internal_thresholds_disabled_by_reliability": True,
            "blended_low": fnum(blended_low),
            "blended_mid": fnum(blended_mid),
            "blended_high": fnum(blended_high),
            "confidence": str(confidence or "").upper(),
            "reliability_score": fnum(reliability_score),
            "dispersion_pct": fnum(dispersion_pct),
        }

    profile = dynamic_overvaluation_profile(
        blended_low=blended_low,
        blended_mid=blended_mid,
        blended_high=blended_high,
        confidence=confidence,
        reliability_score=reliability_score,
        dispersion_pct=dispersion_pct,
        volatility_1y=volatility_1y,
        cyclicality=cyclicality,
        valuation_class=valuation_class,
    )
    if profile is None:
        # LOW confidence etc.: qualitative shell without precise prices.
        return {
            "display_mode": rel.get("display_mode") or "qualitative",
            "exit_confidence": rel.get("exit_confidence") or "LOW",
            "eligible_for_precise_exit": False,
            "exit_reliability": rel,
            "reason_codes": list(rel.get("reason_codes") or []),
            "hold_upper_price": None,
            "overvalued_price": None,
            "trim_price": None,
            "extreme_price": None,
            "internal_thresholds_disabled_by_reliability": True,
            "blended_low": fnum(blended_low),
            "blended_mid": fnum(blended_mid),
            "blended_high": fnum(blended_high),
            "confidence": str(confidence or "").upper(),
            "reliability_score": fnum(reliability_score),
            "dispersion_pct": fnum(dispersion_pct),
        }
    return apply_exit_display_guard(profile, rel)


def dynamic_overvaluation_profile(
    blended_low,
    blended_mid,
    blended_high,
    confidence,
    reliability_score=None,
    dispersion_pct=None,
    volatility_1y=None,
    cyclicality: str | None = "low",
    valuation_class: str | None = None,
) -> dict | None:
    """Dynamic exit / overvaluation thresholds. Not a sell recommendation."""
    conf = str(confidence or "").upper()
    mid = fnum(blended_mid)
    high = fnum(blended_high)
    low = fnum(blended_low)
    if conf not in {"HIGH", "MEDIUM"} or mid is None or mid <= 0 or high is None or high <= 0:
        return None

    if conf == "HIGH":
        hold_upper, overvalued, trim, extreme = 0.08, 0.15, 0.25, 0.40
    else:
        hold_upper, overvalued, trim, extreme = 0.10, 0.20, 0.30, 0.45

    adjustments: list[str] = []
    vol_band = classify_volatility(fnum(volatility_1y))
    vol_adj = 0.0
    if vol_band == "MEDIUM":
        vol_adj = 0.03
        adjustments.append("medium_volatility_+3pct")
    elif vol_band == "HIGH":
        vol_adj = 0.05
        adjustments.append("high_volatility_+5pct")

    hold_upper += vol_adj
    overvalued += vol_adj
    trim += vol_adj
    extreme += vol_adj

    cyclical = str(cyclicality or "").lower() == "high" or "cyclical" in str(valuation_class or "")
    cyclical_adj = 0.0
    if cyclical:
        cyclical_adj = 0.05
        adjustments.append("cyclical_+5pct")
        overvalued += cyclical_adj
        trim += cyclical_adj
        extreme += cyclical_adj

    disp = fnum(dispersion_pct)
    disp_adj = 0.0
    if disp is not None:
        if 0.15 <= disp < 0.30:
            disp_adj = 0.02
            adjustments.append("dispersion_15_30_+2pct")
        elif 0.30 <= disp < 0.50:
            disp_adj = 0.05
            adjustments.append("dispersion_30_50_+5pct")
        elif disp >= 0.50:
            # Very high dispersion should usually be LOW; if still MEDIUM, widen further.
            disp_adj = 0.07
            adjustments.append("dispersion_gt50_+7pct")
    hold_upper += disp_adj
    overvalued += disp_adj
    trim += disp_adj
    extreme += disp_adj

    class_adj, class_tag = _class_exit_adjustment(valuation_class, conf)
    if class_tag:
        adjustments.append(class_tag)
    hold_upper += class_adj
    overvalued += class_adj
    trim += class_adj
    extreme += class_adj

    hold_upper = max(0.0, min(hold_upper, 0.20))
    overvalued = max(0.0, min(overvalued, 0.35))
    trim = max(0.0, min(trim, 0.50))
    extreme = max(0.0, min(extreme, 0.70))

    # Enforce strict pct ordering after caps.
    if overvalued <= hold_upper:
        overvalued = min(0.35, hold_upper + 0.02)
    if trim <= overvalued:
        trim = min(0.50, overvalued + 0.05)
    if extreme <= trim:
        extreme = min(0.70, trim + 0.05)
    if not (hold_upper < overvalued < trim < extreme):
        # Last-resort ladder inside caps.
        hold_upper = min(hold_upper, 0.18)
        overvalued = min(max(overvalued, hold_upper + 0.02), 0.35)
        trim = min(max(trim, overvalued + 0.05), 0.50)
        extreme = min(max(extreme, trim + 0.05), 0.70)

    hold_upper_price = max(mid * (1.0 + hold_upper), high)
    overvalued_price = mid * (1.0 + overvalued)
    trim_price = mid * (1.0 + trim)
    extreme_price = mid * (1.0 + extreme)

    # Prices must stay ordered and trim must clear the fair high bound.
    overvalued_price = max(overvalued_price, hold_upper_price * 1.001)
    trim_price = max(trim_price, overvalued_price * 1.001, high * 1.001)
    extreme_price = max(extreme_price, trim_price * 1.001)

    return {
        "hold_upper_pct": hold_upper,
        "overvalued_pct": overvalued,
        "trim_pct": trim,
        "extreme_pct": extreme,
        "hold_upper_price": hold_upper_price,
        "overvalued_price": overvalued_price,
        "trim_price": trim_price,
        "extreme_price": extreme_price,
        "blended_low": low,
        "blended_mid": mid,
        "blended_high": high,
        "confidence": conf,
        "reliability_score": reliability_score,
        "dispersion_pct": disp,
        "volatility_1y": fnum(volatility_1y),
        "volatility_band": vol_band,
        "cyclicality": cyclicality,
        "valuation_class": valuation_class,
        "adjustments": adjustments,
        "vol_adj": vol_adj,
        "cyclical_adj": cyclical_adj,
        "dispersion_adj": disp_adj,
        "class_adj": class_adj,
    }


def _blend_range(model_pairs: list[tuple[str, dict]], weights_used: dict) -> tuple[float | None, float | None, float | None]:
    low_sum = mid_sum = high_sum = 0.0
    total = 0.0
    for model_id, obj in model_pairs:
        w = float(weights_used.get(model_id) or 0)
        if w <= 0:
            continue
        low, mid, high = fnum(obj.get("low")), fnum(obj.get("mid")), fnum(obj.get("high"))
        if low is None or mid is None or high is None:
            continue
        low_sum += low * w
        mid_sum += mid * w
        high_sum += high * w
        total += w
    if total <= 0:
        return None, None, None
    return low_sum / total, mid_sum / total, high_sum / total


def compute_reliability(
    profile: ValuationProfile,
    financials: dict,
    models: dict,
    included: list[str],
    excluded: list[dict],
    disp: float | None,
    specialized: bool,
) -> ReliabilityResult:
    if specialized:
        return ReliabilityResult(
            overall_confidence="SPECIALIZED",
            reliability_score=None,
            data_quality_score=None,
            model_count_total=len(models),
            model_count_valid=0,
            model_count_included=0,
            model_count_excluded=len(models),
            data_quality="n/a",
            valuation_stability="n/a",
            explanation="传统估值模型不适用，需要专项场景估值。",
        )
    score = 100
    penalties = []
    warnings = []
    model_warnings = []
    missing = 0
    if fnum(financials.get("forward_eps")) is None and fnum(financials.get("trailing_eps")) is None and fnum(financials.get("eps_proxy")) is None:
        missing += 10
        penalties.append({"code": "missing_eps", "delta": -10})
    if fnum(financials.get("canonical_shares")) is None and fnum(financials.get("shares")) is None:
        missing += 8
        penalties.append({"code": "missing_shares", "delta": -8})
    if profile.valuation_class != "bank" and fnum(financials.get("fcf")) is None:
        missing += 8
        penalties.append({"code": "missing_fcf", "delta": -8})
    if profile.valuation_class == "bank" and (
        not (fnum(financials.get("book_value_per_share")) or fnum(financials.get("tangible_book_value_per_share")))
        or not fnum(financials.get("roe"))
    ):
        missing += 15
        penalties.append({"code": "missing_bank_inputs", "delta": -15})
    _, _, is_proxy = _multiple_eps(financials)
    statement_proxy = _statement_derived_proxy_in_use(financials)
    if is_proxy:
        missing += 12
        penalties.append({"code": "eps_proxy_trailing", "delta": -12})
        warnings.append("forward_eps_unavailable")
        warnings.append("using_trailing_eps_proxy")
        if statement_proxy:
            missing += 8
            penalties.append({"code": "statement_derived_eps_proxy", "delta": -8})
            warnings.append("using_statement_derived_trailing_eps_proxy")
    missing = min(missing, 30)
    score -= missing
    data_quality_score = max(0, min(100, 100 - missing))
    if len(included) == 2:
        score -= 10
        penalties.append({"code": "only_two_models", "delta": -10})
    if disp is not None:
        if 0.15 <= disp < 0.30:
            score -= 10
            penalties.append({"code": "dispersion_moderate", "delta": -10})
        elif 0.30 <= disp < 0.50:
            score -= 20
            penalties.append({"code": "dispersion_high", "delta": -20})
        elif disp >= 0.50:
            score -= 35
            penalties.append({"code": "dispersion_very_high", "delta": -35})
            warnings.append("high_valuation_uncertainty")
    outlier_n = sum(1 for obj in models.values() if obj.get("outlier"))
    if outlier_n:
        delta = -10 * outlier_n
        score += delta
        penalties.append({"code": "outliers", "delta": delta, "count": outlier_n})
    dcf = models.get("normalized_fcf_dcf") or {}
    if dcf.get("applicable") is False and dcf.get("reason") in {
        "normalized_fcf_not_stable_enough",
        "fcf_latest_vs_normalized_extreme",
        "capex_or_fcf_distortion",
        "mostly_negative_fcf",
        "fcf_conversion_too_low",
        "fcf_conversion_unverified",
        "fcf_margin_not_stable",
        CURRENCY_MISMATCH_REASON,
    }:
        score -= 15
        penalties.append({"code": "fcf_unstable", "delta": -15})
        warnings.append("fcf_unstable")
    elif "high_terminal_value_share" in (dcf.get("warnings") or []) or dcf.get("reason") == "DCF_LOW_RELIABILITY":
        score -= 10
        penalties.append({"code": "dcf_terminal_heavy", "delta": -10})
        model_warnings.append("DCF_LOW_RELIABILITY" if dcf.get("reason") == "DCF_LOW_RELIABILITY" else "high_terminal_value_share")
    if profile.cyclicality == "high":
        hist = _positive_history_eps(financials)
        if len(hist) < 3:
            score -= 15
            penalties.append({"code": "cyclical_normalization_thin", "delta": -15})
            warnings.append("cyclical_normalization_data_insufficient")
    score = max(0, min(100, score))
    valid_n = sum(1 for obj in models.values() if _usable(obj))
    band = dispersion_band(disp)
    if len(included) < MIN_MODELS_FOR_BLEND:
        confidence = "UNAVAILABLE"
        reliability_score = None
    elif score >= 85 and (band in {None, "LOW"}) and len(included) >= 3:
        confidence = "HIGH"
        reliability_score = score
    elif score >= 65:
        confidence = "MEDIUM"
        reliability_score = score
    else:
        confidence = "LOW"
        reliability_score = score
    if profile.confidence_policy == "low" and confidence in {"HIGH", "MEDIUM"}:
        confidence = "LOW"
    if statement_proxy and profile.valuation_class in STATEMENT_PROXY_ALLOWED_LOW and confidence in {"HIGH", "MEDIUM"}:
        confidence = "LOW"
        warnings.append("statement_proxy_confidence_capped_low")
    if missing >= 20:
        data_quality = "poor"
    elif missing > 0 or is_proxy:
        data_quality = "partial"
    else:
        data_quality = "good"
    stability = {"LOW": "stable", "MODERATE": "moderate", "HIGH": "unstable", "VERY HIGH": "very_unstable"}.get(band or "", "unknown")
    explanation = (
        f"可靠性评分衡量数据完整性、模型一致性及适用性，不是股票评级。"
        f"有效模型 {len(included)}/{len(models)}，分歧 {f'{disp*100:.0f}%' if disp is not None else '—'}。"
    )
    return ReliabilityResult(
        overall_confidence=confidence,
        reliability_score=reliability_score,
        data_quality_score=data_quality_score,
        model_count_total=len(models),
        model_count_valid=valid_n,
        model_count_included=len(included),
        model_count_excluded=len(excluded),
        dispersion_pct=disp,
        dispersion_band=band,
        applicability_warnings=warnings,
        model_warnings=model_warnings,
        excluded_models=excluded,
        data_quality=data_quality,
        valuation_stability=stability,
        explanation=explanation,
        penalties=penalties,
    )


def primary_valuation_view(blend: dict | None) -> dict:
    blend = blend or {}
    conf = str(blend.get("confidence") or "").upper()
    low, mid, high = fnum(blend.get("fair_low")), fnum(blend.get("fair")), fnum(blend.get("fair_high"))
    if conf == "SPECIALIZED":
        return {"mode": "specialized", "primary": None, "label": "No reliable traditional fair value", "low": None, "mid": None, "high": None}
    if conf == "UNAVAILABLE" or blend.get("insufficient_models") or mid is None:
        return {"mode": "unavailable", "primary": None, "label": "Insufficient data", "low": None, "mid": None, "high": None}
    if conf == "LOW":
        return {"mode": "indicative_range", "primary": "range", "label": "Indicative valuation range", "low": low, "mid": mid, "high": high}
    if conf == "HIGH":
        return {"mode": "point", "primary": "mid", "label": "Fair Value", "low": low, "mid": mid, "high": high}
    return {"mode": "estimate", "primary": "mid", "label": "Fair value estimate", "low": low, "mid": mid, "high": high}


def _flag_outliers(models: dict[str, dict]) -> dict[str, dict]:
    candidates = {
        name: obj
        for name, obj in models.items()
        if obj and obj.get("applicable") is not False and obj.get("valid") is not False and not obj.get("outlier") and range_is_ordered(obj.get("low"), obj.get("mid"), obj.get("high"))
    }
    if len(candidates) < 3:
        return models
    mids = {name: fnum(obj.get("mid")) for name, obj in candidates.items()}
    mids = {k: v for k, v in mids.items() if v is not None}
    if len(mids) < 3:
        return models
    consensus = float(sorted(mids.values())[len(mids) // 2])
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
            models[name] = flagged
    return models


def _usable(model: dict | None) -> bool:
    return bool(model) and model.get("applicable") is not False and structural_valid(model)


def _canonical_blend(payload: dict) -> dict:
    mid = payload.get("fair")
    low = payload.get("fair_low")
    high = payload.get("fair_high")
    payload["blended_mid"] = mid
    payload["blended_low"] = low
    payload["blended_high"] = high
    payload["fair_value"] = mid
    payload["overall_confidence"] = payload.get("confidence")
    payload["included_models"] = list(payload.get("included") or [])
    payload["excluded_models"] = list(payload.get("excluded") or [])
    check_valuation_invariants(payload, strict=False)
    return payload


def check_valuation_invariants(blend: dict | None, *, strict: bool = False) -> list[str]:
    problems = []
    blend = blend or {}
    conf = str(blend.get("confidence") or blend.get("overall_confidence") or "").upper()
    included = list(blend.get("included") or blend.get("included_models") or [])
    mid = fnum(blend.get("blended_mid") if blend.get("blended_mid") is not None else blend.get("fair"))
    score = (blend.get("reliability") or {}).get("reliability_score")
    if score is None:
        score = blend.get("reliability_score")
    if conf == "UNAVAILABLE" and score is not None:
        problems.append("unavailable_has_reliability_score")
    if score is not None and float(score) >= 40 and len(included) >= MIN_MODELS_FOR_BLEND and conf == "UNAVAILABLE":
        problems.append("reliability_with_two_models_marked_unavailable")
    if mid is not None and conf in {"UNAVAILABLE", "SPECIALIZED"}:
        problems.append("blended_mid_incompatible_with_confidence")
    if conf == "SPECIALIZED" and mid is not None:
        problems.append("specialized_has_blended_mid")
    if len(included) >= MIN_MODELS_FOR_BLEND and mid is None and conf not in {"SPECIALIZED"} and not blend.get("reason"):
        problems.append("two_models_missing_blend_without_reason")
    if fnum(blend.get("fair")) != fnum(blend.get("fair_value")) and not (
        blend.get("fair") is None and blend.get("fair_value") is None
    ):
        problems.append("fair_alias_mismatch")
    for item in problems:
        logger.warning("valuation invariant ticker=%s issue=%s confidence=%s included=%s", blend.get("profile", {}).get("ticker") if isinstance(blend.get("profile"), dict) else None, item, conf, included)
        if strict:
            raise AssertionError(item)
    return problems


def check_model_input_invariants(models, included, pre_applicability):
    """A blocked gate cannot execute or enter the blend on the same input."""
    for name, applicable in pre_applicability.items():
        model = models.get(name) or {}
        if not applicable and (model.get('executed') or model.get('valid') or name in included):
            raise AssertionError('pre_valuation_applicability_violation:' + name)


def valuate(ticker: str, financials: dict, volatility: float | None = None, *, peer_result=None, peer_mode="diagnostic") -> dict:
    from financial_normalization import NormalizedFinancialInputs
    # Never normalize a supplied normalized snapshot again: doing so silently
    # resurrects EPS from historical statements AFTER the diagnostic gate.
    financials = financials or {}
    explicit_missing_eps = all(key in financials and financials[key] is None
                               for key in ('forward_eps', 'trailing_eps', 'eps_proxy'))
    financials = deepcopy(financials) if isinstance(financials, NormalizedFinancialInputs) else normalize_financials(financials)
    if explicit_missing_eps:
        # Also honor explicit absence in serialized/deserialized snapshots that
        # lost their Python type. Legacy raw inputs omitting proxy still resolve
        # their documented statement fallback before any applicability checks.
        for key in ('forward_eps', 'trailing_eps', 'eps_proxy'):
            financials[key] = None
            financials[key + '_source'] = None
            if key in (financials.get('provenance') or {}):
                financials['provenance'][key]['value'] = None
                financials['provenance'][key]['source'] = None
        financials['eps_proxy_currency_safe'] = False
    profile = build_profile(ticker, financials)
    spec = profile.spec
    specialized = spec.get("fair_policy") in {"specialized", "specialized_if_unprofitable"} and (
        spec.get("fair_policy") == "specialized" or profile.profitability_state == "unprofitable"
    )
    cycle = cycle_context(financials, profile) if profile.valuation_class == "cyclical_semiconductor" or profile.cyclicality == "high" else None
    models: dict[str, dict] = {}
    if specialized:
        overall = "SPECIALIZED"
        unsupported = _not_applicable("unsupported", "specialized_valuation_required", "传统估值模型不适用，需要专项场景估值。")
        reliability = compute_reliability(profile, financials, {"unsupported": unsupported}, [], [{"name": "unsupported", "reason": "specialized_model_required"}], None, True)
        return _canonical_blend({
            "fair": None,
            "fair_low": None,
            "fair_high": None,
            "included": [],
            "excluded": [{"name": "unsupported", "reason": "specialized_model_required"}],
            "weights_used": {},
            "insufficient_models": True,
            "specialized": True,
            "confidence": overall,
            "models": {"unsupported": unsupported},
            "model_list": [unsupported],
            "profile": profile.to_dict(),
            "model_version": MODEL_VERSION,
            "reason": "specialized_valuation_required",
            "warnings": ["specialized_valuation_required"],
            "reliability": reliability.to_dict(),
            "mos": None,
            "zones": None,
            "exit_zone": None,
            "cycle": cycle,
            "volatility_1y": volatility,
            "view": primary_valuation_view({"confidence": overall}),
        })

    pre_applicability = {}
    for model_id in profile.preferred_models:
        gate = APPLICABILITY_GATES.get(model_id)
        gate_result = gate(profile, financials) if gate else None
        pre_applicability[model_id] = gate_result[0] if gate_result else True
        models[model_id] = run_model(model_id, profile, financials, _gate_result=gate_result)
    for model_id in profile.excluded_models:
        if model_id not in models:
            models[model_id] = _not_applicable(model_id, "excluded_by_valuation_class", "该估值类型默认排除此模型。")

    models = _flag_outliers(models)
    # Optional independent model; diagnostic leaves the existing blend untouched.
    peer_weight = 0.0
    if peer_mode == "active" and peer_result is not None and peer_result.valid:
        from peer_comparable import as_blend_model, canonical, WEIGHTS
        if canonical(peer_result.target_ticker) == canonical(ticker) and peer_result.valuation_class == profile.valuation_class:
            peer_weight = WEIGHTS.get(profile.valuation_class, 0.0)
        if peer_weight:
            models["peer_comparable"] = as_blend_model(peer_result)
    for obj in models.values():
        obj["valuation_class"] = profile.valuation_class
        obj["model_applicability"] = obj.get("applicable") is not False
    included = []
    excluded = []
    weights = dict(profile.model_weights or {})
    if peer_weight:
        existing_weight = sum(float(weights.get(k) or 1.0) for k, obj in models.items()
                              if k != "peer_comparable" and k not in profile.excluded_models and _usable(obj))
        if existing_weight:
            weights["peer_comparable"] = existing_weight * peer_weight / (1 - peer_weight)
        else:
            models["peer_comparable"]["applicable"] = False
    weight_total = 0.0
    for model_id, obj in models.items():
        if model_id in profile.excluded_models or obj.get("applicable") is False:
            excluded.append({
                "name": model_id,
                "reason": obj.get("reason") or obj.get("applicability_reason") or "not_applicable",
                "outlier": bool(obj.get("outlier")),
                "executed": bool(obj.get("executed")),
                "why": obj.get("why_applicable"),
            })
            continue
        if _usable(obj):
            w = float(weights.get(model_id) or 0) or 1.0
            included.append(model_id)
            weight_total += w
        else:
            excluded.append({
                "name": model_id,
                "reason": obj.get("reason") or "invalid",
                "outlier": bool(obj.get("outlier")),
                "executed": bool(obj.get("executed")),
                "why": obj.get("why_applicable"),
            })

    check_model_input_invariants(models, included, pre_applicability)
    usable_pairs = [(name, models[name]) for name in included]
    disp = dispersion_pct([obj for _, obj in usable_pairs])
    reliability = compute_reliability(profile, financials, models, included, excluded, disp, False)
    confidence = reliability.overall_confidence

    # Class-level guard: statement-derived EPS alone cannot emit an official fair value
    # for growth/cyclical/fintech classes, even if non-EPS models (EV/revenue) look valid.
    if _blocks_official_statement_proxy(profile, financials):
        warnings = list(reliability.applicability_warnings)
        if FORWARD_AND_TRAILING_UNAVAILABLE not in warnings:
            warnings.append(FORWARD_AND_TRAILING_UNAVAILABLE)
        return _canonical_blend({
            "fair": None,
            "fair_low": None,
            "fair_high": None,
            "included": [],
            "excluded": excluded + [
                {
                    "name": model_id,
                    "reason": FORWARD_AND_TRAILING_UNAVAILABLE,
                    "outlier": bool((models.get(model_id) or {}).get("outlier")),
                    "executed": bool((models.get(model_id) or {}).get("executed")),
                    "why": "Forward 与 Yahoo trailing EPS 均缺失，statement-derived EPS 不能用于正式估值。",
                }
                for model_id in included
            ],
            "weights_used": {},
            "insufficient_models": True,
            "specialized": False,
            "confidence": "UNAVAILABLE",
            "models": models,
            "model_list": list(models.values()),
            "profile": profile.to_dict(),
            "model_version": MODEL_VERSION,
            "dispersion": disp,
            "reason": FORWARD_AND_TRAILING_UNAVAILABLE,
            "warnings": warnings,
            "reliability": {
                **reliability.to_dict(),
                "overall_confidence": "UNAVAILABLE",
                "reliability_score": None,
                "applicability_warnings": warnings,
            },
            "mos": None,
            "zones": None,
            "exit_zone": None,
            "cycle": cycle,
            "volatility_1y": volatility,
            "view": primary_valuation_view({"confidence": "UNAVAILABLE"}),
        })

    if len(included) < MIN_MODELS_FOR_BLEND or weight_total <= 0:
        return _canonical_blend({
            "fair": None,
            "fair_low": None,
            "fair_high": None,
            "included": included,
            "excluded": excluded,
            "weights_used": {},
            "insufficient_models": True,
            "specialized": False,
            "confidence": "UNAVAILABLE",
            "models": models,
            "model_list": list(models.values()),
            "profile": profile.to_dict(),
            "model_version": MODEL_VERSION,
            "dispersion": disp,
            "reason": "insufficient_valid_models",
            "warnings": reliability.applicability_warnings,
            "reliability": {**reliability.to_dict(), "overall_confidence": "UNAVAILABLE", "reliability_score": None},
            "mos": None,
            "zones": None,
            "exit_zone": None,
            "cycle": cycle,
            "volatility_1y": volatility,
            "view": primary_valuation_view({"confidence": "UNAVAILABLE"}),
        })

    weights_used = {name: (weights.get(name) or 1.0) / weight_total for name in included}
    low, mid, high = _blend_range(usable_pairs, weights_used)
    if low is None or mid is None or high is None or not (low <= mid <= high):
        return _canonical_blend({
            "fair": None,
            "fair_low": None,
            "fair_high": None,
            "included": included,
            "excluded": excluded,
            "weights_used": weights_used,
            "insufficient_models": True,
            "specialized": False,
            "confidence": "UNAVAILABLE",
            "models": models,
            "model_list": list(models.values()),
            "profile": profile.to_dict(),
            "model_version": MODEL_VERSION,
            "dispersion": disp,
            "reason": "unordered_blended_range",
            "warnings": reliability.applicability_warnings,
            "reliability": {**reliability.to_dict(), "overall_confidence": "UNAVAILABLE", "reliability_score": None},
            "mos": None,
            "zones": None,
            "exit_zone": None,
            "cycle": cycle,
            "volatility_1y": volatility,
            "view": primary_valuation_view({"confidence": "UNAVAILABLE"}),
        })

    mos = margin_of_safety_profile(confidence, disp, volatility, profile.cyclicality, profile.valuation_class)
    zones = dynamic_buy_zones(mid, mos, low_confidence=(confidence == "LOW"))
    exit_zone = build_exit_zone(
        blended_low=low,
        blended_mid=mid,
        blended_high=high,
        confidence=confidence,
        reliability_score=reliability.reliability_score,
        dispersion_pct=disp,
        volatility_1y=volatility,
        cyclicality=profile.cyclicality,
        valuation_class=profile.valuation_class,
    )
    warnings = list(reliability.applicability_warnings)
    if disp is not None and disp > 0.50:
        warnings.append("high_valuation_uncertainty")
    view = primary_valuation_view({"confidence": confidence, "fair": mid, "fair_low": low, "fair_high": high})
    return _canonical_blend({
        "fair": mid,
        "fair_low": low,
        "fair_high": high,
        "included": included,
        "excluded": excluded,
        "weights_used": weights_used,
        "insufficient_models": False,
        "specialized": False,
        "confidence": confidence,
        "models": models,
        "model_list": list(models.values()),
        "profile": profile.to_dict(),
        "model_version": MODEL_VERSION,
        "dispersion": disp,
        "reason": None,
        "warnings": warnings,
        "reliability": reliability.to_dict(),
        "mos": mos,
        "zones": zones,
        "exit_zone": exit_zone,
        "cycle": cycle,
        "volatility_1y": volatility,
        "view": view,
    })


def reliability_from_snapshot(snap: dict | None) -> dict | None:
    if not snap:
        return None
    raw = snap.get("raw") if isinstance(snap.get("raw"), dict) else {}
    payload = snap.get("reliability_json") or raw.get("reliability_json")
    if isinstance(payload, dict) and payload:
        return {"structural_governance": None, **payload}
    score = snap.get("reliability_score")
    if score is None:
        score = raw.get("reliability_score")
    disp = snap.get("dispersion_pct")
    if disp is None:
        disp = raw.get("dispersion_pct")
    if score is None and disp is None:
        return None
    return {
        "reliability_score": score,
        "dispersion_pct": disp,
        "overall_confidence": snap.get("confidence") or raw.get("confidence"),
        "from_columns": True,
    }


def is_legacy_snapshot(snap: dict | None) -> bool:
    if not snap:
        return False
    raw = snap.get("raw") if isinstance(snap.get("raw"), dict) else {}
    version = snap.get("model_version") or raw.get("model_version")
    if version in (None, "", "legacy"):
        return True
    missing_reliability = snap.get("reliability_score") is None and not (snap.get("reliability_json") or raw.get("reliability_json"))
    missing_range = snap.get("blended_low") is None and snap.get("blended_high") is None and raw.get("blended_low") is None
    return bool(missing_reliability and missing_range)


def exit_zone_from_snapshot(snap: dict | None) -> dict | None:
    """Restore saved exit / overvaluation profile. Never recomputes from live inputs."""
    if not snap:
        return None
    raw = snap.get("raw") if isinstance(snap.get("raw"), dict) else {}
    payload = snap.get("exit_zone_json")
    if not isinstance(payload, dict):
        payload = raw.get("exit_zone_json")
    if isinstance(payload, dict) and payload:
        out = dict(payload)
        for key in ("hold_upper_price", "overvalued_price", "trim_price", "extreme_price"):
            if key in snap and snap.get(key) is not None:
                out[key] = snap.get(key)
            elif out.get("display_mode") and out.get("display_mode") != "precise":
                # Explicit nulls for qualitative/unavailable snapshots.
                if key in snap and snap.get(key) is None:
                    out[key] = None
        for key in ("exit_confidence", "exit_display_mode", "exit_reliability_score"):
            col = key if key != "exit_display_mode" else "exit_display_mode"
            if snap.get(col) is not None:
                if key == "exit_display_mode":
                    out["display_mode"] = snap.get(col)
                else:
                    out[key] = snap.get(col)
        if snap.get("exit_reason_codes") is not None:
            out["reason_codes"] = snap.get("exit_reason_codes")
        elif raw.get("exit_reason_codes") is not None:
            out["reason_codes"] = raw.get("exit_reason_codes")
        if out.get("display_mode") is None and snap.get("exit_display_mode"):
            out["display_mode"] = snap.get("exit_display_mode")
        if out.get("exit_confidence") is None and snap.get("exit_confidence"):
            out["exit_confidence"] = snap.get("exit_confidence")
        return out
    hold = snap.get("hold_upper_price")
    over = snap.get("overvalued_price")
    trim = snap.get("trim_price")
    extreme = snap.get("extreme_price")
    display_mode = snap.get("exit_display_mode") or raw.get("exit_display_mode")
    exit_conf = snap.get("exit_confidence") or raw.get("exit_confidence")
    if hold is None and over is None and trim is None and extreme is None and not display_mode and not exit_conf:
        return None
    return {
        "hold_upper_price": hold,
        "overvalued_price": over,
        "trim_price": trim,
        "extreme_price": extreme,
        "display_mode": display_mode or ("precise" if trim is not None else "qualitative"),
        "exit_confidence": exit_conf,
        "exit_reliability_score": snap.get("exit_reliability_score") or raw.get("exit_reliability_score"),
        "reason_codes": snap.get("exit_reason_codes") or raw.get("exit_reason_codes") or [],
        "eligible_for_precise_exit": bool(trim is not None and extreme is not None),
        "from_columns": True,
    }


def reconstruct_blend_from_snapshot(snap: dict | None) -> dict | None:
    """Rebuild the valuation payload from a stored snapshot. Never recomputes live models."""
    if not snap:
        return None
    raw = snap.get("raw") if isinstance(snap.get("raw"), dict) else {}
    pe = snap.get("pe_model")
    dcf = snap.get("dcf_model")
    growth = snap.get("growth_model")
    fair = snap.get("fair_value")
    vclass = snap.get("valuation_class") or raw.get("valuation_class")
    models_json = snap.get("models_json") or raw.get("models_json") or {}
    if isinstance(models_json, dict):
        model_list = list(models_json.values())
        included = [key for key, obj in models_json.items() if obj]
    elif isinstance(models_json, list):
        model_list = models_json
        included = [obj.get("model_id") or obj.get("name") for obj in model_list if obj]
    else:
        model_list = [obj for obj in (pe, dcf, growth) if obj]
        included = []
        models_json = {}
    conf = snap.get("confidence") or raw.get("confidence")
    if isinstance(conf, str) and conf:
        conf = conf.upper()
    elif is_legacy_snapshot(snap):
        conf = None
    reliability = reliability_from_snapshot(snap) or {}
    fair_low = snap.get("blended_low") if snap.get("blended_low") is not None else raw.get("blended_low")
    fair_high = snap.get("blended_high") if snap.get("blended_high") is not None else raw.get("blended_high")
    version = snap.get("model_version") or raw.get("model_version") or "legacy"
    exit_zone = exit_zone_from_snapshot(snap)
    blend = {
        "fair": fair,
        "fair_low": fair_low,
        "fair_high": fair_high,
        "confidence": conf,
        "profile": {
            "valuation_class": vclass,
            "valuation_class_label": CLASS_LABELS.get(vclass, vclass),
        },
        "models": models_json if isinstance(models_json, dict) else {},
        "model_list": model_list,
        "model_version": version,
        "insufficient_models": fair is None,
        "specialized": str(conf or "").upper() == "SPECIALIZED",
        "included": included,
        "reliability": reliability,
        "structural_governance": reliability.get("structural_governance"),
        "reliability_governance_version": reliability.get("reliability_governance_version"),
        "dispersion": snap.get("dispersion_pct") if snap.get("dispersion_pct") is not None else raw.get("dispersion_pct"),
        "volatility_1y": snap.get("volatility_1y") if snap.get("volatility_1y") is not None else raw.get("volatility_1y"),
        "cycle": raw.get("cycle"),
        "exit_zone": exit_zone,
        "legacy": is_legacy_snapshot(snap),
        "snapshot_date": snap.get("snapshot_date"),
        "snapshot_created_at": snap.get("created_at") or snap.get("updated_at"),
    }
    view_source = dict(blend)
    if not view_source.get("confidence") and fair is not None:
        view_source["confidence"] = "MEDIUM"
    blend["view"] = primary_valuation_view(view_source)
    blend["blended_mid"] = fair
    blend["blended_low"] = fair_low
    blend["blended_high"] = fair_high
    blend["fair_value"] = fair
    blend["overall_confidence"] = conf
    blend["included_models"] = included
    blend["excluded_models"] = []
    return blend


def can_emit_buy_zones(blend: dict | None) -> bool:
    if not blend or not fnum(blend.get("fair")):
        return False
    if blend.get("insufficient_models") or blend.get("specialized"):
        return False
    if blend.get("confidence") in {"SPECIALIZED", "UNAVAILABLE"}:
        return False
    if len(blend.get("included") or []) < MIN_MODELS_FOR_BLEND:
        return False
    return True

