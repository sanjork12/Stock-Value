"""Diagnostic-only capital structure experiments. No production model/storage calls."""
from model_family_governance import governance_audit
from experimental_family_blend import family_blend_experiment
from valuation_primitives import fnum

NET_DEBT_THRESHOLDS=(.10,.25,.50)
LEVERAGE_THRESHOLDS=(1.,2.,3.5)
INTEREST_THRESHOLDS=(8.,4.,2.)
BURDEN_THRESHOLDS=(20.,40.,65.)
COMPONENT_WEIGHTS={'net_debt_to_market_cap':.35,'net_debt_to_ebitda':.30,'interest_coverage':.20,'enterprise_multiple_stretch':.15}
RISK_SCORES={'LOW':0.,'MODERATE':35.,'HIGH':70.,'VERY_HIGH':100.,'NET_CASH':0.,
    'STRONG':0.,'ADEQUATE':35.,'WEAK':70.,'VERY_WEAK':100.,
    'BELOW_RANGE':0.,'WITHIN_RANGE':0.,'ABOVE_RANGE':60.,'FAR_ABOVE_RANGE':100.}
DISCOUNTS={'LOW':0.,'MODERATE':.05,'HIGH':.10,'VERY_HIGH':.15}
STRETCH_TOLERANCE=.20
CONSISTENCY_NEAR_PCT=10.
CONSISTENCY_CONFLICT_PCT=25.


def ascending_band(value,thresholds,labels=('LOW','MODERATE','HIGH','VERY_HIGH')):
    if value is None:return 'UNAVAILABLE'
    for limit,label in zip(thresholds,labels):
        if value<=limit:return label
    return labels[-1]


def interest_band(value):
    if value is None:return 'UNAVAILABLE'
    return next((label for limit,label in zip(INTEREST_THRESHOLDS,('STRONG','ADEQUATE','WEAK')) if value>=limit),'VERY_WEAK')


def sanity_band(value,bounds):
    if value is None or bounds is None:return 'UNAVAILABLE'
    lo,hi=bounds
    if value<lo:return 'BELOW_RANGE'
    if value<=hi:return 'WITHIN_RANGE'
    return 'ABOVE_RANGE' if value<=hi*(1+STRETCH_TOLERANCE) else 'FAR_ABOVE_RANGE'


def valid_range(value):
    if not isinstance(value,(list,tuple)) or len(value)!=2:return None
    lo,hi=map(fnum,value)
    return (lo,hi) if lo is not None and hi is not None and 0<lo<=hi else None


def weighted_burden(components):
    used={k:{'raw_score':v,'base_weight':COMPONENT_WEIGHTS[k]} for k,v in components.items() if v is not None}
    total=sum(v['base_weight'] for v in used.values())
    for value in used.values():
        value['normalized_weight']=value['base_weight']/total
        value['contribution']=value['raw_score']*value['normalized_weight']
    return (sum(v['contribution'] for v in used.values()) if used else None),used,total


