"""Read-only structural dependency diagnostics, never statistical correlation."""
from itertools import combinations
from statistics import median
from valuation_primitives import fnum

MODEL_FAMILIES={
    'forward_pe':'EARNINGS_MULTIPLE','growth_adjusted_pe':'EARNINGS_MULTIPLE',
    'normalized_pe':'CYCLE_NORMALIZED','normalized_cycle_earnings':'CYCLE_NORMALIZED',
    'normalized_fcf_dcf':'CASH_FLOW_INTRINSIC','ev_ebitda':'ENTERPRISE_MULTIPLE',
    'revenue_multiple':'REVENUE_MULTIPLE','price_to_book_roe':'BOOK_VALUE',
    'residual_income':'BOOK_VALUE','unsupported':'SPECIALIZED'}
# Weighted structural drivers. Context (currency/class) is reported separately
# and cannot falsely make all per-share models highly dependent.
CORE_DRIVERS={
    'forward_pe':{'EPS_BASIS':4,'EARNINGS_MULTIPLE_POLICY':2},
    'growth_adjusted_pe':{'EPS_BASIS':4,'EARNINGS_MULTIPLE_POLICY':2,'SUSTAINABLE_GROWTH':1},
    'normalized_pe':{'EPS_BASIS':4,'EARNINGS_MULTIPLE_POLICY':2,'CYCLE_NORMALIZATION':2},
    'normalized_cycle_earnings':{'EPS_BASIS':4,'CYCLE_NORMALIZATION':2},
    'normalized_fcf_dcf':{'FCF':3,'CAPITAL_BRIDGE':4,'SHARES':2,'DISCOUNT_TERMINAL':1},
    'ev_ebitda':{'EBITDA':3,'CAPITAL_BRIDGE':4,'SHARES':2,'ENTERPRISE_MULTIPLE_POLICY':1},
    'revenue_multiple':{'REVENUE':3,'CAPITAL_BRIDGE':4,'SHARES':2,'SALES_MULTIPLE_POLICY':1},
    'price_to_book_roe':{'BOOK_VALUE':4,'ROE':2,'COST_OF_EQUITY':1},
    'residual_income':{'BOOK_VALUE':4,'ROE':2,'COST_OF_EQUITY':1,'RESIDUAL_GROWTH':1}}
DECLARED_INPUTS={
    'forward_pe':{'eps_basis','eps_source','quote_currency','valuation_class_assumptions','pe_range'},
    'growth_adjusted_pe':{'eps_basis','eps_source','quote_currency','valuation_class_assumptions','normalized_growth','peg_target','fair_pe'},
    'normalized_pe':{'eps_basis','quote_currency','valuation_class_assumptions','historical_eps','pe_range'},
    'normalized_cycle_earnings':{'eps_basis','historical_eps','quote_currency','valuation_class_assumptions'},
    'normalized_fcf_dcf':{'fcf','cash','debt','canonical_shares','quote_currency','financial_currency','discount_rate','terminal_growth','dcf_growth'},
    'ev_ebitda':{'ebitda','cash','debt','canonical_shares','quote_currency','financial_currency','enterprise_multiple'},
    'revenue_multiple':{'revenue','cash','debt','canonical_shares','quote_currency','financial_currency','sales_multiple'},
    'price_to_book_roe':{'book_value','roe','cost_of_equity','quote_currency','financial_currency'},
    'residual_income':{'book_value','roe','cost_of_equity','quote_currency','financial_currency','residual_growth'}}
HIGH_DEPENDENCY_MIN=.70
MODERATE_DEPENDENCY_MIN=.40
SAME_FAMILY_INCREMENT={'HIGH_DEPENDENCY':.25,'MODERATE_DEPENDENCY':.50,'LOW_DEPENDENCY':.75}
HIGH_CONCENTRATION_MIN=.75
MODERATE_CONCENTRATION_MIN=.60
CONSISTENT_SPREAD_PCT=20.
MODERATE_SPREAD_PCT=40.
FORECAST_STEP_UP_RATIO=1.5
OUTLIER_REASON='outlier_vs_other_models'


