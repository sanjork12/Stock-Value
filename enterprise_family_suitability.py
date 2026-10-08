"""V4.9 governed diagnostic-only suitability. No valuation formula, IO or ticker rules."""
from copy import deepcopy
import re
from capital_structure_overlay import valid_range
from valuation_primitives import fnum

VERSION='v4.9'
STATES=('PREFERRED','ACCEPTABLE','CONDITIONAL','NOT_PREFERRED','NOT_ELIGIBLE','INSUFFICIENT_EVIDENCE')
COMPONENT_MAX={'class_fit':25,'input_quality':20,'economic_interpretability':20,
    'business_mix_fit':15,'growth_regime_fit':10,'consistency_support':10}

# Proposal metadata only: not imported by production profiles or model registries.
_CLASS_ROWS={
    'mega_cap_tech':('STRONG','MODERATE','MODERATE','Profitable operating scale can anchor EBITDA; revenue requires margin/mix evidence.'),
    'mature_growth':('STRONG','WEAK','MODERATE','Mature profits favour EBITDA; sales alone omits operating margin and reinvestment.'),
    'semiconductor_growth':('MODERATE','MODERATE','MODERATE','Both scale anchors require growth-regime and cycle evidence; agreement is not validation.'),
    'cyclical_semiconductor':('WEAK','WEAK','WEAK','Spot EBITDA and sales may share cycle distortion; normalized operating evidence is required.'),
    'bank':('BLOCKED','BLOCKED','BLOCKED','Funding liabilities and financial assets are operating inputs; ordinary industrial EV bridges are inappropriate.'),
    'fintech_exchange':('MODERATE','WEAK','WEAK','Operating exchange economics may support EBITDA; balance-sheet exposure and revenue basis require explicit evidence.'),
    'crypto_treasury':('BLOCKED','BLOCKED','BLOCKED','Asset/NAV exposure is not anchored by operating EBITDA or sales.'),
    'high_growth_software':('WEAK','STRONG','MODERATE','Revenue can describe scalable operating scale; EBITDA may reflect transitional margins/SBC.'),
    'pre_profit_growth':('WEAK','MODERATE','WEAK','Positive interpretable revenue can be conditional evidence; nonmeaningful/nonpositive EBITDA is blocked.'),
    'space_optionality':('BLOCKED','BLOCKED','BLOCKED','Operating multiples cannot anchor specialized optionality without an explicitly different class policy.'),
    'auto_optionality':('BLOCKED','BLOCKED','BLOCKED','Specialized optionality requires separate operating/optionality evidence, not company-level multiples.'),
    'consumer_platform':('MODERATE','WEAK','WEAK','Class raises a question about margin interpretation; actual heterogeneity requires explicit metadata.'),
    'generic_profitable':('STRONG','WEAK','MODERATE','Interpretable recurring profit may support EBITDA; sales needs additional margin evidence.'),
    'unsupported_specialized':('BLOCKED','BLOCKED','BLOCKED','No governed operating-multiple applicability policy exists for this specialized class.')}


def class_policy(name):
    e,r,c,why=_CLASS_ROWS.get(name,('WEAK','WEAK','WEAK','Unknown class; no affirmative structural policy evidence.'))
    fits={'EV_EBITDA':e,'EV_REVENUE':r}
    return {'valuation_class':name,'ev_ebitda_base_fit':e,'ev_revenue_base_fit':r,'company_level_base_fit':c,
        'class_rationale':why,'rationale':why,'preferred_methods':[k for k,v in fits.items() if v=='STRONG'],
        'allowed_methods':[k for k,v in fits.items() if v!='BLOCKED'],
        'blocked_methods':[k for k,v in fits.items() if v=='BLOCKED'],
        'default_aggregation_policy':'COMPANY_LEVEL_AGGREGATION_NOT_RECOMMENDED' if c=='BLOCKED' else
            'WEIGHTED_METHOD_PRIORITY_REQUIRED' if e!=r else 'INSUFFICIENT_EVIDENCE',
        'proposal_only':True,'production_config_modified':False}


def policy_matrix():return [class_policy(name) for name in _CLASS_ROWS]


