"""Display-only last reliable valuation, stored in existing snapshot raw JSON.

Never calls the valuation engine or accepts peer/reference results as evidence.
Unknown context fails closed. No credentials or arbitrary result keys are stored.
"""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import hashlib
import json
import math


DISPLAY_FIELDS = (
    'fair', 'fair_value', 'fair_low', 'fair_high', 'blended_low', 'blended_mid',
    'blended_high', 'valuation_mode', 'confidence', 'reliability_score',
    'dispersion_pct', 'zones', 'exit_zone', 'exit_confidence', 'exit_display_mode',
    'exit_reliability_score', 'exit_reason_codes', 'blend', 'pe', 'dcf', 'growth',
    'recommendation', 'state', 'cycle', 'model_version', 'valuation_class',
    'overall_confidence', 'valuation_low', 'valuation_mid', 'valuation_high',
    'hide_precise_trading_zones',
)
# Combined missing/nonpositive reasons require positive prior and absent current
# inputs; negative/zero values are deliberately not treated as missing.
MISSING_INPUTS = {
    'insufficient_fcf_history': ('fcf_history',),
    'missing_book_or_roe': ('book_value_per_share', 'tangible_book_value_per_share', 'roe'),
    'missing_ebitda_or_shares': ('ebitda', 'canonical_shares'),
    'missing_revenue_or_shares': ('revenue', 'canonical_shares'),
}
INPUT_FIELDS = tuple(sorted({k for keys in MISSING_INPUTS.values() for k in keys}
                            | {'forward_eps', 'trailing_eps', 'normalized_fcf', 'cash', 'debt',
                               'earnings_growth', 'revenue_growth', 'eps_proxy'}))


def _positive(value):
    return isinstance(value, (int, float)) and math.isfinite(value) and value > 0


def _context(result):
    f = result.get('financials') or {}
    return {k: f.get(k) for k in (
        'quote_currency', 'financial_currency', 'canonical_shares',
        'canonical_shares_source', 'last_split_date', 'last_split_factor',
        'split_context_known',
    )} | {'ticker': result.get('ticker'), 'valuation_class': result.get('valuation_class'),
         'model_version': result.get('model_version')}


def _inputs(result):
    f = result.get('financials') or {}
    from valuation_engine import _fcf_observations
    inputs = {k: deepcopy(f.get(k)) for k in INPUT_FIELDS}
    inputs['fcf_history'] = list(_fcf_observations(f)[1])
    inputs['normalized_fcf'] = f.get('fcf')
    return inputs


def reliable_snapshot(result, now=None):
    """A live, already accepted internal valuation; no new reliability threshold."""
    if result.get('source_status') == 'cached_last_reliable':
        return None
    if (result.get('peer_diagnostics') or {}).get('mode') == 'active':
        return None
    if result.get('valuation_mode') not in ('STANDARD', 'LOW_CONFIDENCE'):
        return None
    bounds = [result.get(k) for k in ('blended_low', 'fair_value', 'blended_high')]
    if not all(_positive(x) for x in bounds) or bounds != sorted(bounds):
        return None
    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    context, inputs = _context(result), _inputs(result)
    fingerprint = hashlib.sha256(json.dumps(
        {'context': context, 'inputs': inputs}, sort_keys=True, allow_nan=False
    ).encode()).hexdigest()
    return {'ticker': result['ticker'], 'calculated_at': stamp,
            'input_fingerprint': fingerprint, 'source_status': 'live',
            'context': context, 'inputs': inputs,
            'valuation': {k: deepcopy(result.get(k)) for k in DISPLAY_FIELDS},
            'buy_zones': deepcopy(result.get('zones')),
            'exit_zones': deepcopy(result.get('exit_zone'))}


def _context_matches(current, saved):
    if current.get('quote_currency') != current.get('financial_currency'):
        return False
    for key in ('ticker', 'valuation_class', 'model_version', 'quote_currency',
                'financial_currency', 'canonical_shares_source'):
        if not current.get(key) or current[key] != saved.get(key):
            return False
    if not current.get('split_context_known') or not saved.get('split_context_known'):
        return False
    if any(current.get(k) != saved.get(k) for k in ('last_split_date', 'last_split_factor')):
        return False
    a, b = current.get('canonical_shares'), saved.get('canonical_shares')
    return _positive(a) and _positive(b) and abs(a / b - 1) <= 0.10


