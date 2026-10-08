"""V4.6 post-valuation reliability policy; never revalues or changes model weights."""
from copy import deepcopy
from independent_evidence_governance import independent_evidence_audit
from valuation_primitives import fnum

VERSION='v4.6.1'
APPLIED_METADATA={
    'status':'APPLIED_TO_PRODUCTION_RELIABILITY',
    'governance_scope':'RELIABILITY_CONFIDENCE_AND_EXIT',
    'fair_value_effect':'NONE',
    'production_effect':'RELIABILITY_CONFIDENCE_PRECISE_EXIT',
    'governance_input_source':'V4.5_STRUCTURAL_GOVERNANCE',
}
SEVERITY_RANK={'NONE':0,'LOW':1,'MODERATE':2,'HIGH':3,'CRITICAL':4}
PENALTIES={'NONE':0,'LOW':-5,'MODERATE':-10,'HIGH':-15,'CRITICAL':-20}
CEILINGS={'NONE':'NONE','LOW':'HIGH','MODERATE':'MEDIUM','HIGH':'MEDIUM','CRITICAL':'LOW'}
CONFIDENCE_RANK={'UNAVAILABLE':0,'LOW':1,'MEDIUM':2,'HIGH':3}
SECONDARY_PENALTY=-5
TOTAL_PENALTY_CAP=-25


def cap_confidence(existing,ceiling):
    if ceiling=='NONE' or existing not in CONFIDENCE_RANK:return existing
    return min((existing,ceiling),key=CONFIDENCE_RANK.get)


