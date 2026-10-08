"""Read-only V5.1 closure over the current production batch. No I/O clients."""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from datetime import date
from uuid import uuid4
import csv
import io
from enterprise_evidence import number, period, safe_ratio, build_v49_evidence_adapter, v49_projection
from enterprise_evidence_policy import POLICY as V50_POLICY, COVERAGE_WEIGHTS
from enterprise_evidence_closure_policy import POLICY

_CAPTURE = ContextVar('v51_statement_capture', default=None)
ROWS = {
    'income_stmt': {'ebitda': ('EBITDA',), 'revenue': ('Total Revenue',),
                    'canonical_shares': ('Diluted Average Shares',)},
    'balance_sheet': {'cash': ('Cash Cash Equivalents And Short Term Investments', 'Cash And Cash Equivalents'),
                      'debt': ('Total Debt',), 'shares': ('Ordinary Shares Number',)},
}

@contextmanager
def observe_basis(ticker):
    capture = {'ticker': ticker, 'historical_evidence_acquisition_id': str(uuid4()), 'series': {}}
    token = _CAPTURE.set(capture)
    try:
        yield capture
    finally:
        _CAPTURE.reset(token)

def observe_statement(stage, path, frame):
    capture = _CAPTURE.get()
    if capture is None or stage not in ROWS or frame is None:
        return
    try:
        for field, aliases in ROWS[stage].items():
            row = next((r for r in aliases if r in frame.index), None)
            if row is None:
                continue
            for col in list(frame.columns)[:8]:
                capture['series'].setdefault(field, []).append({
                    'value': number(frame.loc[row, col]), 'period': period(col),
                    'basis': 'FY' if stage == 'income_stmt' else 'LATEST_BALANCE_SHEET',
                    'source': path + '.' + row, 'semantics': row})
    except Exception:
        capture['observation_status'] = 'INCOMPLETE'

def iso(value):
    value = period(value) if value else None
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError):
        return None

def timing(days):
    if days is None: return 'UNKNOWN'
    for key, state in (('gap_good_days', 'GOOD'), ('gap_acceptable_days', 'ACCEPTABLE'), ('gap_max_days', 'STALE_RISK')):
        if days <= POLICY[key]: return state
    return 'INCOMPATIBLE'

def crosscheck(metric, reference):
    if reference is None or metric['value'] is None: return 'INSUFFICIENT_EVIDENCE'
    if metric.get('currency') and reference.get('currency') and metric['currency'] != reference['currency']:
        return 'NOT_COMPARABLE'
    # A current quote and FY flow are informative references, never equal-period numeric comparisons.
    comparison_period=metric['reporting_period'] or metric['reporting_as_of']
    if metric['metric_basis'] != reference.get('basis') or comparison_period != reference.get('period'):
        return 'NOT_COMPARABLE'
    if metric.get('share_basis_semantics') == 'CURRENT_SHARE_COUNT' and 'Average' in reference.get('semantics', ''):
        return 'NOT_COMPARABLE'
    diff, _ = safe_ratio(abs(metric['value'] - reference['value']), abs(reference['value']))
    if diff is None: return 'INSUFFICIENT_EVIDENCE'
    return 'CONSISTENT' if diff <= POLICY['crosscheck_consistent'] else 'MOSTLY_CONSISTENT' if diff <= POLICY['crosscheck_mostly'] else 'MATERIAL_DIFFERENCE'