def ratio(a,b):
    a,b=fnum(a),fnum(b)
    return a/b if a is not None and b is not None and b>0 else None


def score_state(score):
    return 'PREFERRED' if score>=85 else 'ACCEPTABLE' if score>=70 else 'CONDITIONAL' if score>=50 else 'NOT_PREFERRED' if score>=30 else 'NOT_ELIGIBLE'


def consistency(spread):
    spread=fnum(spread)
    return 'UNKNOWN' if spread is None or spread<0 else 'CONSISTENT' if spread<=20+1e-9 else 'MODERATE_DISAGREEMENT' if spread<=40+1e-9 else 'MATERIAL_DISAGREEMENT'


def evidence(stock,vclass):
    f=stock.get('normalized_inputs',stock.get('financials')) or {}
    blend=stock.get('live_blend',stock.get('blend')) or {}
    profile=blend.get('profile') or {};spec=stock.get('profile_assumptions') or {}
    structural=stock.get('enterprise_structural_metadata') or {}
    def explicit(key):
        for name,obj in (('enterprise_structural_metadata',structural),('normalized_inputs',f),
            ('profile_assumptions',spec),('profile',profile)):
            if key in obj and obj[key] is not None:return obj[key],name+'.'+key
        return None,None
    keys=('heterogeneous_business_mix','business_mix_warning','segment_complexity',
        'company_level_multiple_risk','ebitda_economically_meaningful','ebitda_stable',
        'revenue_interpretable','scalable_operating_economics','margin_regime',
        'sbc_distortion','unusual_da_economics','accounting_distortion',
        'financial_balance_sheet_model','non_operating_revenue','operating_fundamentals_primary_value_driver',
        'cycle_normalized_ebitda','enterprise_input_basis_compatible','ebitda_metric_basis','revenue_metric_basis')
    flags={k:{'value':explicit(k)[0],'source':explicit(k)[1]} for k in keys}
    val=lambda k:flags[k]['value']
    mix='UNKNOWN'
    if val('company_level_multiple_risk') is True or val('business_mix_warning')=='COMPANY_LEVEL_MULTIPLE_RISK':mix='COMPANY_LEVEL_MULTIPLE_RISK'
    elif val('heterogeneous_business_mix') is True or val('business_mix_warning')=='EXPLICIT_HETEROGENEITY' or val('segment_complexity') in ('HIGH','VERY_HIGH'):mix='EXPLICIT_HETEROGENEITY'
    elif val('business_mix_warning')=='POSSIBLE_HETEROGENEITY' or val('segment_complexity')=='MODERATE':mix='POSSIBLE_HETEROGENEITY'
    elif val('heterogeneous_business_mix') is False or val('business_mix_warning')=='NONE' or val('segment_complexity')=='LOW':mix='NONE'
    growth_values={k:fnum(f.get(k)) for k in ('earnings_growth','revenue_growth')}
    forward_growth=ratio(f.get('forward_eps'),f.get('trailing_eps'))
    growth_values['forward_vs_trailing_change']=forward_growth-1 if forward_growth is not None else None
    growth_known=any(v is not None for v in growth_values.values())
    maximum=max((v for v in growth_values.values() if v is not None),default=None)
    growth='MATERIAL' if maximum is not None and maximum>=.5 else 'POSSIBLE' if (
        maximum is not None and maximum>=.25 or vclass in ('semiconductor_growth','high_growth_software','pre_profit_growth')
        or val('margin_regime')=='TRANSITIONAL') else False
    capex=fnum(f.get('normalized_capex',f.get('capital_expenditure')))
    if capex is None:capex=fnum(f.get('capital_expenditure_raw'))
    capex=abs(capex) if capex is not None else None
    capex_revenue=ratio(capex,f.get('revenue'));capex_ocf=ratio(capex,f.get('operating_cash_flow'))
    capint='VERY_HIGH' if (capex_revenue is not None and capex_revenue>.30 or capex_ocf is not None and capex_ocf>1) else (
        'HIGH' if (capex_revenue is not None and capex_revenue>.15 or capex_ocf is not None and capex_ocf>.7) else
        'MODERATE' if (capex_revenue is not None and capex_revenue>.05 or capex_ocf is not None and capex_ocf>.3) else
        'LOW' if capex_revenue is not None or capex_ocf is not None else 'UNKNOWN')
    ebitda_margin=ratio(f.get('ebitda'),f.get('revenue'));opmargin=fnum(f.get('operating_margin'))
    gross=fnum(f.get('gross_margin'))
    stable=val('ebitda_stable') is True or val('margin_regime') in ('STABLE','STABLE_HIGH_MARGIN','STABLE_MODERATE_MARGIN')
    if val('margin_regime')=='TRANSITIONAL':margin='TRANSITIONAL'
    elif val('unusual_da_economics') is True or any(v is not None and (v>1 or v<0) for v in (ebitda_margin,opmargin,gross)):margin='UNUSUAL'
    elif (opmargin is not None and opmargin<.1) or (ebitda_margin is not None and ebitda_margin<.1):margin='LOW_MARGIN'
    elif stable and ebitda_margin is not None:margin='STABLE_HIGH_MARGIN' if ebitda_margin>=.25 else 'STABLE_MODERATE_MARGIN'
    else:margin='UNKNOWN'
    overlay=stock.get('capital_structure_overlay') or {};ratios=overlay.get('ratios') or {}
    net=ratio((fnum(f.get('debt')) or 0)-(fnum(f.get('cash')) or 0),f.get('ebitda')) if fnum(f.get('debt')) is not None and fnum(f.get('cash')) is not None else None
    leverage=fnum(ratios.get('net_debt_to_ebitda'))
    if leverage is None:leverage=net
    relevance='UNKNOWN' if leverage is None else 'VERY_HIGH' if leverage>3.5 else 'HIGH' if leverage>2 else 'MODERATE' if leverage>1 else 'LOW'
    numeric={'ebitda_margin':ebitda_margin,'operating_margin':opmargin,'gross_margin':gross,
        'capex_to_revenue':capex_revenue,'capex_to_operating_cash_flow':capex_ocf,
        'net_debt_to_ebitda':leverage,'debt_to_ebitda':ratio(f.get('debt'),f.get('ebitda')),
        'growth_inputs':growth_values}
    dimensions={
        'PROFITABILITY_QUALITY':'PROFITABLE' if fnum(f.get('net_income')) is not None and fnum(f['net_income'])>0 else
            'NONPROFITABLE' if fnum(f.get('net_income')) is not None else profile.get('profitability_state','UNKNOWN'),
        'EBITDA_MEANINGFULNESS':val('ebitda_economically_meaningful') if isinstance(val('ebitda_economically_meaningful'),bool) else 'UNKNOWN',
        'EBITDA_STABILITY':'STABLE' if stable else 'UNSTABLE' if val('ebitda_stable') is False else 'UNKNOWN',
        'REVENUE_INTERPRETABILITY':val('revenue_interpretable') if isinstance(val('revenue_interpretable'),bool) else 'UNKNOWN',
        'MARGIN_STRUCTURE':margin,'CAPITAL_INTENSITY':capint,'CAPITAL_STRUCTURE_RELEVANCE':relevance,
        'CYCLICALITY':profile.get('cyclicality','HIGH_CLASS_RISK' if vclass=='cyclical_semiconductor' else 'UNKNOWN'),
        'GROWTH_REGIME':growth if growth else 'NORMAL_OBSERVED' if growth_known else 'UNKNOWN',
        'BUSINESS_MIX_HETEROGENEITY':mix,'OPTIONALITY_INTENSITY':profile.get('optionality_level','UNKNOWN'),
        'ACCOUNTING_DISTORTION_RISK':'EXPLICIT_CONCERN' if any(val(k) is True for k in ('sbc_distortion','unusual_da_economics','accounting_distortion')) else 'UNKNOWN',
        'VALUATION_CLASS_FIT':vclass,'METHOD_INTERNAL_CONSISTENCY':consistency((stock.get('enterprise_aware_experiment') or {}).get('method_spread_pct'))}
    return {'explicit':flags,'numeric':numeric,'dimensions':dimensions,'growth':growth,'growth_known':growth_known,
        'mix':mix,'capital_intensity':capint,'capital_relevance':relevance,'margin':margin,'stable':stable}