def dependency_pair(a,b,models):
    da,db=CORE_DRIVERS.get(a,{}),CORE_DRIVERS.get(b,{})
    union=set(da)|set(db);shared=set(da)&set(db)
    denominator=sum(max(da.get(k,0),db.get(k,0)) for k in union)
    overlap=sum(min(da[k],db[k]) for k in shared)/denominator if denominator else 0.
    status='HIGH_DEPENDENCY' if overlap>=HIGH_DEPENDENCY_MIN else 'MODERATE_DEPENDENCY' if overlap>=MODERATE_DEPENDENCY_MIN else 'LOW_DEPENDENCY'
    ia,ib=DECLARED_INPUTS.get(a,set()),DECLARED_INPUTS.get(b,set())
    return {'models':[a,b],'shared_inputs':sorted(ia&ib),'shared_input_count':len(ia&ib),
        'shared_core_driver_count':len(shared),'shared_core_drivers':sorted(shared),
        'distinct_core_drivers':{a:sorted(set(da)-shared),b:sorted(set(db)-shared)},
        'additional_inputs':{a:sorted(ia-ib),b:sorted(ib-ia)},
        'actual_recorded_inputs':{name:models[name].get('inputs') or {} for name in (a,b)},
        'dependency_overlap_score':overlap,'model_pair_governance_status':status,
        'methodology':'weighted core-driver Jaccard; declared structural dependencies, not Pearson correlation'}


