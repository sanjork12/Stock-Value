"""V4.8 independent-family sandbox. No production registration, execution or IO."""
from copy import deepcopy
from statistics import median
from math import isclose
from capital_structure_overlay import valid_range,capital_overlay
from experimental_family_blend import family_blend_experiment
from model_family_governance import governance_audit
from valuation_primitives import fnum

DIAGNOSTIC_FAMILY_MAP={'ev_ebitda':'ENTERPRISE_MULTIPLE','ev_revenue':'ENTERPRISE_MULTIPLE'}
DIAGNOSTIC_BASE_WEIGHTS={'ev_ebitda':.5,'ev_revenue':.5}
CONSISTENT_SPREAD_PCT=20.
MODERATE_SPREAD_PCT=40.
EARNINGS_DIFFERENCE_THRESHOLDS=(10.,25.,50.)
STRONG_CANDIDATE_DIFFERENCE_PCT=25.


def at_most(value,limit):
    return value<=limit or isclose(value,limit,rel_tol=0,abs_tol=1e-9)


def enterprise_model(name,basis,shares,cash,debt,currency_safe,bounds,global_reasons):
    reasons=list(global_reasons)
    if basis is None or basis<=0:reasons.append('missing_or_nonpositive_'+('ebitda' if name=='ev_ebitda' else 'revenue'))
    if shares is None or shares<=0:reasons.append('missing_or_nonpositive_canonical_shares')
    if cash is None or debt is None or cash<0 or debt<0:reasons.append('missing_or_negative_cash_debt')
    if not currency_safe:reasons.append('capital_currency_unsafe_or_unknown')
    if bounds is None:reasons.append('missing_or_invalid_captured_class_range')
    model={'model_name':name,'model_family':DIAGNOSTIC_FAMILY_MAP[name],
        'experimental_family':True,'production_included':False,'valid':not reasons,
        'applicable':not reasons,'executed':not reasons,'reasons':reasons,
        'inputs_used':{'basis':basis,'canonical_shares':shares,'cash':cash,'debt':debt,
            'net_debt':debt-cash if cash is not None and debt is not None else None,'class_range':bounds},
        'low':None,'mid':None,'high':None,'enterprise_values':None,'equity_values':None,
        'negative_equity_signal':False}
    if reasons:return model
    multiples=(bounds[0],sum(bounds)/2,bounds[1])
    ev=[basis*m for m in multiples]
    equity=[value-(debt-cash) for value in ev]
    per_share=[value/shares for value in equity]
    if any(fnum(value) is None for value in ev+equity+per_share):
        model.update(valid=False,executed=True,reasons=['nonfinite_enterprise_calculation'])
        return model
    model.update(low=per_share[0],mid=per_share[1],high=per_share[2],
        enterprise_values=dict(zip(('low','mid','high'),ev)),equity_values=dict(zip(('low','mid','high'),equity)),
        multiples_used=dict(zip(('low','mid','high'),multiples)),
        negative_equity_signal=any(value<=0 for value in equity))
    return model


def difference_band(difference):
    if difference is None:return 'UNAVAILABLE'
    for threshold,label in zip(EARNINGS_DIFFERENCE_THRESHOLDS,('CONSISTENT','MODERATE_DIFFERENCE','MATERIAL_DIFFERENCE')):
        if at_most(abs(difference),threshold):return label
    return 'SEVERE_DIFFERENCE'


