"""Read-only independent attempts using the exact engine code and captured data."""
from copy import deepcopy
from types import FunctionType
import peer_comparable as engine
from finnhub_service import number


def audit_multiples(ticker, financials, valuation_class, provider):
    group=engine.group_for(ticker,valuation_class)
    target=(provider.records.get(ticker,{}).get('basic_financials',{}).get('data') or {})
    orders=engine._multiple_order(group,valuation_class,target) if group else []
    attempts=[]
    for multiple in orders:
        # Private globals copy avoids patching shared production functions, even
        # during concurrent Streamlit sessions. Only the attempt list differs.
        namespace=dict(engine.calculate_peer_comparable.__globals__)
        namespace['_multiple_order']=lambda *args,m=multiple:[m]
        isolated=FunctionType(engine.calculate_peer_comparable.__code__,namespace,
                              engine.calculate_peer_comparable.__name__)
        isolated.__kwdefaults__=engine.calculate_peer_comparable.__kwdefaults__
        result=isolated(ticker,deepcopy(financials),valuation_class,provider=provider)
        key=engine.MULTIPLE_KEYS[multiple]
        rows=[]
        for peer in result.peers_considered:
            record=provider.records.get(peer,{})
            profile=record.get('company_profile',{})
            metrics=record.get('basic_financials',{})
            data=metrics.get('data') or {}
            growth,margin=number(data.get('Revenue Growth TTM YoY')),number(data.get('Operating Margin TTM'))
            tg,tm=number(target.get('Revenue Growth TTM YoY')),number(target.get('Operating Margin TTM'))
            value=number(data.get(key))
            reason=result.exclusion_reasons.get(peer)
            rows.append({'target_ticker':ticker,'multiple_type':multiple,'peer_ticker':peer,
                'profile_status':profile.get('status','NOT_REQUESTED'),'metric_status':metrics.get('status','NOT_REQUESTED'),
                'peer_multiple_value':value,'peer_growth':growth,'peer_margin':margin,
                'peer_market_cap':(profile.get('data') or {}).get('marketCapitalization') or data.get('Market Capitalization'),
                'target_growth':tg,'target_margin':tm,'multiple_available':value is not None and value>0,
                'growth_comparable':None if growth is None or tg is None else True,
                'margin_comparable':None if margin is None or tm is None else True,
                'outlier':reason=='peer_excluded_as_outlier','included':peer in result.peers_included,
                'exact_exclusion_reason':reason,**result.peer_scores.get(peer,{})})
        recorded=result.provenance.get('selection_attempts',[])
        target_safe=engine._metric_inputs(multiple,financials) is not None
        available=sum(r['multiple_available'] for r in rows)
        data_available=sum(all(result.provenance.get(r['peer_ticker'],{}).get(k)=='AVAILABLE'
            for k in ('profile_status','metrics_status')) and
            result.provenance.get(r['peer_ticker'],{}).get('peer_data_age_hours') is not None and
            -.1<=result.provenance[r['peer_ticker']]['peer_data_age_hours']<=engine.MAX_DATA_AGE_HOURS for r in rows)
        final=len(result.peers_included)
        comparable=final+sum(r['outlier'] for r in rows) if recorded and 'included' in recorded[-1] else None
        if result.eligibility=='NOT_ELIGIBLE':status='NOT_ELIGIBLE'
        elif result.valid:status='VALID'
        elif not target_safe or any(a.get('reason') in ('missing_or_unsafe_target_metric','stable_target_profitability_unverified') for a in recorded):status='TARGET_INPUT_UNSAFE'
        elif available<3:status='INSUFFICIENT_MULTIPLE_DATA'
        elif comparable is not None and comparable>=3 and final<3:status='OUTLIER_FILTER_TOO_AGGRESSIVE'
        else:status='INSUFFICIENT_COMPARABLE_PEERS'
        attempts.append({'Ticker':ticker,'Multiple':multiple,'Initial Peers':len(rows),
            'Data Available':data_available,'Multiple Available':available,'After Comparability':comparable,
            'After Outlier':final if comparable is not None else None,'Final Valid':final,
            'Status':status,'Main Failure Reason':'; '.join(a.get('reason','') for a in recorded if a.get('reason')) or
                '; '.join(f"{r['peer_ticker']}: {r['exact_exclusion_reason']}" for r in rows if r['exact_exclusion_reason']) or '; '.join(result.warnings),
            'peer_trace':rows,'engine_attempts':recorded,'warnings':result.warnings,
            'raw_peer_count':result.raw_peer_count,'effective_peer_count':result.effective_peer_count,
            'unweighted_q1':result.peer_q1,'unweighted_median':result.peer_median,'unweighted_q3':result.peer_q3,
            'weighted_low':result.weighted_low,'weighted_median':result.weighted_median,'weighted_high':result.weighted_high,
            'peer_low':result.low,'peer_mid':result.mid,'peer_high':result.high,'confidence':result.confidence})
    return {'control_flow':'continue on insufficient peers; break only on valid valuation; first successful multiple wins',
        'early_exit_on_first_eligible_multiple':False,
        'target_inputs':{k:financials.get(k) for k in ('forward_eps','forward_eps_source','ebitda','revenue','cash','debt','canonical_shares','canonical_shares_source','quote_currency','financial_currency')},
        'attempts':attempts,'alternate_multiple_succeeds':any(a['Status']=='VALID' for a in attempts[1:])}
