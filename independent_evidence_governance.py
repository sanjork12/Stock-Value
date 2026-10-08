"""Read-only V4.5.3 signals. Never consumed by production valuation."""
from model_family_governance import governance_audit, SAME_FAMILY_INCREMENT, OUTLIER_REASON
from experimental_family_blend import family_blend_experiment
from valuation_primitives import fnum

EXPORT_FIELDS=('active_family_count','observed_family_count','independent_family_count',
    'effective_independent_model_count','observed_effective_independent_model_count',
    'family_suppression_status','suppressed_families','suppression_materiality',
    'production_vs_conflict_preserving_difference_pct','independent_evidence_status',
    'correlated_family_dominance','production_fair_dependency','structural_gaps',
    'cross_family_conflict_preservation_required','hypothetical_guard_action','structural_valuation_readiness')


def independent_evidence_audit(stock):
    if stock.get('source_status')=='cached_last_reliable' or (
        stock.get('calibration_eligibility') and stock['calibration_eligibility']!='ELIGIBLE'):
        return {'status':'INELIGIBLE_INPUT_STATE','independent_evidence_status':'INSUFFICIENT',
            'hypothetical_guard_action':'NO_ACTION','strategy_c_as_sensitivity_probe':True}
    g=stock.get('correlation_cross_family_governance') or governance_audit(stock)
    experiment=stock.get('experimental_family_blend') or family_blend_experiment(stock)
    blend=stock.get('live_blend',stock.get('blend')) or {}
    after=blend.get('models') or {}
    reps=g.get('family_representatives',{})
    observed=set(reps)
    numeric_names={n for r in reps.values() for n in r['models']}
    families=g.get('model_families',{})
    included=set(blend.get('included') or []) & numeric_names
    active={families[n] for n in included}
    pairs=g.get('pair_dependencies',[])
    pair_status={frozenset(p['models']):p['model_pair_governance_status'] for p in pairs}
    suppressed_models=[{'model':n,'family':families[n],'reason':OUTLIER_REASON}
        for n,m in after.items() if n in numeric_names and n not in included
        and m.get('outlier') and m.get('reason')==OUTLIER_REASON]
    suppressed=sorted({m['family'] for m in suppressed_models if m['family'] not in active})
    suppression=('MULTIPLE_FAMILIES_SUPPRESSED' if len(suppressed)>1 else
        'INDEPENDENT_FAMILY_SUPPRESSED' if suppressed else
        'SAME_FAMILY_MODEL_SUPPRESSED' if suppressed_models else 'NONE')
    effective=fnum(g.get('effective_independent_model_count')) or 0.
    observed_effective=0.
    for r in reps.values():
        prior=[]
        for name in sorted(r['models']):
            observed_effective+=1. if not prior else min(SAME_FAMILY_INCREMENT[
                pair_status.get(frozenset((name,p)),'LOW_DEPENDENCY')] for p in prior)
            prior.append(name)
    # Active evidence count remains the V4.5.1 quantity. Suppressed evidence is
    # reported separately and cannot silently upgrade production confidence.
    evidence=('INSUFFICIENT' if not observed else
        'DIVERSIFIED_BUT_SUPPRESSED' if len(observed)>=2 and len(active)==1 else
        'DIVERSIFIED_EVIDENCE' if len(observed)>=2 and effective>=2 else
        'CONCENTRATED_MULTI_MODEL' if len(observed)==1 and effective>=1.5 else
        'WEAKLY_INDEPENDENT_EVIDENCE' if len(observed)==1 else 'INSUFFICIENT')
    dominance=len(active)==1 and len(included)>=2 and any(
        set(p['models'])<=included and p['model_pair_governance_status']=='HIGH_DEPENDENCY'
        for p in pairs)
    reference=fnum(experiment.get('strategy_c_evidence_adjusted',{}).get('fair'))
    production=fnum(experiment.get('production_fair'))
    delta=(production/reference-1)*100 if suppressed and production is not None and reference is not None and reference>0 else None
    materiality=('NOT_APPLICABLE' if not suppressed else 'UNAVAILABLE' if delta is None else
        'LOW' if abs(delta)<=10 else 'MODERATE' if abs(delta)<=25 else 'HIGH')
    conflict=g.get('cross_family_status')=='CROSS_FAMILY_DISAGREEMENT'
    preserve=len(observed)>=2 and conflict and bool(suppressed)
    dependency=('SUPPRESSED_CROSS_FAMILY_CONFLICT' if suppressed and materiality=='HIGH' else
        'DIVERSIFIED' if len(active)>=2 else 'HIGHLY_CONCENTRATED' if dominance else
        'MODERATELY_CONCENTRATED' if active else None)
    gaps=[]
    if 'CAPITAL_STRUCTURE_NOT_REPRESENTED_IN_ACTIVE_MODELS' in g.get('capital_structure_flags',[]):
        gaps.append('CAPITAL_STRUCTURE_WITHOUT_INDEPENDENT_VALUATION_FAMILY')
    if 'CASH_FLOW_INTRINSIC' not in observed and g.get('growth_overlap_risk')=='HIGH':
        gaps.append('FORECAST_GROWTH_WITHOUT_INDEPENDENT_CASH_FLOW_CONFIRMATION')
    dcf=after.get('normalized_fcf_dcf',{})
    if 'CASH_FLOW_INTRINSIC' not in observed and dcf.get('reason')=='capex_or_fcf_distortion':
        gaps.append('CAPEX_DISTORTION_REMOVES_INDEPENDENT_CASH_FLOW_CONFIRMATION')
    readiness=('CROSS_FAMILY_CONFLICT_SUPPRESSED' if preserve else
        'ACCEPTABLE_WITH_CONFLICT' if len(active)>=2 and conflict else
        'ROBUST' if len(active)>=2 and evidence=='DIVERSIFIED_EVIDENCE' else
        'CONCENTRATED_WITH_STRUCTURAL_GAP' if gaps else 'CONCENTRATED') if observed else None
    action=('NO_ACTION' if not observed else 'REQUIRE_CROSS_FAMILY_REVIEW' if preserve else
        'REQUIRE_INDEPENDENT_FAMILY_REVIEW' if len(active)<2 else
        'REVIEW_ONLY' if conflict else 'BLOCK_PRECISE_CONFIDENCE_UPGRADE' if evidence!='DIVERSIFIED_EVIDENCE' else 'NO_ACTION')
    return {'status':'DIAGNOSTIC_ONLY','active_families':sorted(active),'observed_families':sorted(observed),
        'active_family_count':len(active),'observed_family_count':len(observed),'independent_family_count':len(observed),
        'effective_independent_model_count':effective,'observed_effective_independent_model_count':observed_effective,
        'family_suppression_status':suppression,'suppressed_families':suppressed,'suppressed_models':suppressed_models,
        'suppression_materiality':materiality,'suppressed_family_materiality':materiality,
        'production_vs_conflict_preserving_difference_pct':delta,
        'difference_definition':'(production fair / Strategy C - 1) * 100; Strategy C is the reference denominator; materiality uses absolute value',
        'independent_evidence_status':evidence,'correlated_family_dominance':dominance,
        'production_fair_dependency':dependency,'structural_gaps':gaps,
        'cross_family_status':g.get('cross_family_status'),'growth_overlap_risk':g.get('growth_overlap_risk'),
        'capital_structure_flags':g.get('capital_structure_flags',[]),'numeric_stability':g.get('governance_summary'),
        'cross_family_conflict_preservation_required':preserve,'hypothetical_guard_action':action,
        'structural_valuation_readiness':readiness,'strategy_c_as_sensitivity_probe':True,
        'strategy_c_description':'conflict-preserving diagnostic reference; not recommended production valuation',
        'scope':'DIAGNOSTIC_GOVERNANCE_ONLY_NO_PRODUCTION_EFFECT'}