def evaluate_structural_governance(g,existing_penalties=()):
    """Highest severity wins; one secondary at most, no ticker/price/benchmark inputs."""
    candidates=[('NONE',None)]
    ready=g.get('structural_valuation_readiness');material=g.get('suppression_materiality')
    suppressed=bool(g.get('suppressed_families'))
    conflict=g.get('cross_family_status')=='CROSS_FAMILY_DISAGREEMENT'
    if ready=='CROSS_FAMILY_CONFLICT_SUPPRESSED':
        candidates.append(('CRITICAL' if material=='HIGH' else 'HIGH' if material=='MODERATE' else 'MODERATE','independent_family_suppressed'))
    if conflict and not suppressed:candidates.append(('MODERATE','cross_family_conflict'))
    if g.get('structural_gaps'):candidates.append(('MODERATE','structural_gap'))
    if g.get('active_family_count')==1:candidates.append(('LOW','structural_concentration'))
    if g.get('active_family_count')==1 and g.get('growth_overlap_risk')=='HIGH':
        candidates.append(('MODERATE','high_growth_overlap'))
    severity,code=max(candidates,key=lambda p:SEVERITY_RANK[p[0]])
    overlap=conflict and any(p.get('code') in ('dispersion_high','dispersion_very_high') for p in existing_penalties)
    secondary_candidates=[]
    if g.get('growth_overlap_risk')=='HIGH' and g.get('active_family_count')==1:
        secondary_candidates.append('high_growth_overlap')
    if g.get('structural_gaps') and severity!='CRITICAL':secondary_candidates.append('structural_gap')
    # A driver already used as primary cannot be charged as secondary. A growth
    # gap confirms the same forecast-overlap driver, so it also cannot be added.
    rejected=[];eligible=[]
    for candidate in secondary_candidates:
        same_growth=(candidate=='structural_gap' and code=='high_growth_overlap' and
            set(g.get('structural_gaps',[]))<= {'FORECAST_GROWTH_WITHOUT_INDEPENDENT_CASH_FLOW_CONFIRMATION'})
        if candidate==code or same_growth:rejected.append({'code':candidate,'reason':'already_captured_by_primary'})
        else:eligible.append(candidate)
    secondary_code=eligible[0] if eligible else None
    rejected.extend({'code':c,'reason':'maximum_one_secondary'} for c in eligible[1:])
    if overlap:rejected.append({'code':'cross_family_conflict_secondary','reason':'existing_high_dispersion_captures_conflict'})
    secondary=SECONDARY_PENALTY if secondary_code else 0
    total=max(TOTAL_PENALTY_CAP,PENALTIES[severity]+secondary)
    warnings=[]
    if g.get('active_family_count')==1:warnings.append('STRUCTURAL_EVIDENCE_CONCENTRATION')
    if conflict:warnings.append('CROSS_FAMILY_DISAGREEMENT')
    if suppressed:warnings.append('INDEPENDENT_FAMILY_SUPPRESSED')
    if suppressed and material=='HIGH':warnings.append('HIGH_MATERIALITY_FAMILY_CONFLICT')
    gaps=g.get('structural_gaps',[])
    if 'CAPITAL_STRUCTURE_WITHOUT_INDEPENDENT_VALUATION_FAMILY' in gaps:warnings.append('CAPITAL_STRUCTURE_UNCONFIRMED')
    if g.get('growth_overlap_risk')=='HIGH':warnings.append('GROWTH_SIGNAL_OVERLAP')
    if any('CASH_FLOW_CONFIRMATION' in s for s in gaps):warnings.append('INDEPENDENT_CASH_FLOW_CONFIRMATION_MISSING')
    block=severity in ('HIGH','CRITICAL') or (severity=='MODERATE' and (g.get('active_family_count')==1 or conflict or bool(gaps)))
    if severity=='CRITICAL':
        explanation='存在被 production outlier 规则排除的独立现金流估值家族，且其与当前 earnings-family 估值存在高物质性冲突。当前 fair 未因此调整，但精确退出价格已禁用。'
    elif conflict:explanation='当前估值由不同估值家族支持，但其中值存在显著冲突，结构可靠性受限。'
    elif g.get('active_family_count')==1:
        explanation='当前估值主要由同一模型家族支持，独立证据有限。'
        if 'CAPITAL_STRUCTURE_UNCONFIRMED' in warnings:explanation+='资本结构风险未被独立估值家族确认。'
        if 'GROWTH_SIGNAL_OVERLAP' in warnings:explanation+='增长信号重叠，缺少独立现金流确认。'
        if 'CAPEX_DISTORTION_REMOVES_INDEPENDENT_CASH_FLOW_CONFIRMATION' in gaps:explanation+='资本开支失真限制了独立现金流确认。'
    else:explanation='结构性证据未触发额外可靠性限制。'
    entries=[]
    if code:entries.append({'code':code,'delta':PENALTIES[severity],'role':'primary'})
    if secondary_code:entries.append({'code':secondary_code,'delta':secondary,'role':'secondary'})
    return {**deepcopy(g),'severity':severity,'structural_penalty':PENALTIES[severity],
        'secondary_penalty':secondary,'total_structural_penalty':total,'penalties':entries,
        'confidence_ceiling':CEILINGS[severity],'precise_exit_block':bool(block),'warnings':warnings,
        'structural_explanation':explanation,'penalty_overlap_guard':{'overlap_detected':overlap or bool(rejected),
        'suppressed_secondary_penalties':rejected},'reliability_governance_version':VERSION}