def method_audit(name,stock,policy,ev,eligible):
    f=stock.get('normalized_inputs',stock.get('financials')) or {};spec=stock.get('profile_assumptions') or {}
    model=(stock.get('enterprise_aware_experiment') or {}).get(name+'_model') or {}
    metric='ebitda' if name=='ev_ebitda' else 'revenue';bounds='ev_ebitda_range' if name=='ev_ebitda' else 'sales_multiple_range'
    fit=policy[name+'_base_fit'];ex=ev['explicit'];value=lambda key:ex[key]['value']
    blocks=[];positive=[];negative=[];missing=[]
    for field in (metric,'cash','debt','canonical_shares'):
        v=fnum(f.get(field))
        if v is None or field in (metric,'canonical_shares') and v<=0 or field in ('cash','debt') and v<0:blocks.append('missing_or_invalid_'+field)
    if not (isinstance(f.get('quote_currency'),str) and re.fullmatch('[A-Z]{3}',f['quote_currency'])
        and f['quote_currency']==f.get('financial_currency') and not f.get('currency_mismatch')):
        blocks.append('currency_unsafe_or_unknown')
    if valid_range(spec.get(bounds)) is None:blocks.append('missing_class_multiple_range')
    if fit=='BLOCKED':blocks.append('class_policy_blocked')
    if value('financial_balance_sheet_model') is True:blocks.append('financial_balance_sheet_semantics')
    if value('operating_fundamentals_primary_value_driver') is False:blocks.append('operating_fundamentals_not_value_anchor')
    if metric=='ebitda' and value('ebitda_economically_meaningful') is False:blocks.append('ebitda_not_economically_meaningful')
    if metric=='revenue' and (value('non_operating_revenue') is True or value('revenue_interpretable') is False):blocks.append('revenue_not_interpretable_operating_scale')
    if value('enterprise_input_basis_compatible') is False:blocks.append('explicit_incompatible_accounting_basis')
    if model.get('negative_equity_signal'):blocks.append('nonpositive_equity_range')
    if model and not model.get('valid'):negative+=['v48_'+reason for reason in model.get('reasons',[])]
    if not model:missing.append('captured_v48_method_result')
    elif not model.get('valid'):missing.append('valid_captured_v48_method')
    if policy['valuation_class'] not in _CLASS_ROWS:missing.append('governed_class_policy')
    provenance=f.get('acquisition_provenance') or {}
    direct=all((provenance.get(k) or {}).get('source_type')=='DIRECT' for k in (metric,'cash','debt'))
    share_known=bool(f.get('canonical_shares_source')) and str(f['canonical_shares_source']).lower() not in ('missing','unknown','none','unavailable')
    quality='INSUFFICIENT' if blocks else 'HIGH' if direct and share_known else 'MEDIUM' if share_known else 'LOW'
    economic=0
    if fnum(f.get(metric)) is not None and fnum(f[metric])>0:economic+=5;positive.append('positive_'+metric)
    profitable=ev['dimensions']['PROFITABILITY_QUALITY'] in ('PROFITABLE','profitable')
    if metric=='ebitda':
        if value('ebitda_economically_meaningful') is True:economic+=6;positive.append('explicit_ebitda_meaningfulness')
        elif value('ebitda_economically_meaningful') is None:missing.append('ebitda_meaningfulness')
        if ev['stable']:economic+=4;positive.append('explicit_stability')
        else:missing.append('ebitda_stability')
        if profitable:economic+=3;positive.append('positive_historical_profitability')
        if ev['numeric']['ebitda_margin'] is not None and 0<ev['numeric']['ebitda_margin']<=1:economic+=2
    else:
        if value('revenue_interpretable') is True:economic+=7;positive.append('explicit_revenue_interpretability')
        elif value('revenue_interpretable') is None:missing.append('revenue_interpretability')
        if ev['numeric']['operating_margin'] is not None and 0<=ev['numeric']['operating_margin']<=1:economic+=3
        if ev['numeric']['gross_margin'] is not None and 0<ev['numeric']['gross_margin']<=1:economic+=2
        if value('scalable_operating_economics') is True:economic+=3
    if ev['mix']=='UNKNOWN':missing.append('business_mix')
    if not ev['growth_known'] and ev['growth'] is False:missing.append('growth_regime')
    components={'class_fit':{'STRONG':25,'MODERATE':18,'WEAK':8,'BLOCKED':0}[fit],
        'input_quality':{'HIGH':20,'MEDIUM':14,'LOW':7,'INSUFFICIENT':0}[quality],
        'economic_interpretability':economic,
        'business_mix_fit':{'NONE':15,'POSSIBLE_HETEROGENEITY':7,'EXPLICIT_HETEROGENEITY':3,'COMPANY_LEVEL_MULTIPLE_RISK':0,'UNKNOWN':0}[ev['mix']],
        'growth_regime_fit':0 if ev['growth']=='MATERIAL' else 5 if ev['growth']=='POSSIBLE' else 10 if ev['growth_known'] else 0,
        # Method agreement is not evidence of individual method accuracy.
        'consistency_support':0}
    score=sum(components.values());suit=score_state(score);ceilings=[]
    concerns=[]
    if fit=='WEAK':concerns.append('weak_class_fit')
    if ev['growth']:concerns.append('growth_regime_mismatch')
    if ev['mix'] in ('EXPLICIT_HETEROGENEITY','COMPANY_LEVEL_MULTIPLE_RISK'):concerns.append('explicit_business_mix_complexity')
    if metric=='ebitda':
        if any(value(k) is True for k in ('sbc_distortion','unusual_da_economics','accounting_distortion')):concerns.append('ebitda_accounting_distortion')
        if policy['valuation_class']=='cyclical_semiconductor' and value('cycle_normalized_ebitda') is not True:concerns.append('spot_ebitda_cycle_normalization_unconfirmed')
        if ev['margin']=='TRANSITIONAL':concerns.append('transitional_ebitda_margin')
    else:
        if ev['capital_intensity'] in ('HIGH','VERY_HIGH'):concerns.append('capital_intensive_revenue_economics')
        if ev['margin']=='LOW_MARGIN':concerns.append('low_margin_revenue_anchor')
        if ev['capital_relevance'] in ('HIGH','VERY_HIGH'):concerns.append('revenue_ignores_material_financing_burden')
        if policy['valuation_class']=='pre_profit_growth':concerns.append('pre_profit_revenue_conditional_only')
        if policy['valuation_class']=='cyclical_semiconductor':concerns.append('cyclical_revenue_without_normalization')
    negative+=concerns
    if concerns or missing:
        ceilings+=concerns+['unconfirmed_'+m for m in missing]
        if suit in ('PREFERRED','ACCEPTABLE'):suit='CONDITIONAL'
    if not any(positive) and not blocks:suit='INSUFFICIENT_EVIDENCE'
    if blocks:suit='NOT_ELIGIBLE'
    if not eligible:
        suit='INSUFFICIENT_EVIDENCE' if not blocks else 'NOT_ELIGIBLE'
        ceilings.append('ineligible_batch_no_final_suitability_conclusion')
    candidate='YES' if eligible and suit in ('PREFERRED','ACCEPTABLE') and direct and share_known and not concerns and not missing and model.get('valid') else (
        'REVIEW' if eligible and not missing and suit in ('PREFERRED','ACCEPTABLE','CONDITIONAL') and model.get('valid') else 'NO')
    return {'suitability':suit,'score':score,'method_suitability_score':score,'score_components':components,'component_maxima':dict(COMPONENT_MAX),
        'input_quality':quality,'direct_input_evidence':direct,'hard_blocks':blocks,
        'positive_evidence':positive,'negative_evidence':negative,'missing_evidence':missing,
        'ceilings':ceilings,'production_candidate':candidate,'method_available':bool(model.get('valid')),
        'consistency_support_reason':'Company-level aggregation evidence only; zero points for method agreement.'}