def metric_basis(stock):
    f = stock.get('normalized_inputs') or {}
    capture = stock.get('metric_basis_evidence_snapshot') or {}
    valid_capture = capture.get('ticker') == stock.get('ticker') and all(capture.get(k) in (None,f.get(k)) for k in ('input_batch_id','fundamentals_acquisition_id'))
    series = capture.get('series', {}) if valid_capture else {}
    historical=stock.get('evidence_snapshot') or {}
    if historical.get('ticker')==stock.get('ticker'):
        series=deepcopy(series)
        for key in ('ebitda','revenue'):
            if not series.get(key):series[key]=deepcopy((historical.get('series',{}).get(key) or {}).get('filtered_series') or [])
    records = {}; reasons = []; missing = []
    lines = {x.get('field'): x for x in f.get('statement_acquisition_provenance') or []}
    for key in ('ebitda', 'revenue', 'cash', 'debt', 'canonical_shares'):
        p = (f.get('acquisition_provenance') or {}).get(key) or {}
        line = lines.get(key) or {}
        basis = (f.get('enterprise_metric_basis') or {}).get(key) or p.get('metric_basis') or line.get('metric_basis')
        basis = basis if isinstance(basis, str) else None
        source = f.get('canonical_shares_source') if key == 'canonical_shares' else p.get('source') or line.get('source')
        end = iso(p.get('period') or line.get('period'))
        asof = iso(p.get('as_of_date') or line.get('as_of_date'))
        references = [r for r in series.get(key, series.get('shares', []) if key == 'canonical_shares' else []) if iso(r.get('period')) and number(r.get('value')) is not None]
        reference = deepcopy(max(references, key=lambda r: r['period'])) if references else None
        value = number(f.get(key))
        if p.get('source')=='existing_missing_assumed_zero': value=None
        if reference and not reference.get('currency'):reference['currency']=f.get('financial_currency')
        # Exact direct source identity may establish reporting semantics; numerical proximity alone cannot.
        if reference and source==reference['source'] and value==reference['value']:
            basis=reference['basis'];end=reference['period'] if key in ('ebitda','revenue') else end
            asof=reference['period'] if key in ('cash','debt','canonical_shares') else asof
        confidence = 'HIGH' if basis in ('TTM', 'FY', 'LATEST_BALANCE_SHEET') and (end or asof) else 'LOW'
        derivation = 'EXPLICIT_METADATA' if basis else 'NO_EXPLICIT_REPORTING_BASIS'
        if key == 'canonical_shares':
            source = source or ''
            basis = f.get('canonical_shares_basis') or basis
            if not basis:
                basis = 'FY_DILUTED_AVG' if 'diluted' in source.lower() else 'CURRENT_MARKET_IMPLIED' if any(s in source.lower() for s in ('implied', 'market_cap', 'marketcap', 'market cap')) else 'CURRENT_PROVIDER_SHARES' if 'sharesoutstanding' in source.lower() or 'shares_outstanding' in source.lower() else 'UNKNOWN'
        if not basis: basis = 'PROVIDER_CURRENT_UNSPECIFIED'
        near = False
        if reference and value is not None:
            relative, _ = safe_ratio(abs(value-reference['value']), abs(reference['value']))
            near = relative is not None and relative <= POLICY['crosscheck_consistent']
            if near and basis == 'PROVIDER_CURRENT_UNSPECIFIED':
                derivation = 'CROSSVALIDATED_NEAR_LATEST_FY' if key in ('ebitda', 'revenue') else 'CROSSVALIDATED_NEAR_LATEST_BALANCE_SHEET'
                if key in ('ebitda', 'revenue'): basis = 'CURRENT_PROVIDER_VALUE_NEAR_LATEST_FY'
                confidence = 'MEDIUM'
        record = {'value': value, 'production_input_value': number(f.get(key)), 'source': source,
            'source_type': p.get('source_type') or line.get('source_type') or 'EXISTING_NORMALIZED_INPUT', 'metric_basis': basis,
            'reporting_period': end, 'reporting_as_of': asof, 'retrieved_at': p.get('acquired_at'),
            'currency': p.get('currency') or f.get('financial_currency'), 'basis_confidence': confidence,
            'basis_derivation': derivation, 'basis_evidence_source': reference.get('source') if reference else source,
            'reference_value': reference.get('value') if reference else None, 'reference': reference,
            'reference_basis':reference.get('basis') if reference else None,
            'reference_reporting_as_of':reference.get('period') if reference else None,
            'provider_current_crossvalidated_to_latest_balance_sheet': near if key in ('cash', 'debt') else False,
            'share_basis_semantics': 'FY_AVERAGE' if basis in ('FY_DILUTED_AVG', 'DILUTED_ANNUAL_AVERAGE') else 'CURRENT_SHARE_COUNT' if key == 'canonical_shares' and basis != 'UNKNOWN' else None,
            'basis_as_of': asof, 'source_confidence': confidence}
        records[key] = record
        if value is None: missing.append(key)
    dates = [iso(r['reporting_as_of'] or r['reporting_period']) for r in records.values()]
    known_dates = [date.fromisoformat(d) for d in dates if d]
    gap = (max(known_dates)-min(known_dates)).days if len(known_dates)==5 else None
    execution_date=iso(stock.get('analysis_generated_at'))
    age_days=max((date.fromisoformat(execution_date)-d).days for d in known_dates) if execution_date and known_dates else None
    currencies = {r['currency'] for k,r in records.items() if k != 'canonical_shares' and r['currency']}
    mismatch = f.get('currency_mismatch') or len(currencies)>1 or bool(f.get('quote_currency') and f.get('financial_currency') and f['quote_currency'] != f['financial_currency'])
    flows_known = all(records[k]['metric_basis'] in ('TTM', 'FY', 'QUOTE_SUMMARY_TTM') for k in ('ebitda', 'revenue'))
    stocks_known = all(records[k]['metric_basis'] in ('LATEST_BALANCE_SHEET', 'CURRENT_BALANCE_SHEET', 'QUOTE_SUMMARY_CURRENT_BALANCE') for k in ('cash', 'debt'))
    shares_known = records['canonical_shares']['metric_basis'] not in ('UNKNOWN', 'PROVIDER_CURRENT_UNSPECIFIED')
    flow_references_supported=all(records[k]['metric_basis'] in ('TTM','FY','QUOTE_SUMMARY_TTM','CURRENT_PROVIDER_VALUE_NEAR_LATEST_FY') for k in ('ebitda','revenue'))
    stock_references_supported=all(records[k]['metric_basis'] in ('LATEST_BALANCE_SHEET','CURRENT_BALANCE_SHEET','QUOTE_SUMMARY_CURRENT_BALANCE') or records[k]['provider_current_crossvalidated_to_latest_balance_sheet'] for k in ('cash','debt'))
    if mismatch or timing(gap)=='INCOMPATIBLE': state='INCOMPATIBLE'
    elif missing or not f.get('quote_currency') or not f.get('financial_currency') or not shares_known: state='INSUFFICIENT_EVIDENCE'
    elif not (flows_known and stocks_known): state='MIXED_BASIS' if flow_references_supported and stock_references_supported else 'INSUFFICIENT_EVIDENCE'
    elif gap is None: state='MIXED_BASIS'
    elif timing(gap)=='STALE_RISK' or timing(age_days) in ('STALE_RISK','INCOMPATIBLE'): state='MIXED_BASIS'
    else: state='MOSTLY_COMPATIBLE' if timing(gap)=='ACCEPTABLE' else 'COMPATIBLE'
    semantic = 'INCOMPATIBLE' if mismatch else 'MIXED_BUT_STANDARD' if flows_known and stocks_known and shares_known else 'MOSTLY_COMPATIBLE' if flow_references_supported and stock_references_supported and shares_known and not missing else 'UNKNOWN'
    if not flows_known: reasons.append('FLOW_BASIS_NOT_PROVEN')
    if semantic=='MOSTLY_COMPATIBLE':reasons.append('REFERENCE_CROSSVALIDATION_ONLY_CURRENT_PERIODS_UNPROVEN_NO_FORMAL_COMPATIBILITY_ADAPTER')
    if gap is None: reasons.append('REPORTING_DATES_INCOMPLETE_RETRIEVAL_NOT_SUBSTITUTED')
    return {'metrics': records, 'metric_basis_crosscheck': {k: crosscheck(r,r['reference']) for k,r in records.items()},
        'enterprise_input_basis_compatibility': state, 'enterprise_bridge_semantic_compatibility': semantic,
        'enterprise_bridge_timing_assessment': timing(max(gap,age_days)) if gap is not None and age_days is not None else timing(gap), 'as_of_gap_days': gap,
        'oldest_reporting_age_days':age_days,
        'flow_period_end': {k:records[k]['reporting_period'] for k in ('ebitda','revenue')},
        'balance_sheet_as_of': {k:records[k]['reporting_as_of'] for k in ('cash','debt')},
        'share_basis_as_of':records['canonical_shares']['reporting_as_of'],
        'canonical_shares_basis':records['canonical_shares']['metric_basis'],
        'reason_codes': reasons, 'missing_inputs':missing,
        'historical_evidence_acquisition_id':(capture.get('historical_evidence_acquisition_id') if valid_capture else None) or historical.get('historical_evidence_acquisition_id')}