def govern_blend(ticker,financials,blend):
    """Called after unchanged valuation and buy-zone construction; no storage IO."""
    if blend.get('reliability_governance_version')==VERSION:return blend
    if fnum(blend.get('fair')) is None:return blend
    out=deepcopy(blend)
    primitive_blend=deepcopy(blend)
    primitive_blend['models']={n:m for n,m in (blend.get('models') or {}).items() if n!='peer_comparable'}
    primitive_blend['included']=[n for n in blend.get('included',[]) if n!='peer_comparable']
    g=independent_evidence_audit({'ticker':ticker,'source_status':'live',
        'normalized_inputs':financials,'blend':primitive_blend,
        'models_before_outlier':{n:m for n,m in blend.get('models_before_outlier',{}).items() if n!='peer_comparable'}})
    rel=out.get('reliability') or {}
    structural=evaluate_structural_governance(g,rel.get('penalties') or [])
    structural['scope']='PRODUCTION_RELIABILITY_CONFIDENCE_AND_EXIT_ONLY'
    structural.update(APPLIED_METADATA)
    before_score=fnum(rel.get('reliability_score'));before_conf=out.get('confidence')
    score=max(0,min(100,before_score+structural['total_structural_penalty'])) if before_score is not None else None
    # Reuse the unchanged production score thresholds and then apply the ceiling.
    score_conf=before_conf
    if score is not None:
        if score<65:score_conf=cap_confidence(score_conf,'LOW')
        elif score<85:score_conf=cap_confidence(score_conf,'MEDIUM')
    confidence=cap_confidence(score_conf,structural['confidence_ceiling'])
    existing_exit=deepcopy(out.get('exit_zone'))
    if existing_exit:
        from valuation_engine import compute_exit_reliability,apply_exit_display_guard
        exit_rel=compute_exit_reliability(confidence,score,out.get('dispersion'),out.get('fair'),out.get('fair_high'))
        eligible=bool(existing_exit.get('eligible_for_precise_exit')) and exit_rel['eligible_for_precise_exit'] and not structural['precise_exit_block']
        exit_rel['eligible_for_precise_exit']=eligible
        if not eligible:
            exit_rel['display_mode']='qualitative'
            if structural['precise_exit_block']:exit_rel['reason_codes']=list(exit_rel.get('reason_codes') or [])+['structural_governance_blocks_precise_exit']
        out['exit_zone']=apply_exit_display_guard(existing_exit,exit_rel)
    rel.update(reliability_score=score,overall_confidence=confidence,structural_governance=structural,
        structural_reliability_penalties=structural['penalties'],structural_explanation=structural['structural_explanation'],
        reliability_governance_version=VERSION)
    out.update(reliability=rel,confidence=confidence,overall_confidence=confidence,
        structural_governance=structural,structural_reliability_penalties=structural['penalties'],
        structural_confidence_ceiling=structural['confidence_ceiling'],structural_precise_exit_block=structural['precise_exit_block'],
        structural_warnings=structural['warnings'],reliability_governance_version=VERSION)
    from valuation_engine import primary_valuation_view
    out['view']=primary_valuation_view(out)
    out['reliability_governance_audit']={'production_fair_before':blend['fair'],'production_fair_after':out['fair'],
        'fair_before':blend['fair'],'fair_after':out['fair'],'fair_unchanged':blend['fair']==out['fair'],
        'reliability_before':before_score,'reliability_after':score,'confidence_before':before_conf,'confidence_after':confidence,
        'precise_exit_before':bool((existing_exit or {}).get('eligible_for_precise_exit')),
        'precise_exit_after':bool((out.get('exit_zone') or {}).get('eligible_for_precise_exit')),
        'structural_governance':structural,'invariants':{k:out.get(k)==blend.get(k) for k in
            ('fair','fair_low','fair_high','blended_low','blended_mid','blended_high','included','included_models','weights_used','models','excluded','mos','zones','peer_comparable_result','peer_diagnostics')}}
    return out


def render_structural_notice(st,result):
    g=(result.get('blend') or {}).get('structural_governance')
    if not g or g.get('severity')=='NONE':return
    label='结构可靠性：低' if g['severity']=='CRITICAL' else '结构可靠性：需复核'
    st.caption(label)
    with st.expander(label):
        st.write(g.get('structural_explanation',''))
        for label,key in (('估值家族数','active_family_count'),('已观察家族数','observed_family_count'),
            ('有效独立证据','effective_independent_model_count'),('家族分歧','cross_family_status'),
            ('被排除家族','suppressed_families'),('结构缺口','structural_gaps'),('可靠性影响','total_structural_penalty')):
            st.write(label+'：'+str(g.get(key)))
