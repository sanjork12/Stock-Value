"""Read-only calibration data-state governance; not a valuation gate."""
from datetime import datetime,timezone,timedelta
import re
from financial_normalization import is_statement_eps_source
from valuation_primitives import fnum

REFERENCE_MAX_AGE=timedelta(hours=24)


def known_currency(value):
    return isinstance(value,str) and re.fullmatch('[A-Z]{3}',value) is not None


def positive(value):
    number=fnum(value)
    return number is not None and number>0


def reference_snapshot(row,ticker,now=None):
    """Project existing raw.last_reliable only. Never create/update a snapshot."""
    saved=((row or {}).get('raw') or {}).get('last_reliable')
    if not isinstance(saved,dict) or saved.get('ticker')!=ticker:return None
    context=saved.get('context') or {};inputs=saved.get('inputs') or {};valuation=saved.get('valuation') or {}
    model_inputs=((valuation.get('blend') or {}).get('models',{}).get('forward_pe',{}).get('inputs') or {})
    source=inputs.get('forward_eps_source')
    if source is None and positive(model_inputs.get('forward_eps')):source=model_inputs.get('eps_source')
    stamp=saved.get('calculated_at')
    try:
        when=datetime.fromisoformat(str(stamp).replace('Z','+00:00'))
        age=(now or datetime.now(timezone.utc))-when if when.tzinfo else None
        fresh=age is not None and timedelta(0)<=age<REFERENCE_MAX_AGE
    except (ValueError,TypeError):fresh=False
    ref={'calculated_at':stamp,'source_status':saved.get('source_status'),
        'fair':valuation.get('fair_value'),'confidence':valuation.get('confidence'),
        'forward_eps':inputs.get('forward_eps'),'forward_eps_source':source,
        **{key:context.get(key) for key in ('quote_currency','financial_currency','canonical_shares',
            'canonical_shares_source','split_context_known','last_split_date','last_split_factor')},
        'reference_snapshot_used_for_calibration':False,'fresh_within_24h':fresh}
    ref['healthy_reference']=(fresh and ref['source_status']=='live' and positive(ref['fair'])
        and positive(ref['forward_eps']) and not is_statement_eps_source(source)
        and known_currency(ref['quote_currency']) and known_currency(ref['financial_currency'])
        and ref['quote_currency']==ref['financial_currency']
        and positive(ref['canonical_shares']) and bool(ref['canonical_shares_source'])
        and ref['split_context_known'] is True and ref['last_split_date'] is not None
        and ref['last_split_factor'] is not None)
    return ref


def calibration_eligibility(stock,reference=None):
    f=stock.get('normalized_inputs',stock.get('financials')) or {}
    blend=stock.get('live_blend',stock.get('blend')) or {}
    included=blend.get('included') or []
    models=blend.get('models') or {}
    reasons=[]
    unavailable=(not positive(stock.get('production_analysis_fair')) or not positive(blend.get('fair'))
                 or not included)
    if unavailable:reasons.append('current_live_valuation_unavailable')
    if len(included)<2:reasons.append('fewer_than_two_included_production_models')
    eps_models=[models[name] for name in included if name in ('forward_pe','growth_adjusted_pe','normalized_pe','normalized_cycle_earnings') and name in models]
    proxy=(fnum(f.get('forward_eps')) is None and any(
        model.get('uses_proxy') or model.get('eps_proxy') or (model.get('inputs') or {}).get('uses_proxy')
        or (model.get('inputs') or {}).get('eps_proxy')
        or is_statement_eps_source((model.get('inputs') or {}).get('eps_source')) for model in eps_models))
    if proxy:reasons.append('proxy_only_eps_regime_forward_eps_missing')
    currency_unknown=not known_currency(f.get('quote_currency')) or not known_currency(f.get('financial_currency'))
    mismatch=f.get('currency_mismatch') is True or (not currency_unknown and f['quote_currency']!=f['financial_currency'])
    if not known_currency(f.get('quote_currency')):reasons.append('quote_currency_unknown')
    if not known_currency(f.get('financial_currency')):reasons.append('financial_currency_unknown')
    if mismatch:reasons.append('currency_context_mismatch')
    missing=[]
    if reference and reference.get('healthy_reference'):
        if fnum(f.get('forward_eps')) is None:missing.append('forward_eps')
        for key in ('quote_currency','financial_currency'):
            if not known_currency(f.get(key)):missing.append(key)
        if not positive(f.get('canonical_shares')):missing.append('canonical_shares')
        if not f.get('canonical_shares_source'):missing.append('canonical_shares_source')
        if f.get('split_context_known') is not True:missing.append('split_context')
    transient=bool(missing)
    if transient:reasons.extend('healthy_reference_present_current_missing_'+key for key in missing)
    path_ok=(stock.get('source_status')=='live' and stock.get('input_blend_alignment')=='SAME_LIVE_EXECUTION'
             and stock.get('capture_status')=='COMPLETE')
    if not path_ok:reasons.append('not_complete_same_execution_live_input_and_blend')
    if stock.get('peer_in_blend'):reasons.append('peer_in_internal_blend')
    # All reasons survive; main status precedence is explicit, not dependent
    # on iteration order. This never changes production applicability/results.
    if unavailable or len(included)<2:status='INELIGIBLE_UNAVAILABLE_VALUATION'
    elif transient:status='INELIGIBLE_TRANSIENT_INPUT_DEGRADATION'
    elif proxy:status='INELIGIBLE_PROXY_ONLY_VALUATION'
    elif currency_unknown or mismatch:status='INELIGIBLE_CURRENCY_CONTEXT_UNKNOWN'
    elif not path_ok or stock.get('peer_in_blend'):status='INELIGIBLE_TRANSIENT_INPUT_DEGRADATION'
    else:status='ELIGIBLE'
    return {'calibration_eligibility':status,'calibration_eligibility_reasons':reasons,
            'transient_input_degradation':transient,'reference_snapshot':reference,
            'reference_snapshot_used_for_calibration':False}


def batch_eligibility(stocks,required):
    by_ticker={stock['ticker']:stock for stock in stocks}
    missing=[ticker for ticker in required if ticker not in by_ticker]
    ineligible=[ticker for ticker in required if ticker not in by_ticker or by_ticker[ticker].get('calibration_eligibility')!='ELIGIBLE']
    reasons=[{'ticker':ticker,'status':by_ticker.get(ticker,{}).get('calibration_eligibility','MISSING_REQUIRED_TICKER'),
        'reasons':by_ticker.get(ticker,{}).get('calibration_eligibility_reasons',['missing_required_ticker'])} for ticker in ineligible]
    if len(stocks)!=len(required) or len(by_ticker)!=len(stocks):
        reasons.append({'ticker':None,'status':'INVALID_BATCH_COMPOSITION','reasons':['unexpected_or_duplicate_tickers']})
    return {'batch_calibration_eligibility':'ELIGIBLE' if not ineligible and not reasons else 'INELIGIBLE',
            'ineligible_tickers':ineligible,'batch_reasons':reasons}