def capital_overlay(stock):
    f=stock.get('normalized_inputs',stock.get('financials')) or {}
    g=stock.get('correlation_cross_family_governance') or governance_audit(stock)
    experiment=stock.get('experimental_family_blend') or family_blend_experiment(stock)
    blend=stock.get('live_blend',stock.get('blend')) or {}
    production=fnum(stock.get('production_analysis_fair',stock.get('fair_value',blend.get('fair'))))
    active=g.get('active_families',[])
    inputs={k:fnum(f.get(key)) for k,key in (('cash','cash'),('total_debt','debt'),('market_cap','market_cap'),
        ('ebitda','ebitda'),('revenue','revenue'),('interest_expense','interest_expense'),('ebit','ebit'),
        ('canonical_shares','canonical_shares'),('net_income','net_income'),('trailing_eps','trailing_eps'))}
    reasons={k:'missing_or_nonfinite' for k,v in inputs.items() if v is None}
    cash,debt,cap=inputs['cash'],inputs['total_debt'],inputs['market_cap']
    safe=bool(f.get('quote_currency') and f.get('financial_currency') and
        f['quote_currency']==f['financial_currency'] and not f.get('currency_mismatch'))
    net=debt-cash if debt is not None and cash is not None else None
    inputs.update(net_debt=net,enterprise_value=cap+net if cap is not None and net is not None else None,
        quote_currency=f.get('quote_currency'),financial_currency=f.get('financial_currency'))
    if net is None:reasons['net_debt']='missing_cash_or_debt'
    if inputs['enterprise_value'] is None:reasons['enterprise_value']='missing_market_cap_or_net_debt'
    # Historical profitability only, never future EPS or external price/targets.
    profit=inputs['net_income'] if inputs['net_income'] is not None else inputs['trailing_eps']
    profit_source='net_income' if inputs['net_income'] is not None else 'trailing_eps'
    failures=[]
    if stock.get('source_status')=='cached_last_reliable':failures.append('cached_display_not_same_live_input')
    if stock.get('calibration_eligibility') and stock['calibration_eligibility']!='ELIGIBLE':failures.append('ineligible_input_state')
    if profit is None or profit<=0:failures.append('profitability_unconfirmed_or_nonpositive')
    if 'EARNINGS_MULTIPLE' not in active:failures.append('no_active_earnings_family')
    if cash is None or debt is None or cash<0 or debt<0:failures.append('missing_or_negative_cash_debt')
    if cap is None or cap<=0:failures.append('missing_or_nonpositive_market_cap')
    if not safe:failures.append('capital_currency_unsafe_or_unknown')
    shares=inputs['canonical_shares']
    if shares is None or shares<=0:failures.append('missing_or_nonpositive_canonical_shares')
    earnings=fnum(experiment.get('family_representatives',{}).get('EARNINGS_MULTIPLE',{}).get('family_mid'))
    if earnings is None or earnings<=0:failures.append('missing_captured_earnings_family_representative')
    result={'applicability':{'applicable':not failures,'reasons':failures,'profitability_source':profit_source,
        'currency_safe':safe},'overlay_role':'PRIMARY_STRUCTURAL_DIAGNOSTIC' if active==['EARNINGS_MULTIPLE'] else 'SECONDARY_DIAGNOSTIC',
        'inputs':inputs,'input_reasons':reasons,'production_fair':production,'earnings_family_fair':earnings,
        'scope':'DIAGNOSTIC_ONLY_NOT_A_PRODUCTION_MODEL','fair_value_effect':'NONE'}
    if failures:
        return {**result,'ratios':{},'bands':{},'burden_score':None,'burden_band':'UNAVAILABLE',
            'score_components':{},'score_components_used':[],'burden_overlay_fair':None,'ev_bridge_fair':None,
            'consistency_status':'UNAVAILABLE','governance':'UNAVAILABLE'}
    ratios={};ratio_reasons={}
    def ratio(name,numerator,denominator):
        ratios[name]=numerator/denominator if numerator is not None and denominator is not None and denominator>0 else None
        if ratios[name] is None:ratio_reasons[name]='missing_numerator_or_nonpositive_denominator'
    ratio('net_debt_to_market_cap',net,cap);ratio('debt_to_market_cap',debt,cap)
    ratio('net_debt_to_ebitda',net,inputs['ebitda']);ratio('debt_to_ebitda',debt,inputs['ebitda'])
    interest=inputs['interest_expense']
    ratio('interest_coverage',inputs['ebit'],abs(interest) if interest is not None else None)
    equity=earnings*shares;implied_ev=equity+net
    ratio('implied_ev_to_ebitda',implied_ev,inputs['ebitda']);ratio('implied_ev_to_revenue',implied_ev,inputs['revenue'])
    spec=stock.get('profile_assumptions') or {}
    ev_range=valid_range(spec.get('ev_ebitda_range'));sales_range=valid_range(spec.get('sales_multiple_range'))
    bands={'net_debt_band':'NET_CASH' if net<=0 else ascending_band(ratios['net_debt_to_market_cap'],NET_DEBT_THRESHOLDS),
        'leverage_band':ascending_band(ratios['net_debt_to_ebitda'],LEVERAGE_THRESHOLDS),
        'interest_coverage_band':interest_band(ratios['interest_coverage']),
        'implied_ev_ebitda_vs_class_range':sanity_band(ratios['implied_ev_to_ebitda'],ev_range),
        'implied_ev_revenue_vs_class_range':sanity_band(ratios['implied_ev_to_revenue'],sales_range)}
    stretch=[RISK_SCORES[bands[k]] for k in ('implied_ev_ebitda_vs_class_range','implied_ev_revenue_vs_class_range') if bands[k]!='UNAVAILABLE']
    components={'net_debt_to_market_cap':RISK_SCORES.get(bands['net_debt_band']),
        'net_debt_to_ebitda':RISK_SCORES.get(bands['leverage_band']),
        'interest_coverage':RISK_SCORES.get(bands['interest_coverage_band']),
        'enterprise_multiple_stretch':max(stretch) if stretch else None}
    score,used,coverage=weighted_burden(components)
    burden=ascending_band(score,BURDEN_THRESHOLDS);discount=DISCOUNTS[burden]
    overlay=earnings*(1-discount)
    ev_bridge=(sum(ev_range)/2*inputs['ebitda']-net)/shares if ev_range and inputs['ebitda'] is not None and inputs['ebitda']>0 else None
    def diff(value,reference):return (value/reference-1)*100 if value is not None and reference is not None and reference>0 else None
    differences={'burden_overlay':diff(overlay,production),'ev_bridge':diff(ev_bridge,production)}
    ds=list(differences.values())
    consistency=('UNAVAILABLE' if any(v is None for v in ds) else
        'CONSISTENT' if max(abs(v) for v in ds)<=CONSISTENCY_NEAR_PCT else
        'CAPITAL_STRUCTURE_CONFLICT' if all(v<-CONSISTENCY_CONFLICT_PCT for v in ds) else 'MODERATE_CONCERN')
    governance=('MATERIAL_CAPITAL_STRUCTURE_CONFLICT' if burden=='VERY_HIGH' or consistency=='CAPITAL_STRUCTURE_CONFLICT' else
        'REVIEW_REQUIRED' if burden=='HIGH' else 'MONITOR' if burden=='MODERATE' or consistency=='MODERATE_CONCERN' else
        'NO_CONCERN' if burden=='LOW' and consistency=='CONSISTENT' else 'UNAVAILABLE')
    return {**result,'ratios':ratios,'ratio_reasons':ratio_reasons,'bands':bands,
        'class_ranges':{'ev_ebitda_range':ev_range,'sales_multiple_range':sales_range},
        'class_range_reasons':{k:'missing_or_invalid_captured_class_range' for k,v in
            (('ev_ebitda_range',ev_range),('sales_multiple_range',sales_range)) if v is None},
        'earnings_equity_value':equity,'implied_enterprise_value':implied_ev,
        'burden_score':score,'capital_structure_burden_score':score,'burden_band':burden,
        'capital_structure_burden_band':burden,'score_components':used,'score_components_used':list(used),
        'score_weight_coverage':coverage,'score_components_missing':{k:'input_or_class_range_unavailable' for k,v in components.items() if v is None},
        'burden_discount_pct':discount,'experimental_discount_pct':discount,'burden_overlay_fair':overlay,
        'capital_structure_adjusted_equity_value':overlay*shares,'capital_structure_adjusted_equity_fair':overlay,
        'class_range_ev_bridge':{'midpoint':sum(ev_range)/2 if ev_range else None,
            'diagnostic_enterprise_value':sum(ev_range)/2*inputs['ebitda'] if ev_bridge is not None else None,
            'diagnostic_equity_value':ev_bridge*shares if ev_bridge is not None else None,
            'reason':None if ev_bridge is not None else 'missing_class_ev_range_or_positive_ebitda'},
        'ev_bridge_fair':ev_bridge,'negative_equity_signal':ev_bridge is not None and ev_bridge<=0,
        'difference_vs_production_pct':differences,'difference_between_overlay_methods_pct':diff(ev_bridge,overlay),
        'consistency_status':consistency,'consistency_reason':'both_methods_required; >25% downward difference on both methods required for conflict',
        'governance':governance,'capital_structure_governance':governance}


def overlay_summary(stock):
    o=stock.get('capital_structure_overlay',{})
    return {'ticker':stock['ticker'],'applicable':o.get('applicability',{}).get('applicable'),
        'reason':o.get('applicability',{}).get('reasons'),
        **{k:o.get(k) for k in ('overlay_role','production_fair','earnings_family_fair','burden_score','burden_band',
            'burden_overlay_fair','ev_bridge_fair','consistency_status','governance')},
        'net_debt':o.get('inputs',{}).get('net_debt'),
        **{k:o.get('ratios',{}).get(k) for k in ('net_debt_to_market_cap','net_debt_to_ebitda','interest_coverage')}}