def business_structure(stock):
    f=stock.get('normalized_inputs') or {}
    metadata=stock.get('governed_business_structure_metadata') or f.get('governed_business_structure_metadata') or {}
    structural=stock.get('structural_segments') or f.get('structural_segments') or {}
    rows=stock.get('operating_segments') or f.get('operating_segments') or []
    if not rows and structural:
        rows=[{**r,'segment_type':'OPERATING_SEGMENT' if structural.get('basis')=='OPERATING_SEGMENTS' else 'GEOGRAPHIC_SEGMENT' if structural.get('basis')=='GEOGRAPHIC' else 'UNKNOWN_SEGMENT_TYPE',
            'source':r.get('source') or structural.get('source'),'period':r.get('period') or structural.get('period')} for r in structural.get('segments',[]) if isinstance(r,dict)]
    accepted=[]; excluded=[]
    for row in rows:
        if not isinstance(row,dict): continue
        if row.get('segment_type')!='OPERATING_SEGMENT':
            excluded.append({'segment_type':row.get('segment_type','UNKNOWN_SEGMENT_TYPE'),'reason':'NOT_OPERATING_SEGMENT'});continue
        accepted.append({k:deepcopy(row.get(k)) for k in ('label','segment_type','revenue','revenue_share','operating_margin','growth','economic_model','period','source')})
    shares=[number(r['revenue_share']) for r in accepted]
    total=sum(number(r['revenue']) or 0 for r in accepted)
    for r,s in zip(accepted,shares):
        r['revenue_share']=s if s is not None else safe_ratio(r['revenue'],total)[0]
    material=[r for r in accepted if number(r['revenue_share']) is not None and r['revenue_share']>=V50_POLICY.get('segment_material_share',.10)]
    def dispersion(key):
        vals=[number(r[key]) for r in material if number(r[key]) is not None]
        return max(vals)-min(vals) if len(vals)>=2 and len(vals)==len(material) else None
    margin=dispersion('operating_margin');growth=dispersion('growth')
    models={r['economic_model'] for r in material if isinstance(r['economic_model'],str) and r['economic_model']}
    diversity='UNKNOWN' if not material or any(not r['economic_model'] for r in material) else 'LOW' if len(models)==1 else 'MODERATE' if len(models)==2 else 'HIGH'
    status=metadata.get('review_status','PENDING_REVIEW') if metadata else 'INSUFFICIENT_EVIDENCE'
    required=('ticker','effective_date','source_type','source_note','reviewed_by','confidence','business_models','segment_complexity')
    if metadata:
        if metadata.get('ticker')!=stock.get('ticker'): status='CONFLICTING'
        elif status=='REVIEWED' and (any(not metadata.get(k) for k in required) or not iso(metadata.get('effective_date')) or not isinstance(metadata.get('heterogeneous_business_mix'),bool) or not isinstance(metadata.get('company_level_multiple_risk'),bool)): status='PENDING_REVIEW'
        elif status=='REVIEWED' and stock.get('analysis_generated_at') and iso(stock['analysis_generated_at']) and (date.fromisoformat(iso(stock['analysis_generated_at']))-date.fromisoformat(iso(metadata['effective_date']))).days>POLICY['metadata_max_age_days']:status='STALE'
    # Complete, explicitly sourced operating evidence has precedence. No label/name inference.
    supported=bool(material and all(r['source'] and period(r['period']) for r in material) and diversity!='UNKNOWN' and (len(material)==1 or margin is not None and growth is not None) and all(number(r['revenue_share']) is not None and 0<=r['revenue_share']<=1 for r in accepted) and abs(sum(r['revenue_share'] for r in accepted)-1)<=POLICY['crosscheck_consistent'] and len({r['period'] for r in accepted})==1)
    mix='INSUFFICIENT_EVIDENCE';complexity='UNKNOWN';risk=None
    if supported:
        heterogeneity=int(len(models)>1)+int(margin is not None and margin>V50_POLICY['segment_margin_dispersion'])+int(growth is not None and growth>V50_POLICY['segment_growth_dispersion'])
        concentration=max(r['revenue_share'] for r in material)
        mix='HOMOGENEOUS' if heterogeneity==0 else 'MODERATELY_DIVERSE' if heterogeneity==1 or concentration>=POLICY['segment_dominant_share'] else 'HETEROGENEOUS' if heterogeneity==2 else 'HIGHLY_HETEROGENEOUS'
        complexity={'HOMOGENEOUS':'LOW','MODERATELY_DIVERSE':'MODERATE','HETEROGENEOUS':'HIGH','HIGHLY_HETEROGENEOUS':'VERY_HIGH'}[mix]
        risk=mix in ('HETEROGENEOUS','HIGHLY_HETEROGENEOUS');status='REVIEWED'
        if metadata.get('review_status')=='REVIEWED' and metadata.get('heterogeneous_business_mix') is not None and metadata['heterogeneous_business_mix']!=risk:status='CONFLICTING';supported=False
    elif status=='REVIEWED':
        complexity=metadata.get('segment_complexity','UNKNOWN');risk=metadata.get('company_level_multiple_risk')
        mix=metadata.get('business_mix') or ('HIGHLY_HETEROGENEOUS' if metadata.get('heterogeneous_business_mix') is True and complexity=='VERY_HIGH' else 'HETEROGENEOUS' if metadata.get('heterogeneous_business_mix') is True else 'HOMOGENEOUS' if metadata.get('heterogeneous_business_mix') is False and complexity=='LOW' else 'MODERATELY_DIVERSE' if metadata.get('heterogeneous_business_mix') is False and complexity=='MODERATE' else 'INSUFFICIENT_EVIDENCE')
        supported=mix in ('HOMOGENEOUS','MODERATELY_DIVERSE','HETEROGENEOUS','HIGHLY_HETEROGENEOUS') and complexity in ('LOW','MODERATE','HIGH','VERY_HIGH')
    return {'source_status':'SUPPORTED' if supported else 'INSUFFICIENT_EVIDENCE','metadata_review_status':status,
        'segment_basis':'OPERATING_SEGMENT' if accepted else 'UNKNOWN_SEGMENT_TYPE','segments':accepted,'excluded_segments':excluded,
        'material_segment_count':len(material) if accepted else None,'revenue_concentration':max((r['revenue_share'] for r in material),default=None),
        'margin_dispersion':margin,'growth_dispersion':growth,'economic_model_diversity':diversity,
        'business_mix':mix,'segment_complexity':complexity,'company_level_multiple_risk':risk,
        'confidence':'MEDIUM' if supported else 'INSUFFICIENT','source_note':metadata.get('source_note'),
        'governed_metadata':{k:deepcopy(metadata.get(k)) for k in (*required,'review_status','heterogeneous_business_mix','company_level_multiple_risk')},
        'segment_source_audit':{'paths_checked':['operating_segments','normalized_inputs.operating_segments','structural_segments','normalized_inputs.structural_segments','governed_business_structure_metadata'],
            'operating_segment_rows':len(accepted),'excluded_nonoperating_rows':len(excluded),
            'no_added_provider_calls':True},
        'reason_codes':[] if supported else ['NO_REVIEWED_COMPLETE_OPERATING_EVIDENCE'],
        'missing_inputs':[] if supported else ['reviewed_operating_structure'],
        'business_structure_evidence_id':str(uuid4())}

