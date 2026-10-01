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

MODEL_VERSION = "v4-sector-aware"
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


def _dispersion(models: list[dict]) -> float | None:
    mids = [fnum(m.get("mid")) for m in models if fnum(m.get("mid"))]
    if len(mids) < 2:
        return None
    median = float(sorted(mids)[len(mids) // 2])
    if median <= 0:
        return None
    return max(abs(m - median) / median for m in mids)


def valuate(ticker: str, financials: dict) -> dict:
    profile = build_profile(ticker, financials)
    spec = profile.spec
    specialized = spec.get("fair_policy") in {"specialized", "specialized_if_unprofitable"} and (
        spec.get("fair_policy") == "specialized" or profile.profitability_state == "unprofitable"
    )
    models: dict[str, dict] = {}
    if specialized:
        overall = "SPECIALIZED" if spec.get("fair_policy") == "specialized" or profile.profitability_state == "unprofitable" else "UNAVAILABLE"
        unsupported = model_result(
            "Unsupported / specialized",
            valid=False,
            reason="specialized_valuation_required",
            extra={
                "model_id": "unsupported",
                "applicable": False,
                "valuation_class": profile.valuation_class,
                "model_applicability": False,
            },
        )
        return {
            "fair": None,
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
        }

    for model_id in profile.preferred_models:
        runner = MODEL_RUNNERS.get(model_id)
        if not runner:
            continue
        models[model_id] = runner(profile, financials)
    for model_id in profile.excluded_models:
        if model_id not in models:
            models[model_id] = model_result(
                model_id,
                valid=False,
                reason="excluded_by_valuation_class",
                extra={"model_id": model_id, "applicable": False, "valuation_class": profile.valuation_class},
            )

    models = _flag_outliers(models)
    for obj in models.values():
        obj["valuation_class"] = profile.valuation_class
        obj["model_applicability"] = obj.get("applicable") is not False
    included = []
    excluded = []
    weighted_sum = 0.0
    weight_total = 0.0
    weights = profile.model_weights or {}
    for model_id, obj in models.items():
        if model_id in profile.excluded_models:
            excluded.append({"name": model_id, "reason": obj.get("reason") or "excluded_by_valuation_class", "outlier": bool(obj.get("outlier"))})
            continue
        if _usable(obj):
            w = float(weights.get(model_id) or 0)
            if w <= 0:
                w = 1.0
            included.append(model_id)
            weighted_sum += float(obj["mid"]) * w
            weight_total += w
        else:
            excluded.append({"name": model_id, "reason": obj.get("reason") or "invalid", "outlier": bool(obj.get("outlier"))})

    usable_models = [models[m] for m in included]
    disp = _dispersion(usable_models)
    policy = profile.confidence_policy
    if len(included) < MIN_MODELS_FOR_BLEND or weight_total <= 0:
        confidence = "SPECIALIZED" if policy == "specialized" else "UNAVAILABLE"
        if policy == "low" and len(included) == 1:
            confidence = "UNAVAILABLE"
        return {
            "fair": None,
            "included": included,
            "excluded": excluded,
            "weights_used": {},
            "insufficient_models": True,
            "specialized": policy == "specialized",
            "confidence": confidence,
            "models": models,
            "model_list": list(models.values()),
            "profile": profile.to_dict(),
            "model_version": MODEL_VERSION,
            "dispersion": disp,
            "reason": "insufficient_valid_models",
        }

    weights_used = {name: (weights.get(name) or 1.0) / weight_total for name in included}
    fair = weighted_sum / weight_total
    warnings = []
    if policy == "low":
        confidence = "LOW"
    elif policy == "specialized":
        confidence = "SPECIALIZED"
    elif len(included) >= 3 and (disp is None or disp <= 0.35) and policy == "medium_high":
        confidence = "HIGH"
    elif disp is not None and disp > 0.60:
        confidence = "LOW"
        warnings.append("high_valuation_uncertainty")
    else:
        confidence = "MEDIUM"
    if disp is not None and disp > 0.60:
        if "high_valuation_uncertainty" not in warnings:
            warnings.append("high_valuation_uncertainty")

    return {
        "fair": fair,
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
    }


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