def enterprise_experiment(stock):
    f=stock.get('normalized_inputs',stock.get('financials')) or {}
    spec=stock.get('profile_assumptions') or {}
    g=stock.get('correlation_cross_family_governance') or governance_audit(stock)
    family=stock.get('experimental_family_blend') or family_blend_experiment(stock)
    overlay=stock.get('capital_structure_overlay') or capital_overlay(stock)
    blend=stock.get('live_blend',stock.get('blend')) or {}
    safe=bool(f.get('quote_currency') and f.get('financial_currency') and
        f['quote_currency']==f['financial_currency'] and not f.get('currency_mismatch'))
    shares,cash,debt=(fnum(f.get(k)) for k in ('canonical_shares','cash','debt'))
    global_reasons=[]
    if stock.get('source_status')=='cached_last_reliable':global_reasons.append('cached_display_not_same_live_inputs')
    if stock.get('calibration_eligibility') and stock['calibration_eligibility']!='ELIGIBLE':global_reasons.append('ineligible_input_state')
    models={
        'ev_ebitda':enterprise_model('ev_ebitda',fnum(f.get('ebitda')),shares,cash,debt,safe,valid_range(spec.get('ev_ebitda_range')),global_reasons),
        'ev_revenue':enterprise_model('ev_revenue',fnum(f.get('revenue')),shares,cash,debt,safe,valid_range(spec.get('sales_multiple_range')),global_reasons)}
    valid={name:m for name,m in models.items() if m['valid']}
    n=len(valid);mids=[m['mid'] for m in valid.values()]
    spread=(max(mids)-min(mids))/median(mids)*100 if n==2 and median(mids)>0 else None
    method_consistency=('UNAVAILABLE' if n==0 or n==2 and spread is None else 'SINGLE_METHOD' if n==1 else
        'CONSISTENT' if at_most(spread,CONSISTENT_SPREAD_PCT) else 'MODERATE_DISAGREEMENT' if at_most(spread,MODERATE_SPREAD_PCT) else 'METHOD_DISAGREEMENT')
    confidence='UNAVAILABLE' if not n else 'MEDIUM' if n==2 and spread is not None and at_most(spread,CONSISTENT_SPREAD_PCT) else 'LOW'
    weights={name:DIAGNOSTIC_BASE_WEIGHTS[name]/sum(DIAGNOSTIC_BASE_WEIGHTS[k] for k in valid) for name in valid}
    representative={key:sum(m[key]*weights[name] for name,m in valid.items()) if n else None for key in ('low','mid','high')}
    earnings=fnum(family.get('family_representatives',{}).get('EARNINGS_MULTIPLE',{}).get('family_mid'))
    enterprise_mid=representative['mid']
    difference=(enterprise_mid/earnings-1)*100 if enterprise_mid is not None and earnings is not None and earnings>0 else None
    band=difference_band(difference)
    direction=None if difference is None else 'FLAT' if difference==0 else 'UP' if difference>0 else 'DOWN'
    evidence=('UNAVAILABLE' if not n else 'SINGLE_METHOD' if n==1 else
        {'CONSISTENT':'CONSISTENT_WITH_EARNINGS','MODERATE_DIFFERENCE':'MODERATE_CONFLICT',
         'MATERIAL_DIFFERENCE':'MATERIAL_CONFLICT','SEVERE_DIFFERENCE':'SEVERE_CONFLICT'}.get(band,'UNAVAILABLE'))
    positive=enterprise_mid is not None and all(m['mid']>0 for m in valid.values())
    readiness=('NOT_READY' if n!=2 or spread is None or not at_most(spread,MODERATE_SPREAD_PCT) or not positive or difference is None else
        'STRONG_CANDIDATE' if at_most(spread,CONSISTENT_SPREAD_PCT) and at_most(STRONG_CANDIDATE_DIFFERENCE_PCT,abs(difference))
        and overlay.get('burden_band') in ('HIGH','VERY_HIGH') else 'REVIEW_CANDIDATE')
    observed=set(g.get('executed_families',[])) if not global_reasons else set()
    if n:observed.add('ENTERPRISE_MULTIPLE')
    production=fnum(stock.get('production_analysis_fair',stock.get('fair_value',blend.get('fair'))))
    equal=(earnings+enterprise_mid)/2 if earnings is not None and enterprise_mid is not None else None
    warnings=[]
    if n==1:warnings.append('SINGLE_ENTERPRISE_METHOD_ONLY')
    if method_consistency=='METHOD_DISAGREEMENT':warnings.append('ENTERPRISE_METHOD_DISAGREEMENT')
    if n==2 and spread is None:warnings.append('NONPOSITIVE_MEDIAN_PREVENTS_METHOD_SPREAD')
    if any(m['negative_equity_signal'] for m in valid.values()):warnings.append('NONPOSITIVE_EQUITY_RANGE_SIGNAL')
    if difference is not None and abs(difference)>=25:warnings.append('CLASS_MULTIPLE_FIT_REQUIRES_REVIEW')
    mix=deepcopy(f.get('business_mix_warning') or spec.get('business_mix_warning') or
        (blend.get('profile') or {}).get('business_mix_warning'))
    cashflow=fnum(family.get('family_representatives',{}).get('CASH_FLOW_INTRINSIC',{}).get('family_mid'))
    distances={name:abs(enterprise_mid-mid) for name,mid in (('EARNINGS_MULTIPLE',earnings),('CASH_FLOW_INTRINSIC',cashflow))
        if enterprise_mid is not None and mid is not None}
    nearest=min(distances,key=distances.get) if len(distances)==2 else None
    return {'applicability':{'applicable':bool(n),'valid_method_count':n,'global_reasons':global_reasons,'currency_safe':safe,
            'model_reasons':{name:m['reasons'] for name,m in models.items()}},
        'diagnostic_family_map':dict(DIAGNOSTIC_FAMILY_MAP),'experimental_family':True,'production_included':False,
        'ev_ebitda_model':models['ev_ebitda'],'ev_revenue_model':models['ev_revenue'],
        'enterprise_family':{**representative,'family':'ENTERPRISE_MULTIPLE','confidence':confidence,
            'weights':weights,'single_method_only':n==1,'valid_method_count':n,
            'negative_equity_signal':any(m['negative_equity_signal'] for m in valid.values())},
        'enterprise_family_low':representative['low'],'enterprise_family_mid':enterprise_mid,'enterprise_family_high':representative['high'],
        'enterprise_family_confidence':confidence,'single_method_only':n==1,
        'method_spread_pct':spread,'enterprise_method_spread_pct':spread,'method_consistency':method_consistency,
        'method_spread_reason':'requires_two_methods_and_positive_median' if spread is None else None,
        'earnings_family_mid':earnings,'difference_vs_earnings_pct':difference,'difference_band':band,'difference_direction':direction,
        'enterprise_evidence_status':evidence,'experimental_observed_families':sorted(observed),
        'experimental_independent_family_count':len(observed),
        'production_active_families':deepcopy(g.get('active_families',[])),
        'earnings_enterprise_equal_weight_fair':equal,'production_fair':production,
        'difference_vs_production_pct':(equal/production-1)*100 if equal is not None and production is not None and production>0 else None,
        'production_readiness':readiness,'enterprise_family_production_readiness':readiness,
        'capital_burden_band':overlay.get('burden_band'),
        'business_mix_warning':mix,'business_mix_warning_reason':None if mix else 'not_present_in_captured_production_fields',
        'cash_flow_family_mid':cashflow,'nearest_observed_family':nearest,'observed_family_distances':distances,
        'warnings':warnings,'scope':'DIAGNOSTIC_ONLY_NOT_A_PRODUCTION_MODEL_OR_RELIABILITY_INPUT'}


def enterprise_summary(stock):
    e=stock.get('enterprise_aware_experiment',{})
    return {'ticker':stock['ticker'],**{k:e.get(k) for k in ('production_fair','earnings_family_mid','enterprise_family_mid',
        'enterprise_family_confidence','method_spread_pct','difference_vs_earnings_pct','difference_direction',
        'enterprise_evidence_status','production_readiness','experimental_independent_family_count')},
        'evidence_status':e.get('enterprise_evidence_status'),
        'ev_ebitda_mid':e.get('ev_ebitda_model',{}).get('mid'),'ev_revenue_mid':e.get('ev_revenue_model',{}).get('mid')}