def build_v49_metric_basis_adapter(basis):
    state=basis['enterprise_input_basis_compatibility'];out={}
    if state in ('COMPATIBLE','MOSTLY_COMPATIBLE','INCOMPATIBLE'):
        out['enterprise_input_basis_compatible']=state!='INCOMPATIBLE'
    for key in ('ebitda','revenue'):
        r=basis['metrics'][key]
        if r['metric_basis'] in ('TTM','FY') and r['basis_confidence'] in ('HIGH','MEDIUM'):out[key+'_metric_basis']=r['metric_basis']
    return out

def build_v49_business_structure_adapter(business):
    if business['metadata_review_status']!='REVIEWED' or business['source_status']!='SUPPORTED':return {}
    mix=business['business_mix']
    return {'heterogeneous_business_mix':mix in ('HETEROGENEOUS','HIGHLY_HETEROGENEOUS'),
        'business_mix_warning':{'HOMOGENEOUS':'NONE','MODERATELY_DIVERSE':'POSSIBLE_HETEROGENEITY','HETEROGENEOUS':'EXPLICIT_HETEROGENEITY','HIGHLY_HETEROGENEOUS':'COMPANY_LEVEL_MULTIPLE_RISK'}[mix],
        'segment_complexity':business['segment_complexity'],'company_level_multiple_risk':business['company_level_multiple_risk']}

