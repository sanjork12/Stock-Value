from dataclasses import asdict, dataclass, field
import math


def positive(value):
    try:
        value = float(value)
        return value if math.isfinite(value) and value > 0 else None
    except (TypeError, ValueError):
        return None


@dataclass
class MarketReferenceResult:
    ticker: str
    analyst_consensus_target: float | None = None
    analyst_target_low: float | None = None
    analyst_target_high: float | None = None
    analyst_count: int | None = None
    consensus_updated_at: str | None = None
    consensus_source: str | None = None
    current_forward_pe: float | None = None
    historical_pe_median_3y: float | None = None
    historical_pe_median_5y: float | None = None
    sector_forward_pe: float | None = None
    internal_fair_mid: float | None = None
    internal_implied_forward_pe: float | None = None
    internal_vs_consensus_pct: float | None = None
    sanity_status: str = 'NO_EXTERNAL_REFERENCE'
    sanity_warnings: list[str] = field(default_factory=list)


def build_market_reference(ticker, financials, internal_fair_mid, price=None):
    """Pure, independent comparison. Percent values use percentage points."""
    f = financials or {}
    r = MarketReferenceResult(ticker=ticker, internal_fair_mid=positive(internal_fair_mid))
    for key in ('analyst_consensus_target', 'analyst_target_low', 'analyst_target_high',
                'historical_pe_median_3y', 'historical_pe_median_5y', 'sector_forward_pe'):
        setattr(r, key, positive(f.get(key)))
    count = positive(f.get('analyst_count'))
    r.analyst_count = int(count) if count and count.is_integer() else None
    r.consensus_source = f.get('consensus_source')
    r.consensus_updated_at = f.get('consensus_updated_at')
    eps = positive(f.get('forward_eps'))
    r.current_forward_pe = positive(price) / eps if eps and positive(price) else positive(f.get('current_forward_pe'))
    if eps and r.internal_fair_mid:
        r.internal_implied_forward_pe = r.internal_fair_mid / eps
    if r.analyst_consensus_target and r.internal_fair_mid:
        r.internal_vs_consensus_pct = (r.internal_fair_mid / r.analyst_consensus_target - 1) * 100
        deviation = round(abs(r.internal_vs_consensus_pct), 10)
        r.sanity_status = 'NORMAL' if deviation < 20 else 'REVIEW' if deviation <= 35 else 'HIGH_DIVERGENCE'
        if r.sanity_status == 'HIGH_DIVERGENCE':
            r.sanity_warnings.append('内部模型与外部市场参考存在显著分歧；不代表内部模型错误。')
    return asdict(r)


def apply_reference_display_policy(result):
    """Add presentation fields without mutating the internal model or its zones."""
    legacy = str(result.get('confidence') or '').upper()
    mode = 'SPECIALIZED' if legacy == 'SPECIALIZED' else 'UNAVAILABLE' if legacy not in {'HIGH', 'MEDIUM', 'LOW'} else 'LOW_CONFIDENCE' if legacy == 'LOW' else 'STANDARD'
    result['valuation_mode'] = mode
    result['confidence'] = legacy if legacy in {'HIGH', 'MEDIUM', 'LOW'} else None
    result['overall_confidence'] = result['confidence']
    result['valuation_low'] = result.get('blended_low')
    result['valuation_mid'] = result.get('blended_mid')
    result['valuation_high'] = result.get('blended_high')
    ref = result.get('market_reference') or {}
    result['hide_precise_trading_zones'] = legacy == 'LOW' and ref.get('sanity_status') == 'HIGH_DIVERGENCE'
    if result['hide_precise_trading_zones']:
        result['recommendation'] = '模型分歧较大（低置信度）'
    return result
