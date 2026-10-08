"""Read-only acquisition/normalization/valuation/calibration boundary observations."""
from copy import deepcopy

FIELDS={'forward_eps':'forwardEps','quote_currency':'currency','financial_currency':'financialCurrency'}


def snapshot_fundamentals(ticker):
    # Deliberately bypass Streamlit's legacy normalized cache for explicit admin runs.
    from fundamental_acquisition import flags
    from mag7_monitor import get_live_fundamentals
    if not flags().quality_cache:
        raise RuntimeError('Canonical quality-aware acquisition disabled')
    return get_live_fundamentals(ticker,force_refresh=True)


def identity(inputs):
    return {k:inputs.get(k) for k in ('input_batch_id','fundamentals_acquisition_id')}


def build_trace(ticker,acquired,valuation,calibration,*,batch_id=None):
    meta=acquired.get('acquisition_metadata') or {}
    raw=meta.get('production_raw_fields') or {}
    ids={'raw_acquisition':identity(meta),'normalized_input':identity(acquired),
         'valuation':identity(valuation),'calibration':identity(calibration)}
    divergent=[];missing=[]
    for key in ('input_batch_id','fundamentals_acquisition_id'):
        values=[value.get(key) for value in ids.values()]
        if key=='input_batch_id' and batch_id is not None:values.append(batch_id)
        if len(set(v for v in values if v is not None))>1:divergent.append(key)
        if any(v is None for v in values):missing.append(key)
    trace={'ticker':ticker,'input_batch_id':batch_id or acquired.get('input_batch_id'),
        'fundamentals_acquisition_id':acquired.get('fundamentals_acquisition_id'),
        'acquisition_health':meta.get('health_state','UNOBSERVED'),'stage_identities':ids,
        'primary_acquisition_health':(meta.get('primary_health') or {}).get('overall_state'),
        'canonical_entrypoint':'mag7_monitor.get_live_fundamentals → fundamental_acquisition.RAW_CACHE.get' if raw else 'UNOBSERVED',
        'divergence':'BATCH_ACQUISITION_DIVERGENCE' if divergent else 'UNOBSERVED' if missing else 'NONE',
        'identity_divergent_fields':divergent,'identity_missing_fields':missing,
        'fresh_recovery_used':meta.get('fresh_recovery_used'),
        'fresh_recovery_result':meta.get('fresh_recovery_result'),
        'accepted_recovery_payload_is_downstream_payload':None,
        'value_divergent_fields':[]}
    decision=meta.get('provider_recovery_decision') or {}
    trace.update(primary_exception_category=meta.get('primary_exception_category'),
        primary_exception_class=meta.get('primary_exception_class'),
        recovery_triggered=decision.get('triggered'),recovery_trigger_type=decision.get('trigger_type'),
        recovery_attempted=meta.get('fresh_recovery_attempted'),recovery_result=meta.get('fresh_recovery_result'),
        recovery_health=(meta.get('fresh_recovery_health') or {}).get('overall_state'),
        rate_limit_observed=meta.get('rate_limit_observed'),batch_cooldown_applied=meta.get('batch_cooldown_applied'),
        provider_recovery_status=meta.get('provider_recovery_status'),provider_attempts=deepcopy(meta.get('provider_attempts')),
        trace_acceptance_semantics='WIRING_CONSISTENCY_ONLY_NOT_PROVIDER_AVAILABILITY')
    for field in FIELDS:
        observation=raw.get(field) or {}
        provenance=(acquired.get('acquisition_provenance') or {}).get(field) or {}
        trace[field]={'raw':deepcopy(observation.get('value')),'raw_source':observation.get('source','UNOBSERVED'),
            'raw_provider_observed':field in raw,'acquisition_health':trace['acquisition_health'],
            'normalized':deepcopy(acquired.get(field)),
            'normalized_source':provenance.get('source') or acquired.get(field+'_source') or 'missing',
            'normalization_rule_source':acquired.get(field+'_source'),
            'valuation_input':deepcopy(valuation.get(field)),
            'calibration_input':deepcopy(calibration.get(field))}
        values=[acquired.get(field),valuation.get(field),calibration.get(field)]
        if field in raw:values.append(observation.get('value'))
        if field=='forward_eps':
            from valuation_primitives import fnum
            values=[fnum(v) for v in values]
        if any(v!=values[0] for v in values[1:]):trace['value_divergent_fields'].append(field)
    if meta.get('fresh_recovery_used') and len(raw)==len(FIELDS):
        trace['accepted_recovery_payload_is_downstream_payload']=not trace['value_divergent_fields']
    trace['acceptance_status']='FAIL' if divergent or ((trace['acquisition_health']=='HEALTHY' or meta.get('fresh_recovery_used')) and trace['value_divergent_fields']) else (
        'PASS' if not missing and len(raw)==len(FIELDS) else 'UNOBSERVED')
    return trace


def summary(stock):
    trace=stock.get('production_input_trace') or {}
    row={'ticker':stock['ticker'],'acquisition_health':trace.get('acquisition_health')}
    row.update(primary_health=trace.get('primary_acquisition_health'),
        primary_exception=trace.get('primary_exception_class'),rate_limited=trace.get('rate_limit_observed'),
        recovery_attempted=trace.get('recovery_attempted'),recovery_result=trace.get('recovery_result'),
        recovery_health=trace.get('recovery_health'),cooldown=trace.get('batch_cooldown_applied'),
        calibration_eligibility=stock.get('calibration_eligibility'),provider_recovery_status=trace.get('provider_recovery_status'))
    for field in FIELDS:
        values=trace.get(field) or {}
        row[field+'_raw']=values.get('raw')
    row.update(valuation_forward_eps=(trace.get('forward_eps') or {}).get('valuation_input'),
        calibration_forward_eps=(trace.get('forward_eps') or {}).get('calibration_input'),
        divergence=trace.get('divergence'),acceptance_status=trace.get('acceptance_status'))
    return row