def company_audit(ebitda,revenue,policy,ev,spread,eligible):
    methods={'EV_EBITDA':ebitda,'EV_REVENUE':revenue}
    good={k for k,v in methods.items() if v['suitability'] in ('PREFERRED','ACCEPTABLE') and v['method_available']}
    viable={k for k,v in methods.items() if v['suitability'] in ('PREFERRED','ACCEPTABLE','CONDITIONAL') and v['method_available']}
    band=consistency(spread);reasons=[]
    if policy['company_level_base_fit']=='BLOCKED' or all(v['suitability']=='NOT_ELIGIBLE' for v in methods.values()):
        suit,preferred,agg='NOT_ELIGIBLE','NONE','COMPANY_LEVEL_AGGREGATION_NOT_RECOMMENDED'
        reasons.append('company_class_or_both_methods_blocked')
    elif not eligible:
        suit,preferred,agg='INSUFFICIENT_EVIDENCE','UNRESOLVED','INSUFFICIENT_EVIDENCE';reasons.append('ineligible_input_state')
    elif not viable:
        suit,preferred,agg='NOT_PREFERRED','UNRESOLVED','COMPANY_LEVEL_AGGREGATION_NOT_RECOMMENDED';reasons.append('no_structurally_supported_method')
    elif len(good)==1:
        suit,preferred,agg='CONDITIONAL',next(iter(good)),'SINGLE_METHOD_PREFERRED';reasons.append('one_strong_method_other_weaker')
    elif len(viable)==1:
        suit,preferred,agg='CONDITIONAL',next(iter(viable)),'SINGLE_METHOD_PREFERRED';reasons.append('single_viable_method_requires_review')
    elif band=='MATERIAL_DISAGREEMENT':
        suit,preferred,agg='NOT_PREFERRED','UNRESOLVED','COMPANY_LEVEL_AGGREGATION_NOT_RECOMMENDED';reasons.append('material_method_disagreement')
    elif len(good)==2 and band=='CONSISTENT':
        suit,preferred,agg='ACCEPTABLE','BOTH','EQUAL_WEIGHT_REASONABLE'
        if all(v['suitability']=='PREFERRED' for v in methods.values()) and policy['company_level_base_fit']=='STRONG':suit='PREFERRED'
    else:
        suit,preferred,agg='CONDITIONAL','UNRESOLVED','WEIGHTED_METHOD_PRIORITY_REQUIRED';reasons.append('method_suitability_or_consistency_requires_review')
    if ev['mix']=='COMPANY_LEVEL_MULTIPLE_RISK':
        suit,agg='NOT_ELIGIBLE','COMPANY_LEVEL_AGGREGATION_NOT_RECOMMENDED';reasons.append('explicit_company_level_multiple_risk')
    elif ev['mix'] in ('EXPLICIT_HETEROGENEITY','POSSIBLE_HETEROGENEITY','UNKNOWN'):
        if suit in ('PREFERRED','ACCEPTABLE'):suit='CONDITIONAL'
        if agg=='EQUAL_WEIGHT_REASONABLE':agg='WEIGHTED_METHOD_PRIORITY_REQUIRED'
        reasons.append('business_mix_requires_evidence_or_segment_review')
    if band=='MODERATE_DISAGREEMENT' and suit in ('PREFERRED','ACCEPTABLE'):
        suit='CONDITIONAL';agg='WEIGHTED_METHOD_PRIORITY_REQUIRED';reasons.append('moderate_method_disagreement')
    if band=='MATERIAL_DISAGREEMENT' and suit not in ('NOT_ELIGIBLE','INSUFFICIENT_EVIDENCE'):
        suit='NOT_PREFERRED';reasons.append('material_spread_company_level_ceiling')
        if agg=='EQUAL_WEIGHT_REASONABLE':agg='COMPANY_LEVEL_AGGREGATION_NOT_RECOMMENDED'
    if band=='UNKNOWN' and len(viable)==2:
        suit='INSUFFICIENT_EVIDENCE';agg='INSUFFICIENT_EVIDENCE';reasons.append('captured_method_spread_unavailable')
    if ev['growth'] and suit in ('PREFERRED','ACCEPTABLE'):
        suit='CONDITIONAL';reasons.append('growth_regime_requires_review')
    if policy['company_level_base_fit']=='WEAK' and suit in ('PREFERRED','ACCEPTABLE'):
        suit='CONDITIONAL';reasons.append('weak_company_level_class_fit')
    candidate='YES' if (eligible and suit in ('PREFERRED','ACCEPTABLE') and len(good)==2 and band=='CONSISTENT' and
        ev['mix']=='NONE' and ev['growth'] is False and all(v['production_candidate']=='YES' for v in methods.values())) else (
        'REVIEW' if eligible and suit in ('PREFERRED','ACCEPTABLE','CONDITIONAL') and
        any(v['production_candidate'] in ('YES','REVIEW') for v in methods.values()) else 'NO')
    return {'suitability':suit,'preferred_enterprise_method':preferred,'aggregation_policy_assessment':agg,
        'method_spread_pct':spread,'method_internal_consistency':band,'production_candidate':candidate,'reasons':reasons}


