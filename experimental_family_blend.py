"""Family weighting sandbox: no production valuation, state or parameters edited."""
from statistics import median
from model_family_governance import governance_audit,SAME_FAMILY_INCREMENT,CONSISTENT_SPREAD_PCT
from valuation_primitives import fnum

FULL_EVIDENCE_MIN=1.75
PARTIAL_EVIDENCE_MIN=1.25
FULL_EVIDENCE_STRENGTH=1.
PARTIAL_EVIDENCE_STRENGTH=.85
SINGLE_EVIDENCE_STRENGTH=.70
# Uniform modifier explicitly preserves every conflicting family. It cancels
# on normalization; it expresses caution, not a benchmark-based preference.
CONFLICT_GOVERNANCE_MODIFIER=.85
NORMAL_GOVERNANCE_MODIFIER=1.
LOW_SENSITIVITY_MAX_PCT=10.
MODERATE_SENSITIVITY_MAX_PCT=25.


def evidence_strength(effective):
    return FULL_EVIDENCE_STRENGTH if effective>=FULL_EVIDENCE_MIN else PARTIAL_EVIDENCE_STRENGTH if effective>=PARTIAL_EVIDENCE_MIN else SINGLE_EVIDENCE_STRENGTH


def sensitivity_band(difference):
    if difference is None:return 'UNAVAILABLE'
    absolute=abs(difference)
    return 'LOW_SENSITIVITY' if absolute<=LOW_SENSITIVITY_MAX_PCT else 'MODERATE_SENSITIVITY' if absolute<=MODERATE_SENSITIVITY_MAX_PCT else 'HIGH_SENSITIVITY'