def close_stock(stock, batch_eligibility=None):
    from enterprise_family_suitability import suitability_audit
    original=deepcopy(stock)
    e=stock.get('enterprise_structural_evidence') or {}
    if not e:raise ValueError('V5.0 completion required')
    basis=metric_basis(stock);business=business_structure(stock)
    base_adapter=build_v49_evidence_adapter(e)['values']
    if not (e.get('business_mix') or {}).get('reviewed'):
        for key in ('heterogeneous_business_mix','segment_complexity','company_level_multiple_risk','business_mix_warning'):base_adapter.pop(key,None)
    adapter={**base_adapter,**build_v49_metric_basis_adapter(basis),**build_v49_business_structure_adapter(business)}
    private=deepcopy(stock)
    private['enterprise_structural_metadata']={**(private.get('enterprise_structural_metadata') or {}),**adapter,'_evidence_policy_version':'v5.0'}
    f=stock.get('normalized_inputs') or {}
    eligible=bool(e.get('formal_completion_conclusion_allowed') and batch_eligibility=='ELIGIBLE' and
        stock.get('input_batch_id')==f.get('input_batch_id') and stock.get('fundamentals_acquisition_id')==f.get('fundamentals_acquisition_id') and
        f.get('input_batch_id') and f.get('fundamentals_acquisition_id'))
    after=suitability_audit(private,batch_eligibility='ELIGIBLE' if eligible else 'INELIGIBLE')
    if not eligible or not build_v49_business_structure_adapter(business):
        for key in ('ev_ebitda','ev_revenue'):after[key]['production_candidate']='NO'
        after['company_level']['production_candidate']='NO';after['enterprise_family_production_candidate']='NO'
    after['enterprise_family_readiness']='DIAGNOSTIC_ONLY'
    before=deepcopy(stock.get('v49_after') or {})
    projection=v49_projection(after)
    method_delta={}
    for name in ('ev_ebitda','ev_revenue'):
        b=before.get(name) or {};a=projection[name]
        method_delta[name]={'score_before':b.get('score'),'score_after':a.get('score'),
            'component_changes':{k:{'before':(b.get('score_components') or {}).get(k),'after':v} for k,v in (a.get('score_components') or {}).items() if v!=(b.get('score_components') or {}).get(k)}}
    components=deepcopy((e.get('evidence_coverage') or {}).get('components') or {})
    old=deepcopy(components)
    components['business_mix']=max(old.get('business_mix',0),COVERAGE_WEIGHTS['business_mix'] if build_v49_business_structure_adapter(business) else 0)
    components['metric_basis']=max(old.get('metric_basis',0),COVERAGE_WEIGHTS['metric_basis'] if basis['enterprise_input_basis_compatibility'] in ('COMPATIBLE','MOSTLY_COMPATIBLE','INCOMPATIBLE') else COVERAGE_WEIGHTS['metric_basis']*.5 if basis['enterprise_input_basis_compatibility']=='MIXED_BASIS' else 0)
    coverage_before=e.get('evidence_coverage_score',sum(old.values()));coverage_after=coverage_before+sum(components[k]-old.get(k,0) for k in ('business_mix','metric_basis'))
    f=stock.get('normalized_inputs') or {}
    return {'version':'v5.1','mode':'DIAGNOSTIC_ONLY','ticker':stock.get('ticker'),
        'input_batch_id':f.get('input_batch_id'),'fundamentals_acquisition_id':f.get('fundamentals_acquisition_id'),
        'metric_basis_closure':basis,'business_structure_closure':business,
        'coverage_before':coverage_before,'coverage_after':coverage_after,'coverage_delta':coverage_after-coverage_before,
        'coverage_component_delta':{k:{'before':old.get(k,0),'after':components[k],'delta':components[k]-old.get(k,0)} for k in ('business_mix','metric_basis')},
        'v49_before':before,'v49_after':projection,'v49_evidence_delta':{'adapter':adapter,'methods':method_delta,
            'new_basis_evidence':build_v49_metric_basis_adapter(basis),'new_business_evidence':build_v49_business_structure_adapter(business),
            'reason':'Only new supported basis or reviewed business evidence; frozen scoring.'},
        'production_integration_performed':False,'formal_conclusion_allowed':eligible,
        'production_invariants':{'original_stock_unchanged':stock==original},
        'telemetry':{'added_logical_calls':0,'added_provider_calls':0,'statement_reads':sum(len(v) for v in (stock.get('metric_basis_evidence_snapshot') or {}).get('series',{}).values()),'metadata_reads':1,'cache_hits':0}}

