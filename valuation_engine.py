from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from mag7_monitor import (
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

MODEL_VERSION = "v4.1-reliability"
TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
COST_OF_EQUITY_DEFAULT = 0.10

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


def _profitability_state(financials: dict) -> str:
    eps = fnum(financials.get("forward_eps")) or fnum(financials.get("trailing_eps"))
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
    history = [fnum(row.get("eps")) for row in (financials.get("historical_eps") or [])]
    values = [v for v in history if v is not None and v > 0]
    if not values:
        return []
    median_hist = float(sorted(values)[len(values) // 2])
    ref = fnum(financials.get("trailing_eps")) or fnum(financials.get("forward_eps"))
    if ref and median_hist > 0:
        ratio = ref / median_hist
        if ratio > 5 or ratio < 0.2:
            return []
    return values


def _cycle_eps(financials: dict) -> tuple[float | None, str]:
    forward = fnum(financials.get("forward_eps"))
    trailing = fnum(financials.get("trailing_eps"))
    history = _positive_history_eps(financials)
    growth = fnum(financials.get("earnings_growth"))
    rebound = growth is not None and growth > 1
    if history:
        median_hist = float(sorted(history)[len(history) // 2])
        if forward and forward > 0:
            if rebound:
                return 0.35 * forward + 0.65 * median_hist, "rebound_capped_blend"
            return 0.40 * forward + 0.60 * median_hist, "forward_history_blend"
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
    trailing = fnum(financials.get("trailing_eps"))
    if trailing and trailing > 0:
        return trailing, "trailing_eps"
    return _cycle_eps(financials)


def model_forward_pe(profile: ValuationProfile, financials: dict) -> dict:
    spec = profile.spec
    eps = fnum(financials.get("forward_eps"))
    if eps is None or eps <= 0:
        return model_result("Forward P/E", valid=False, reason="missing_or_nonpositive_forward_eps", extra={"model_id": "forward_pe", "applicable": True})
    lo, hi = spec.get("pe_range") or (16, 22)
    return model_result(
        "Forward P/E",
        valid=True,
        low=eps * lo,
        mid=eps * (lo + hi) / 2,
        high=eps * hi,
        confidence="high" if profile.confidence_policy == "medium_high" else "medium",
        inputs={"forward_eps": eps, "pe_low": lo, "pe_high": hi},
        extra={"model_id": "forward_pe", "applicable": True, "valuation_class": profile.valuation_class},
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
    eps = fnum(financials.get("forward_eps"))
    if eps is None or eps <= 0:
        return model_result("Growth-adjusted P/E", valid=False, reason="missing_or_nonpositive_forward_eps", extra={"model_id": "growth_adjusted_pe", "applicable": True})
    g = _cap_growth(financials.get("earnings_growth"), spec, financials)
    floor = (spec.get("pe_range") or (10, 22))[0]
    fair_pe = max(floor, min(g * 100 * spec.get("peg_target", 1.5), spec.get("growth_pe_cap", 28)))
    return model_result(
        "Growth-adjusted P/E",
        valid=True,
        low=eps * fair_pe * 0.88,
        mid=eps * fair_pe,
        high=eps * fair_pe * 1.12,
        confidence="medium",
        inputs={"forward_eps": eps, "growth_used": g, "fair_pe": fair_pe, "peg_target": spec.get("peg_target")},
        extra={"model_id": "growth_adjusted_pe", "applicable": True, "fair_pe": fair_pe, "growth_used": g, "valuation_class": profile.valuation_class},
    )


def model_normalized_fcf_dcf(profile: ValuationProfile, financials: dict) -> dict:
    spec = profile.spec
    result = dcf_model(
        profile.ticker,
        financials.get("fcf"),
        financials.get("shares"),
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
        },
    )
    result["name"] = "Normalized FCF DCF"
    result["model_id"] = "normalized_fcf_dcf"
    result["applicable"] = True
    result["valuation_class"] = profile.valuation_class
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
    shares = fnum(financials.get("shares"))
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
        inputs={"ebitda": ebitda, "multiple_low": lo, "multiple_high": hi, "cash": cash, "debt": debt, "shares": shares},
        extra={"model_id": "ev_ebitda", "applicable": True, "valuation_class": profile.valuation_class},
    )


def model_revenue_multiple(profile: ValuationProfile, financials: dict) -> dict:
    spec = profile.spec
    revenue = fnum(financials.get("revenue"))
    shares = fnum(financials.get("shares"))
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
        inputs={"revenue": revenue, "multiple_low": lo, "multiple_high": hi, "shares": shares},
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


@dataclass
class ReliabilityResult:
    overall_confidence: str
    reliability_score: int | None
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
    eps = fnum(financials.get("forward_eps"))
    trailing = fnum(financials.get("trailing_eps"))
    diag = {"forward_eps": eps, "trailing_eps": trailing}
    if eps is None or eps <= 0:
        return False, "missing_or_nonpositive_forward_eps", "Forward EPS 缺失或非正，Forward P/E 不适用。", diag
    if eps < 0.05:
        return False, "forward_eps_near_zero", "Forward EPS 接近 0，倍数估值不稳定。", diag
    if trailing and trailing > 0 and eps / trailing > 5:
        return False, "eps_forecast_anomalous", "Forward EPS 相对 trailing 变化过大，预测可能异常。", diag
    why = "盈利为正，forward EPS 数据完整。"
    if trailing and trailing > 0 and abs(eps / trailing - 1) > 1:
        why += " 预测变化较大，已降低该模型置信度。"
    return True, "applicable", why, diag


def check_normalized_pe_applicable(profile: ValuationProfile, financials: dict) -> tuple[bool, str, str, dict]:
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
    eps = fnum(financials.get("forward_eps"))
    if eps is None or eps <= 0:
        return False, "missing_or_nonpositive_forward_eps", "缺少正的 Forward EPS，Growth 模型不适用。", {}
    live = fnum(financials.get("earnings_growth"))
    why = "使用规范化远期增长率，而非单年爆发增长。"
    if live is not None and live > 1:
        why = "当前 EPS 增长属于 rebound/cycle effect，已忽略单年增速，改用 normalized growth。"
    return True, "applicable", why, {"earnings_growth": live}


def check_dcf_applicable(profile: ValuationProfile, financials: dict) -> tuple[bool, str, str, dict]:
    annual, observations = _fcf_observations(financials)
    norm = fnum(financials.get("fcf"))
    latest = annual[0] if annual else fnum(financials.get("fcf_ttm_info"))
    diag = {
        "observation_count": len(observations),
        "annual_count": len(annual),
        "normalized_fcf": norm,
        "latest_fcf": latest,
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
    if latest is not None and norm:
        gap = abs(latest - norm) / abs(norm)
        diag["latest_vs_normalized"] = gap
        if gap > 2.0:
            return False, "fcf_latest_vs_normalized_extreme", "最新 FCF 与 normalized FCF 差异过大，可能存在 CapEx 扭曲。", diag
        if latest < 0.5 * abs(norm) and norm > 0:
            return False, "capex_or_fcf_distortion", "最新 FCF 显著低于 normalized FCF，CapEx/FCF 扭曲过高。", diag
    shares = fnum(financials.get("shares"))
    eps = fnum(financials.get("forward_eps")) or fnum(financials.get("trailing_eps"))
    if shares and shares > 0 and eps and eps > 0 and norm:
        conversion = (norm / shares) / eps
        diag["fcf_eps_conversion"] = conversion
        if conversion < 0.25:
            return False, "fcf_conversion_too_low", "Normalized FCF 相对 EPS 过低，DCF 不能可靠代表盈利能力。", diag
    return True, "applicable", "有足够年度 FCF 且波动可接受。", diag


def check_pb_roe_applicable(profile: ValuationProfile, financials: dict) -> tuple[bool, str, str, dict]:
    bvps = fnum(financials.get("tangible_book_value_per_share")) or fnum(financials.get("book_value_per_share"))
    roe = fnum(financials.get("roe"))
    if bvps is None or bvps <= 0 or roe is None or roe <= 0:
        return False, "missing_book_or_roe", "缺少账面价值或 ROE，银行估值模型不适用。", {"bvps": bvps, "roe": roe}
    return True, "applicable", "账面价值与 ROE 数据完整。", {"bvps": bvps, "roe": roe}


def check_residual_income_applicable(profile: ValuationProfile, financials: dict) -> tuple[bool, str, str, dict]:
    return check_pb_roe_applicable(profile, financials)


def check_ev_ebitda_applicable(profile: ValuationProfile, financials: dict) -> tuple[bool, str, str, dict]:
    ebitda = fnum(financials.get("ebitda"))
    shares = fnum(financials.get("shares"))
    if ebitda is None or ebitda <= 0 or shares is None or shares <= 0:
        return False, "missing_ebitda_or_shares", "缺少正的 EBITDA 或股本。", {"ebitda": ebitda, "shares": shares}
    return True, "applicable", "EBITDA 与股本数据完整。", {"ebitda": ebitda, "shares": shares}


def check_revenue_applicable(profile: ValuationProfile, financials: dict) -> tuple[bool, str, str, dict]:
    revenue = fnum(financials.get("revenue"))
    shares = fnum(financials.get("shares"))
    if revenue is None or revenue <= 0 or shares is None or shares <= 0:
        return False, "missing_revenue_or_shares", "缺少收入或股本。", {"revenue": revenue, "shares": shares}
    return True, "applicable", "收入与股本数据完整。", {"revenue": revenue, "shares": shares}


def check_cycle_earnings_applicable(profile: ValuationProfile, financials: dict) -> tuple[bool, str, str, dict]:
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


def run_model(model_id: str, profile: ValuationProfile, financials: dict) -> dict:
    gate = APPLICABILITY_GATES.get(model_id)
    why = ""
    if gate:
        ok, reason, why, diag = gate(profile, financials)
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
    if fnum(financials.get("forward_eps")) is None and fnum(financials.get("trailing_eps")) is None:
        missing += 10
        penalties.append({"code": "missing_eps", "delta": -10})
    if fnum(financials.get("shares")) is None:
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
    missing = min(missing, 25)
    score -= missing
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
    elif score >= 85 and (band in {None, "LOW"}) and len(included) >= 3:
        confidence = "HIGH"
    elif score >= 65:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"
    if profile.confidence_policy == "low" and confidence in {"HIGH", "MEDIUM"}:
        confidence = "LOW"
    if missing >= 20:
        data_quality = "poor"
    elif missing > 0:
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
        reliability_score=score,
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


def valuate(ticker: str, financials: dict, volatility: float | None = None) -> dict:
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
        return {
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
            "cycle": cycle,
            "volatility_1y": volatility,
            "view": primary_valuation_view({"confidence": overall}),
        }

    for model_id in profile.preferred_models:
        models[model_id] = run_model(model_id, profile, financials)
    for model_id in profile.excluded_models:
        if model_id not in models:
            models[model_id] = _not_applicable(model_id, "excluded_by_valuation_class", "该估值类型默认排除此模型。")

    models = _flag_outliers(models)
    for obj in models.values():
        obj["valuation_class"] = profile.valuation_class
        obj["model_applicability"] = obj.get("applicable") is not False
    included = []
    excluded = []
    weights = profile.model_weights or {}
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

    usable_pairs = [(name, models[name]) for name in included]
    disp = dispersion_pct([obj for _, obj in usable_pairs])
    reliability = compute_reliability(profile, financials, models, included, excluded, disp, False)
    confidence = reliability.overall_confidence

    if len(included) < MIN_MODELS_FOR_BLEND or weight_total <= 0:
        return {
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
            "reliability": {**reliability.to_dict(), "overall_confidence": "UNAVAILABLE"},
            "mos": None,
            "zones": None,
            "cycle": cycle,
            "volatility_1y": volatility,
            "view": primary_valuation_view({"confidence": "UNAVAILABLE"}),
        }

    weights_used = {name: (weights.get(name) or 1.0) / weight_total for name in included}
    low, mid, high = _blend_range(usable_pairs, weights_used)
    if low is None or mid is None or high is None or not (low <= mid <= high):
        return {
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
            "reliability": {**reliability.to_dict(), "overall_confidence": "UNAVAILABLE"},
            "mos": None,
            "zones": None,
            "cycle": cycle,
            "volatility_1y": volatility,
            "view": primary_valuation_view({"confidence": "UNAVAILABLE"}),
        }

    mos = margin_of_safety_profile(confidence, disp, volatility, profile.cyclicality, profile.valuation_class)
    zones = dynamic_buy_zones(mid, mos, low_confidence=(confidence == "LOW"))
    warnings = list(reliability.applicability_warnings)
    if disp is not None and disp > 0.50:
        warnings.append("high_valuation_uncertainty")
    view = primary_valuation_view({"confidence": confidence, "fair": mid, "fair_low": low, "fair_high": high})
    return {
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
        "cycle": cycle,
        "volatility_1y": volatility,
        "view": view,
    }


def reliability_from_snapshot(snap: dict | None) -> dict | None:
    if not snap:
        return None
    raw = snap.get("raw") if isinstance(snap.get("raw"), dict) else {}
    payload = snap.get("reliability_json") or raw.get("reliability_json")
    if isinstance(payload, dict) and payload:
        return payload
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
        "dispersion": snap.get("dispersion_pct") if snap.get("dispersion_pct") is not None else raw.get("dispersion_pct"),
        "volatility_1y": snap.get("volatility_1y") if snap.get("volatility_1y") is not None else raw.get("volatility_1y"),
        "cycle": raw.get("cycle"),
        "legacy": is_legacy_snapshot(snap),
        "snapshot_date": snap.get("snapshot_date"),
        "snapshot_created_at": snap.get("created_at") or snap.get("updated_at"),
    }
    view_source = dict(blend)
    if not view_source.get("confidence") and fair is not None:
        view_source["confidence"] = "MEDIUM"
    blend["view"] = primary_valuation_view(view_source)
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