def disagreement_driver(ev,spec,spread):
    if consistency(spread) in ('UNKNOWN','CONSISTENT'):return 'UNKNOWN',{}
    if ev['mix'] in ('EXPLICIT_HETEROGENEITY','COMPANY_LEVEL_MULTIPLE_RISK'):return 'BUSINESS_MIX_HETEROGENEITY',{}
    if ev['explicit']['enterprise_input_basis_compatible']['value'] is False:return 'ACCOUNTING_BASIS_DIFFERENCE',{}
    if ev['capital_intensity'] in ('HIGH','VERY_HIGH'):return 'CAPITAL_INTENSITY',{}
    if ev['growth']=='MATERIAL':return 'GROWTH_REGIME_MISMATCH',{}
    er=valid_range(spec.get('ev_ebitda_range'));rr=valid_range(spec.get('sales_multiple_range'))
    implied=(sum(rr)/sum(er)) if er and rr else None
    observed=ev['numeric']['ebitda_margin'];gap=(observed/implied-1) if observed is not None and implied else None
    context={'observed_ebitda_margin':observed,'class_multiple_pair_implied_margin':implied,'relative_margin_gap':gap,
        'interpretation':'Range-pair margin semantics, not a claim of value accuracy.'}
    if gap is not None and abs(gap)>.25:return 'MARGIN_SENSITIVITY',context
    if ev['capital_relevance'] in ('HIGH','VERY_HIGH'):return 'LEVERAGE_SENSITIVITY',context
    return 'UNKNOWN',context