def close_report(report):
    out=deepcopy(report)
    for s in out.get('stocks') or []:
        s['enterprise_evidence_closure']=close_stock(s,report.get('batch_calibration_eligibility'))
    out['enterprise_evidence_closure_version']='v5.1'
    return out

def summary(stock):
    c=stock['enterprise_evidence_closure'];b=c['metric_basis_closure'];s=c['business_structure_closure']
    return {'Ticker':stock['ticker'],'Coverage Before':c['coverage_before'],'Coverage After':c['coverage_after'],
        'Metric Basis':b['enterprise_input_basis_compatibility'],'Bridge Timing':b['enterprise_bridge_timing_assessment'],
        'Business Mix':s['business_mix'],'Segment Complexity':s['segment_complexity'],'Business Metadata Status':s['metadata_review_status'],
        'V4.9 Company Before':c['v49_before'].get('company_level',{}).get('suitability'),
        'V4.9 Company After':c['v49_after']['company_level'].get('suitability'),
        'Production Candidate':c['v49_after']['production_candidate'],'Readiness':c['v49_after']['readiness']}

def export_report(report):
    return {'version':'v5.1','mode':'DIAGNOSTIC_ONLY','batch_id':report.get('batch_id'),
        'input_batch_id':report.get('input_batch_id'),'stocks':[deepcopy(s['enterprise_evidence_closure']) for s in report.get('stocks') or []]}

def export_csv(report):
    rows=[summary(s) for s in report.get('stocks') or []];buffer=io.StringIO(newline='')
    if rows:
        writer=csv.DictWriter(buffer,fieldnames=list(rows[0]));writer.writeheader()
        writer.writerows({k:"'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v for k,v in row.items()} for row in rows)
    return buffer.getvalue().encode('utf-8-sig')