def governance_audit(stock):
    # Never compare current live inputs to cached display models.
    if stock.get('source_status')=='cached_last_reliable':
        return {'audit_status':'SKIPPED_CACHED_INPUT_BLEND_MISMATCH','governance_classification':'INSUFFICIENT_EVIDENCE',
                'governance_review_status':'REVIEW_REQUIRED'}
    blend=stock.get('live_blend',stock.get('blend')) or {}
    after=blend.get('models') or {}
    before=stock.get('models_before_outlier') or {}
    included=list(blend.get('included') or [])
    models={name:dict(before.get(name) or model) for name,model in after.items()}
    for name,model in before.items():models.setdefault(name,dict(model))
    families={name:MODEL_FAMILIES.get(name,'SPECIALIZED') for name in models}
    pairs=[dependency_pair(a,b,models) for a,b in combinations(sorted(models),2)]
    pair_status={frozenset(p['models']):p['model_pair_governance_status'] for p in pairs}
    active={}
    for name in included:active.setdefault(MODEL_FAMILIES.get(name,'SPECIALIZED'),[]).append(name)
    effective=0.
    for family,names in active.items():
        previous=[]
        for name in sorted(names):
            if not previous:effective+=1.
            else:
                increment=min(SAME_FAMILY_INCREMENT[pair_status.get(frozenset((name,p)),'LOW_DEPENDENCY')] for p in previous)
                effective+=increment
            previous.append(name)
    concentration={family:sum(fnum((blend.get('weights_used') or {}).get(name)) or 0. for name in names) for family,names in active.items()}
    dominant=max(sorted(concentration),key=concentration.get) if concentration else None
    dominant_weight=concentration.get(dominant,0.)
    concentration_status=('HIGH_FAMILY_CONCENTRATION' if dominant_weight>=HIGH_CONCENTRATION_MIN else
        'MODERATE_FAMILY_CONCENTRATION' if dominant_weight>=MODERATE_CONCENTRATION_MIN else 'DIVERSIFIED_FAMILY_EVIDENCE')
    executed={}
    for name,model in models.items():
        post=after.get(name,{})
        is_outlier_only=post.get('outlier') and post.get('reason')==OUTLIER_REASON
        numeric=fnum(model.get('mid'))
        if model.get('applicable') is False or model.get('executed') is not True or numeric is None:continue
        if model.get('valid') is False and not is_outlier_only:continue
        executed.setdefault(families[name],[]).append((name,numeric))
    reps={family:{'family_model_count':len(values),'models':[name for name,_ in values],
        'family_mid_median':median(v for _,v in values),'family_mid_min':min(v for _,v in values),
        'family_mid_max':max(v for _,v in values)} for family,values in executed.items()}
    values=[r['family_mid_median'] for r in reps.values()]
    spread=pairwise=None
    if not values:cross_status='UNAVAILABLE'
    elif len(values)==1:cross_status='SINGLE_FAMILY_ONLY'
    else:
        center=median(values)
        if center<=0:cross_status='UNAVAILABLE'
        else:
            spread=(max(values)-min(values))/center*100
            pairwise=max((abs(a-b)/((abs(a)+abs(b))/2)*100 for a,b in combinations(values,2) if abs(a)+abs(b)>0),default=0.)
            cross_status='CONSISTENT' if spread<=CONSISTENT_SPREAD_PCT else 'MODERATE_DISAGREEMENT' if spread<=MODERATE_SPREAD_PCT else 'CROSS_FAMILY_DISAGREEMENT'
    reviews=[]
    for name,post in after.items():
        if (post.get('outlier') and post.get('reason')==OUTLIER_REASON and dominant
                and families.get(name)!=dominant and families.get(name) in executed
                and name in reps[families[name]]['models']):
            reviews.append({'model':name,'family':families[name],'flag':'CROSS_FAMILY_SIGNAL_SUPPRESSED',
                'production_exclusion_remains_unchanged':True,'exact_production_reason':post.get('reason')})
    f=stock.get('normalized_inputs',stock.get('financials')) or {}
    forward,trailing=fnum(f.get('forward_eps')),fnum(f.get('trailing_eps'))
    ratio=forward/trailing if forward is not None and trailing is not None and trailing>0 else None
    pe_pair=all(name in included for name in ('forward_pe','growth_adjusted_pe'))
    shared_eps=pe_pair and pair_status.get(frozenset(('forward_pe','growth_adjusted_pe')))=='HIGH_DEPENDENCY'
    shared_forward=(shared_eps and forward is not None and forward>0 and all(
        fnum((after.get(name,{}).get('inputs') or {}).get('forward_eps'))==forward
        and not after.get(name,{}).get('uses_proxy')
        and not (after.get(name,{}).get('inputs') or {}).get('uses_proxy')
        and not (after.get(name,{}).get('inputs') or {}).get('eps_proxy')
        for name in ('forward_pe','growth_adjusted_pe')))
    step_up=ratio is not None and ratio>FORECAST_STEP_UP_RATIO
    reasons=[]
    if shared_eps:reasons.append('included_earnings_models_share_eps_basis_and_growth_multiple_overlay')
    if shared_forward:reasons.append('both_included_pe_models_record_same_actual_forward_eps')
    if step_up:reasons.append('forward_to_trailing_eps_ratio_above_1_5')
    if ratio is None:reasons.append('forward_trailing_eps_ratio_unavailable')
    cash,debt,cap=(fnum(f.get(k)) for k in ('cash','debt','market_cap'))
    net_debt=debt-cash if cash is not None and debt is not None else None
    capital_flags=[]
    if net_debt is not None and net_debt>0 and set(active)=={'EARNINGS_MULTIPLE'}:
        capital_flags.append('CAPITAL_STRUCTURE_NOT_REPRESENTED_IN_ACTIVE_MODELS')
    if cross_status=='CROSS_FAMILY_DISAGREEMENT':classification='CROSS_FAMILY_CONFLICT';review='CROSS_FAMILY_REVIEW_REQUIRED'
    elif not included or not reps:classification='INSUFFICIENT_EVIDENCE';review='REVIEW_REQUIRED'
    elif len(active)==1:classification='SINGLE_FAMILY_ONLY';review='STRUCTURALLY_CONCENTRATED'
    elif dominant_weight>=HIGH_CONCENTRATION_MIN:classification='CONCENTRATED_SUPPORT';review='STRUCTURALLY_CONCENTRATED'
    else:classification='DIVERSIFIED_SUPPORT';review='REVIEW_REQUIRED' if cross_status=='MODERATE_DISAGREEMENT' or capital_flags or reviews else 'HEALTHY'
    if 'CASH_FLOW_INTRINSIC' in active:reasons.append('active_cash_flow_family_provides_separate_structural_evidence')
    risk='HIGH' if shared_forward and step_up else 'MODERATE' if shared_eps or step_up else 'LOW'
    active_mids=[fnum(after.get(name,{}).get('mid')) for name in included]
    numeric=[v for v in active_mids if v is not None]
    numerically_stable=(len(numeric)>=2 and median(numeric)>0
                        and (max(numeric)-min(numeric))/median(numeric)*100<=CONSISTENT_SPREAD_PCT)
    return {'audit_status':'DIAGNOSTIC_ONLY','model_families':families,'model_dependencies':pairs,'pair_dependencies':pairs,
        'model_count_included':len(included),'included_models':included,'effective_independent_model_count':effective,
        'active_families':sorted(active),'executed_families':sorted(executed),
        'family_weight_concentration':concentration,'dominant_family':dominant,'dominant_family_weight':dominant_weight,
        'family_concentration_status':concentration_status,'family_representatives':reps,
        'cross_family_status':cross_status,'cross_family_spread_pct':spread,'max_family_pairwise_difference_pct':pairwise,
        'outlier_governance_flags':[r['flag'] for r in reviews],'outlier_governance_review':reviews,
        'forward_to_trailing_eps_ratio':ratio,'forecast_step_up_status':'FORECAST_STEP_UP_HIGH' if step_up else 'UNKNOWN' if ratio is None else 'NO_HIGH_STEP_UP',
        'growth_overlap_risk':risk,'growth_overlap_reasons':reasons,
        'capital_structure':{'cash':cash,'debt':debt,'net_debt':net_debt,'net_debt_to_market_cap':net_debt/cap if net_debt is not None and cap is not None and cap>0 else None},
        'capital_structure_flags':capital_flags,'governance_classification':classification,'governance_review_status':review,
        'governance_summary':'NUMERICALLY_STABLE_BUT_CONCENTRATED' if len(active)==1 and shared_eps and numerically_stable else classification,
        'scope':'structural evidence diagnostics only; no production eligibility, weight, outlier or reliability changes'}