def suitability_audit(stock,*,batch_eligibility=None):
    e=stock.get('enterprise_aware_experiment') or {};blend=stock.get('live_blend',stock.get('blend')) or {}
    vclass=(blend.get('profile') or {}).get('valuation_class') or stock.get('valuation_class') or 'UNKNOWN'
    policy=class_policy(vclass)
    eligible=(batch_eligibility=='ELIGIBLE' and stock.get('calibration_eligibility')=='ELIGIBLE'
        and stock.get('source_status')=='live' and bool(e))
    ev=evidence(stock,vclass)
    eb=method_audit('ev_ebitda',stock,policy,ev,eligible);rev=method_audit('ev_revenue',stock,policy,ev,eligible)
    spread=fnum(e.get('method_spread_pct'));company=company_audit(eb,rev,policy,ev,spread,eligible)
    driver,driver_evidence=disagreement_driver(ev,stock.get('profile_assumptions') or {},spread)
    n=sum(m['method_available'] for m in (eb,rev))
    readiness='NOT_READY' if not eligible or company['suitability']=='NOT_ELIGIBLE' or n==0 else (
        'PRODUCTION_CANDIDATE' if company['production_candidate']=='YES' else
        'REVIEW_CANDIDATE' if company['production_candidate']=='REVIEW' else 'DIAGNOSTIC_ONLY')
    context={k:deepcopy(e.get(k)) for k in ('earnings_family_mid','enterprise_family_mid','difference_vs_earnings_pct','difference_direction','enterprise_evidence_status')}
    context.update(structural_governance=deepcopy(stock.get('structural_governance')),
        independent_evidence_governance=deepcopy(stock.get('independent_evidence_governance')),
        used_for_method_score=False)
    refs={k:deepcopy(e.get(k)) for k in ('ev_ebitda_model','ev_revenue_model','enterprise_family_mid','enterprise_family_confidence',
        'method_spread_pct','difference_vs_earnings_pct','difference_direction','enterprise_evidence_status','input_snapshot')}
    return {'version':VERSION,'audit_status':'ELIGIBLE_DIAGNOSTIC_AUDIT' if eligible else 'INELIGIBLE_INPUT_STATE',
        'batch_calibration_eligibility':batch_eligibility,'stock_calibration_eligibility':stock.get('calibration_eligibility'),
        'valuation_class':vclass,'enterprise_method_class_policy':policy,'ev_ebitda':eb,'ev_revenue':rev,'company_level':company,
        'growth_regime_mismatch_flag':ev['growth'],'business_mix_warning':ev['mix'],
        'capital_intensity_assessment':ev['capital_intensity'],'capital_structure_relevance':ev['capital_relevance'],
        'margin_structure_assessment':ev['margin'],'primary_disagreement_driver':driver,'disagreement_driver_evidence':driver_evidence,
        'enterprise_family_independence_value':'HIGH' if n==2 else 'MODERATE' if n==1 else 'LOW',
        'independence_reason':'Operating EBITDA/revenue and net-debt bridge differ from EPS multiples; independence is not suitability.',
        'enterprise_family_readiness':readiness,'enterprise_family_production_candidate':company['production_candidate'],
        'company_level_enterprise_suitability':company['suitability'],'evidence':ev,
        'cross_family_conflict_context':context,'v48_references':refs,
        'scope':'DIAGNOSTIC_ONLY_METHOD_SUITABILITY_NOT_VALUE_ACCURACY','production_included':False,
        'production_integration_performed':False,'last_reliable_used_for_inputs_or_scores':False}