def family_blend_experiment(stock):
    """Only read captured inputs + existing successful-family governance.

    Outlier-only invalidation is restored; other invalid/applicability failures
    are never rescued. Base weights must come from captured model/profile data.
    """
    if stock.get('source_status')=='cached_last_reliable' or (
        stock.get('calibration_eligibility') and stock['calibration_eligibility']!='ELIGIBLE'):
        return {'status':'INELIGIBLE_INPUT_STATE','family_weighting_governance':'NO_ACTION',
                'reason':'No experiment mixes degraded live inputs with cached results.'}
    governance=stock.get('correlation_cross_family_governance') or governance_audit(stock)
    blend=stock.get('live_blend',stock.get('blend')) or {}
    after=blend.get('models') or {}
    before=stock.get('models_before_outlier') or {}
    profile_weights=((blend.get('profile') or {}).get('model_weights') or
                     (stock.get('profile_assumptions') or {}).get('weights') or {})
    production=fnum(stock.get('production_analysis_fair',stock.get('fair_value',blend.get('fair'))))
    pair_status={frozenset(p['models']):p['model_pair_governance_status'] for p in governance.get('pair_dependencies',[])}
    representatives={}
    omitted=[]
    for family,existing in governance.get('family_representatives',{}).items():
        members=[]
        for name in existing['models']:
            model=before.get(name) or after.get(name) or {}
            post=after.get(name) or {}
            mid=fnum(model.get('mid'))
            restored=bool(post.get('outlier') and post.get('reason')=='outlier_vs_other_models')
            if model.get('applicable') is False or model.get('executed') is not True or mid is None or (model.get('valid') is False and not restored):continue
            weight=fnum(post.get('base_weight',profile_weights.get(name)))
            if weight is None or weight<=0:
                omitted.append({'model':name,'reason':'missing_positive_captured_base_weight'})
                continue
            members.append({'model':name,'mid':mid,'low':fnum(model.get('low')),'high':fnum(model.get('high')),
                'base_weight':weight,'production_included':name in blend.get('included',[]),
                'restored_outlier_only':restored})
        if not members:continue
        total=sum(m['base_weight'] for m in members)
        for member in members:member['family_internal_share']=member['base_weight']/total
        effective=0.;previous=[]
        for member in sorted(members,key=lambda m:m['model']):
            name=member['model']
            effective+=1. if not previous else min(SAME_FAMILY_INCREMENT[pair_status.get(frozenset((name,p)),'LOW_DEPENDENCY')] for p in previous)
            previous.append(name)
        mid=sum(m['mid']*m['family_internal_share'] for m in members)
        low=sum(m['low']*m['family_internal_share'] for m in members) if all(m['low'] is not None for m in members) else None
        high=sum(m['high']*m['family_internal_share'] for m in members) if all(m['high'] is not None for m in members) else None
        representatives[family]={'family':family,'member_models':[m['model'] for m in members],
            'members':members,'raw_model_count':len(members),'effective_model_count':effective,
            'family_effective_model_count':effective,'family_mid':mid,'family_low':low,'family_high':high,
            'correlation_adjusted_family_mid':mid,'family_base_weight_sum':total,
            'dependency_penalty':1-effective/len(members),'family_dependency_penalty':1-effective/len(members),
            'evidence_strength':evidence_strength(effective),'family_evidence_strength':evidence_strength(effective)}
    if omitted:
        return {'status':'INCOMPLETE_CAPTURED_BASE_WEIGHTS','omitted_models':omitted,
            'family_weighting_governance':'NO_ACTION','family_representatives':representatives}
    if not representatives:return {'status':'UNAVAILABLE','family_count':0,'family_weighting_governance':'NO_ACTION'}
    conflict=governance.get('cross_family_status')=='CROSS_FAMILY_DISAGREEMENT'
    modifier=CONFLICT_GOVERNANCE_MODIFIER if conflict else NORMAL_GOVERNANCE_MODIFIER
    weights_a={f:r['family_base_weight_sum'] for f,r in representatives.items()}
    weights_b={f:1. for f in representatives}
    weights_c={f:r['family_base_weight_sum']*r['evidence_strength']*modifier for f,r in representatives.items()}
    def strategy(raw):
        total=sum(raw.values());weights={f:w/total for f,w in raw.items()}
        fair=sum(representatives[f]['family_mid']*w for f,w in weights.items())
        delta=(fair/production-1)*100 if production is not None and production>0 else None
        return {'fair':fair,'family_weights':weights,'experimental_family_weights':weights,
            'raw_family_weights':raw,'difference_vs_production_pct':delta,
            'family_weighting_sensitivity':sensitivity_band(delta)}
    a,b,c=(strategy(w) for w in (weights_a,weights_b,weights_c))
    suppressed=[review for review in governance.get('outlier_governance_review',[])
        if review['family'] in representatives and review['family'] not in governance.get('active_families',[])]
    families_suppressed=sorted({item['family'] for item in suppressed})
    max_difference=max((abs(s['difference_vs_production_pct']) for s in (a,b,c) if s['difference_vs_production_pct'] is not None),default=None)
    sensitivity=sensitivity_band(max_difference)
    single=len(representatives)==1
    family_mid_values=[m['mid'] for r in representatives.values() for m in r['members']]
    stability=(single and len(family_mid_values)>=2 and median(family_mid_values)>0
        and (max(family_mid_values)-min(family_mid_values))/median(family_mid_values)*100<=CONSISTENT_SPREAD_PCT)
    if conflict:recommendation='CROSS_FAMILY_CONFLICT_REQUIRES_REVIEW'
    elif single:recommendation='SINGLE_FAMILY_LIMITATION'
    elif governance.get('cross_family_status')=='MODERATE_DISAGREEMENT' or sensitivity=='HIGH_SENSITIVITY':recommendation='FAMILY_LEVEL_BLEND_NEEDS_REVIEW'
    elif sensitivity=='MODERATE_SENSITIVITY':recommendation='FAMILY_LEVEL_BLEND_PROMISING'
    else:recommendation='NO_ACTION'
    return {'status':'SINGLE_FAMILY_EXPERIMENT' if single else 'MULTI_FAMILY_EXPERIMENT',
        'production_fair':production,'active_families':governance.get('active_families',[]),
        'executed_families':governance.get('executed_families',[]),'family_count':len(representatives),
        'family_representatives':representatives,'family_effective_model_count':{f:r['effective_model_count'] for f,r in representatives.items()},
        'family_evidence_strength':{f:r['evidence_strength'] for f,r in representatives.items()},
        'strategy_a_current_weight_aggregated':a,'strategy_b_equal_family':b,'strategy_c_evidence_adjusted':c,
        'experimental_current_weight_aggregated':a['fair'],'experimental_equal_family':b['fair'],
        'experimental_evidence_adjusted':c['fair'],
        'cross_family_governance_modifier':modifier,'family_conflict_flag':conflict,'conflict_preserving_blend':True,
        'family_weighting_sensitivity':sensitivity,'production_family_suppressed':bool(suppressed),
        'suppressed_family':families_suppressed,'suppression_reason':{item['model']:item['exact_production_reason'] for item in suppressed},
        'experimental_restored':bool(suppressed),'single_family_numeric_stability':stability,
        'family_confidence_cap_recommended':single and governance.get('growth_overlap_risk')=='HIGH',
        'growth_overlap_risk':governance.get('growth_overlap_risk'),'capital_structure_flags':governance.get('capital_structure_flags',[]),
        'family_weighting_governance':recommendation,
        'limitation':'Family weighting cannot introduce independent evidence or repair a missing capital-structure/cashflow model.',
        'scope':'EXPERIMENT_ONLY_NEVER_PRODUCTION_INPUT'}


def experiment_summary(stock):
    experiment=stock.get('experimental_family_blend',{})
    summary={'ticker':stock['ticker'],'production_fair':experiment.get('production_fair'),
        'active_families':experiment.get('active_families'),'executed_families':experiment.get('executed_families'),
        'family_weighting_sensitivity':experiment.get('family_weighting_sensitivity'),
        'suppressed_family':experiment.get('suppressed_family'),
        'family_weighting_governance':experiment.get('family_weighting_governance'),'experiment_status':experiment.get('status')}
    for letter,key in (('A','strategy_a_current_weight_aggregated'),('B','strategy_b_equal_family'),('C','strategy_c_evidence_adjusted')):
        summary[letter+'_fair']=experiment.get(key,{}).get('fair')
        summary[letter+'_difference_pct']=experiment.get(key,{}).get('difference_vs_production_pct')
    return summary