def _transient_missing(result, saved):
    f, blend = result.get('financials') or {}, result.get('blend') or {}
    if (result.get('peer_diagnostics') or {}).get('mode') == 'active':
        return False
    if f.get('currency_mismatch') or blend.get('reason') != 'insufficient_valid_models':
        return False
    # Guard refusal, outliers, failed execution and economic invalidity cannot be
    # relabeled as provider outages. Only prior-valid models losing data qualify.
    prior_models = (saved.get('valuation', {}).get('blend') or {}).get('models') or {}
    lost = False
    for name, model in (blend.get('models') or {}).items():
        if name == 'peer_comparable':
            continue
        if model.get('valid') and model.get('applicable') is not False and not model.get('outlier'):
            continue
        reason = model.get('reason') or model.get('applicability_reason')
        if reason == 'excluded_by_valuation_class':
            continue
        prior = prior_models.get(name) or {}
        # Existing economic/guard failures are not evidence of an outage.
        if not prior.get('valid'):
            return False
        if model.get('outlier') or reason not in MISSING_INPUTS:
            return False
        vanished = False
        for key in MISSING_INPUTS[reason]:
            value, old = _inputs(result).get(key), saved.get('inputs', {}).get(key)
            if key == 'fcf_history':
                if any(not _positive(x) for x in (value or [])):
                    return False
                vanished |= isinstance(old, list) and len(old) >= 3 and len(value or []) < 3
            else:
                raw = ((f.get('normalized') or {}).get(key) or {}).get('value')
                if value is not None and not _positive(value):
                    return False
                if raw is not None and not _positive(raw):
                    return False
                vanished |= value is None and _positive(old)
        if not vanished:
            return False
        lost = True
    return lost


def apply_last_reliable(result, row, now=None):
    """Return a display copy only. Current financials and peer sidecars survive."""
    live = deepcopy(result)
    live['source_status'] = 'live'
    if result.get('fair_value') is not None or result.get('valuation_mode') != 'UNAVAILABLE':
        return live
    saved = ((row or {}).get('raw') or {}).get('last_reliable')
    if not isinstance(saved, dict) or saved.get('source_status') != 'live':
        return live
    try:
        stamp = datetime.fromisoformat(saved['calculated_at'])
        if stamp.tzinfo is None:
            return live
        age = (now or datetime.now(timezone.utc)) - stamp
        if not timedelta(0) <= age < timedelta(hours=24):
            return live
        if not _context_matches(_context(result), saved.get('context') or {}):
            return live
        if not _transient_missing(result, saved):
            return live
        # Validate cached payload as strictly as live snapshots before display.
        valuation = saved.get('valuation') or {}
        bounds = [valuation.get(k) for k in ('blended_low', 'fair_value', 'blended_high')]
        if (valuation.get('valuation_mode') not in ('STANDARD', 'LOW_CONFIDENCE')
                or not all(_positive(x) for x in bounds) or bounds != sorted(bounds)):
            return live
    except (TypeError, ValueError, KeyError, OverflowError):
        return live
    live['current_live_valuation'] = {k: deepcopy(result.get(k)) for k in DISPLAY_FIELDS}
    live.update(deepcopy(saved['valuation']))
    live.update(source_status='cached_last_reliable',
                stale_reason='current_financial_input_incomplete',
                calculated_at=saved['calculated_at'], input_fingerprint=saved['input_fingerprint'])
    return live


def resolve_live_result(result, load_snapshot, save_live):
    """Storage callbacks keep existing ownership/RLS checks at the app boundary."""
    live = deepcopy(result)
    live['source_status'] = 'live'
    if reliable_snapshot(live) is not None:
        save_live(live)
        return live
    return apply_last_reliable(live, load_snapshot())


def render_cache_notice(st, result):
    if result.get('source_status') == 'cached_last_reliable':
        st.warning(f"{result.get('ticker', '')}：实时财务输入暂不完整，当前显示最近一次可靠估值。")
        st.caption(f"上次可靠更新：{result.get('calculated_at')}（UTC）")