def summary(stock):
    s=stock.get('enterprise_family_suitability') or {};eb=s.get('ev_ebitda') or {};r=s.get('ev_revenue') or {};c=s.get('company_level') or {}
    return {'ticker':stock['ticker'],'valuation_class':s.get('valuation_class'),'audit_status':s.get('audit_status'),
        'ev_ebitda_suitability':eb.get('suitability'),'ev_ebitda_score':eb.get('score'),
        'ev_revenue_suitability':r.get('suitability'),'ev_revenue_score':r.get('score'),
        'company_level_suitability':c.get('suitability'),'method_spread_pct':c.get('method_spread_pct'),
        'preferred_method':c.get('preferred_enterprise_method'),'aggregation_policy':c.get('aggregation_policy_assessment'),
        'growth_regime_mismatch':s.get('growth_regime_mismatch_flag'),'business_mix_warning':s.get('business_mix_warning'),
        'capital_intensity':s.get('capital_intensity_assessment'),'primary_disagreement_driver':s.get('primary_disagreement_driver'),
        'enterprise_family_production_candidate':c.get('production_candidate'),'readiness':s.get('enterprise_family_readiness')}


def attach_report(report):
    out=deepcopy(report)
    for stock in out.get('stocks',[]):stock['enterprise_family_suitability']=suitability_audit(stock,batch_eligibility=out.get('batch_calibration_eligibility'))
    out['enterprise_suitability_version']=VERSION
    return out


def audit_export(report):
    prepared=attach_report(report)
    return {'version':VERSION,'batch_id':prepared.get('batch_id'),'generated_at':prepared.get('generated_at'),
        'batch_calibration_eligibility':prepared.get('batch_calibration_eligibility'),
        'mode':'DIAGNOSTIC_ONLY_METHOD_SUITABILITY','proposed_enterprise_method_policy':policy_matrix(),
        'stocks':[{'ticker':s['ticker'],'enterprise_family_suitability':s['enterprise_family_suitability']} for s in prepared.get('stocks',[])]}


def csv_export(report):
    import csv,io
    rows=[summary(s) for s in attach_report(report).get('stocks',[])]
    buffer=io.StringIO(newline='')
    if rows:
        writer=csv.DictWriter(buffer,fieldnames=list(rows[0]));writer.writeheader()
        for row in rows:writer.writerow({k:"'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v for k,v in row.items()})
    return buffer.getvalue().encode('utf-8-sig')
