"""V5.2 read-only reporting basis audit. No provider, database or cache clients."""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from datetime import date,datetime,timezone,timedelta
from types import FunctionType
import csv
import io
from enterprise_evidence import number, safe_ratio, v49_projection
from enterprise_evidence_closure import iso, timing
from provider_metric_semantics import POLICY,QUARTERLY_PATHS,REPORTING_EPOCHS,METRICS,registry

_OBSERVER=ContextVar('reporting_basis_evidence',default=None)
ROWS={'ebitda':('EBITDA',),'revenue':('Total Revenue',),
    'cash':('Cash Cash Equivalents And Short Term Investments','Cash And Cash Equivalents'),
    'debt':('Total Debt',),'shares':('Diluted Average Shares','Ordinary Shares Number')}

@contextmanager
def observe_reporting(ticker):
    observed={'ticker':ticker,'provider_fields':{},'series':{},'observed_statement_paths':[]}
    token=_OBSERVER.set(observed)
    try:yield observed
    finally:_OBSERVER.reset(token)

def observe_provider(path,payload):
    observed=_OBSERVER.get()
    if observed is None or path!='ticker.get_info' or not isinstance(payload,dict):return
    try:
        fields={k:number(payload.get(k)) for k in (*REPORTING_EPOCHS,'maxAge','enterpriseValue','totalRevenue','ebitda','totalCash','totalDebt','sharesOutstanding','impliedSharesOutstanding')}
        for key in ('currency','financialCurrency'):
            value=payload.get(key);fields[key]=value if isinstance(value,str) and len(value)==3 and value.isupper() else None
        fields['quoteType']=payload.get('quoteType') if payload.get('quoteType') in ('EQUITY','ETF','MUTUALFUND','INDEX','CRYPTOCURRENCY','FUTURE','CURRENCY') else None
        observed['provider_fields']=fields
    except Exception:observed['observation_status']='INCOMPLETE'

def observe_statement(stage,path,frame):
    observed=_OBSERVER.get()
    if observed is None or frame is None:return
    try:
        if frame.empty:return
        quarterly='quarterly' in path or stage.startswith('quarterly_')
        stage=stage.removeprefix('quarterly_')
        if stage=='financials':stage='income_stmt'
        if stage not in ('income_stmt','balance_sheet','cashflow'):return
        observed['observed_statement_paths'].append(path)
        for metric,aliases in ROWS.items():
            if metric in ('ebitda','revenue') and stage!='income_stmt':continue
            if metric in ('cash','debt') and stage!='balance_sheet':continue
            if metric=='shares' and stage not in ('income_stmt','balance_sheet'):continue
            row=next((r for r in aliases if r in frame.index),None)
            if not row:continue
            for col in list(frame.columns)[:8]:
                observed['series'].setdefault(metric,[]).append({'value':number(frame.loc[row,col]),
                    'period_end':iso(col),'frequency':'QUARTERLY' if quarterly else 'ANNUAL',
                    'accounting_semantics':row,'source':path+'.'+row,'statement_stage':stage})
    except Exception:observed['observation_status']='INCOMPLETE'

def epoch_date(value):
    value=number(value)
    if value is None or value<=0:return None
    try:
        result=datetime.fromtimestamp(value,timezone.utc).date()
        return result.isoformat() if 1970<=result.year<=2100 else None
    except (ValueError,OverflowError,OSError):return None

def capture_snapshot(stock,observed):
    f=stock.get('normalized_inputs') or {};snapshot=deepcopy(observed or {})
    snapshot.update(input_batch_id=f.get('input_batch_id'),fundamentals_acquisition_id=f.get('fundamentals_acquisition_id'),
        retrieved_at=(f.get('acquisition_metadata') or {}).get('acquired_at'),
        canonical_source_path=(f.get('acquisition_metadata') or {}).get('source_path'))
    for rows in snapshot.get('series',{}).values():
        for row in rows:
            row['currency']=f.get('financial_currency')
            row['currency_evidence']='SAME_ACQUISITION_FINANCIAL_CURRENCY'
    return snapshot

def evidence_view(stock):
    f=stock.get('normalized_inputs') or {};snapshot=stock.get('reporting_basis_evidence_snapshot') or {}
    expected={k:f.get(k) for k in ('input_batch_id','fundamentals_acquisition_id')}
    valid=bool(snapshot.get('ticker')==stock.get('ticker') and all(snapshot.get(k)==v and v for k,v in expected.items()))
    snapshot=deepcopy(snapshot) if valid else {'provider_fields':{},'series':{},'observed_statement_paths':[],
        'reason_codes':['REPORTING_EVIDENCE_IDENTITY_UNOBSERVED_OR_MISMATCH']}
    historical=stock.get('evidence_snapshot') or {}
    historical_valid=bool(historical.get('ticker')==stock.get('ticker') and all(historical.get(k)==v and v for k,v in expected.items()))
    if historical_valid:
        for metric in ('ebitda','revenue'):
            if not any(r.get('frequency')=='ANNUAL' for r in snapshot.setdefault('series',{}).get(metric,[])):
                for row in ((historical.get('series') or {}).get(metric) or {}).get('filtered_series',[]):
                    snapshot['series'].setdefault(metric,[]).append({'value':number(row.get('value')),'period_end':iso(row.get('period')),
                        'frequency':'ANNUAL','accounting_semantics':'EBITDA' if metric=='ebitda' else 'Total Revenue',
                        'currency':row.get('currency'),'source':row.get('source'),'statement_stage':'income_stmt'})
    basis_snapshot=stock.get('metric_basis_evidence_snapshot') or {}
    if basis_snapshot.get('ticker')==stock.get('ticker') and all(basis_snapshot.get(k)==v and v for k,v in expected.items()):
        for metric in ('cash','debt','shares','canonical_shares'):
            key='shares' if metric=='canonical_shares' else metric
            if snapshot.setdefault('series',{}).get(key):continue
            for row in basis_snapshot.get('series',{}).get(metric,[]):
                snapshot['series'].setdefault(key,[]).append({'value':number(row.get('value')),'period_end':iso(row.get('period')),
                    'frequency':'ANNUAL','accounting_semantics':row.get('semantics'),'source':row.get('source'),
                    'currency':row.get('currency') or f.get('financial_currency'),'statement_stage':'income_stmt' if metric=='canonical_shares' else 'balance_sheet'})
    snapshot['historical_evidence_acquisition_id']=historical.get('historical_evidence_acquisition_id') if historical_valid else None
    return snapshot

def reporting_metadata(snapshot):
    raw=snapshot.get('provider_fields') or {}
    fields={k:number(raw.get(k)) for k in (*REPORTING_EPOCHS,'maxAge','enterpriseValue','totalRevenue','ebitda','totalCash','totalDebt','sharesOutstanding','impliedSharesOutstanding')}
    for key in ('currency','financialCurrency'):
        v=raw.get(key);fields[key]=v if isinstance(v,str) and len(v)==3 and v.isalpha() and v.isupper() else None
    fields['quoteType']=raw.get('quoteType') if raw.get('quoteType') in ('EQUITY','ETF','MUTUALFUND','INDEX','CRYPTOCURRENCY','FUTURE','CURRENCY') else None
    dates={k:epoch_date(fields.get(k)) for k in REPORTING_EPOCHS}
    balance_dates={r.get('period_end') for k in ('cash','debt') for r in snapshot.get('series',{}).get(k,[]) if r.get('period_end')}
    latest_balance_date=max(balance_dates) if balance_dates else None
    match=bool(dates['mostRecentQuarter'] and dates['mostRecentQuarter']==latest_balance_date)
    return {'raw_fields':deepcopy(fields),'parsed_dates':dates,
        'provider_last_fiscal_year_end':dates['lastFiscalYearEnd'],'provider_most_recent_quarter':dates['mostRecentQuarter'],
        'provider_next_fiscal_year_end':dates['nextFiscalYearEnd'],'retrieved_at':snapshot.get('retrieved_at'),
        'reporting_metadata_confidence':'HIGH' if match else 'MEDIUM' if dates['lastFiscalYearEnd'] or dates['mostRecentQuarter'] else 'INSUFFICIENT',
        'most_recent_quarter_matches_balance_sheet':match,
        'latest_observed_balance_sheet_date':latest_balance_date,
        'reason_codes':['FISCAL_METADATA_SUPPORTS_BUT_DOES_NOT_ALONE_PROVE_METRIC_PERIOD'],
        'quarterly_statement_availability':{path:'ALREADY_OBSERVED' if any(path in p for p in snapshot.get('observed_statement_paths',[])) else 'QUARTERLY_DATA_NOT_ALREADY_AVAILABLE' for path in QUARTERLY_PATHS}}

def reconstruct_ttm(rows):
    rows=[deepcopy(r) for r in rows if r.get('frequency')=='QUARTERLY']
    fail=lambda reason:{'value':None,'period_start':None,'period_end':None,'reason_codes':[reason],'source':[]}
    if len(rows)<4:return fail('INCOMPLETE_QUARTERS')
    if any(not iso(r.get('period_end')) or number(r.get('value')) is None for r in rows):return fail('INVALID_QUARTER_OBSERVATION')
    if len({r['period_end'] for r in rows})!=len(rows):return fail('DUPLICATE_QUARTER')
    rows.sort(key=lambda r:r['period_end']);latest=rows[-4:]
    currencies={r.get('currency') for r in latest};semantics={r.get('accounting_semantics') for r in latest}
    if None in currencies or len(currencies)!=1:return fail('MISSING_OR_MIXED_QUARTER_CURRENCY')
    if None in semantics or len(semantics)!=1:return fail('MISSING_OR_MIXED_ACCOUNTING_SEMANTICS')
    if any(not r.get('source') for r in latest):return fail('QUARTER_SOURCE_NOT_PROVEN')
    gaps=[(date.fromisoformat(b['period_end'])-date.fromisoformat(a['period_end'])).days for a,b in zip(latest,latest[1:])]
    if any(not POLICY['quarter_gap_min_days']<=gap<=POLICY['quarter_gap_max_days'] for gap in gaps):return fail('NONCONTIGUOUS_QUARTERS')
    start=iso(latest[0].get('period_start'))
    if start is None and len(rows)>4:
        previous=rows[-5];gap=(date.fromisoformat(latest[0]['period_end'])-date.fromisoformat(previous['period_end'])).days
        if POLICY['quarter_gap_min_days']<=gap<=POLICY['quarter_gap_max_days']:start=(date.fromisoformat(previous['period_end'])+timedelta(days=1)).isoformat()
    total=number(sum(r['value'] for r in latest))
    if total is None:return fail('NONFINITE_TTM_SUM')
    return {'value':total,'period_start':start,'period_end':latest[-1]['period_end'],
        'source':[r.get('source') for r in latest],'currency':next(iter(currencies)),
        'accounting_semantics':next(iter(semantics)),'reason_codes':[] if start else ['FIRST_QUARTER_START_NOT_EXPLICIT']}

def comparison(value,reference,basis):
    diff,_=safe_ratio(abs(value-reference) if value is not None and reference is not None else None,abs(reference) if reference is not None else None)
    strength='STRONG' if diff is not None and diff<=POLICY['strong_match'] else 'MODERATE' if diff is not None and diff<=POLICY['moderate_match'] else 'NO'
    return {'relative_difference':diff,'support':strength+'_'+basis+'_MATCH' if diff is not None else 'INSUFFICIENT_EVIDENCE'}

def flow_resolution(metric,stock,snapshot,metadata):
    f=stock.get('normalized_inputs') or {};value=number(f.get(metric));provenance=(f.get('acquisition_provenance') or {}).get(metric) or {}
    rows=snapshot.get('series',{}).get(metric,[]);ttm=reconstruct_ttm(rows)
    annual=[r for r in rows if r.get('frequency')=='ANNUAL' and iso(r.get('period_end')) and number(r.get('value')) is not None and f.get('financial_currency') and r.get('currency')==f.get('financial_currency') and r.get('accounting_semantics') in ROWS[metric]]
    fy=max(annual,key=lambda r:r['period_end']) if annual else {}
    annual_conflict=bool(fy and len({(r.get('value'),r.get('accounting_semantics')) for r in annual if r['period_end']==fy['period_end']})>1)
    if annual_conflict:fy={}
    cttm=comparison(value,ttm['value'],'TTM');cfy=comparison(value,number(fy.get('value')),'FY')
    explicit=(f.get('enterprise_metric_basis') or {}).get(metric) or provenance.get('metric_basis')
    explicit_end=iso(provenance.get('period') or provenance.get('as_of_date'))
    candidates=[{'basis':basis,'value':ref.get('value'),'period_end':ref.get('period_end'),**comp} for basis,ref,comp in (('TTM',ttm,cttm),('LATEST_FY',fy,cfy))]
    tmatch=cttm['support'].startswith(('STRONG_','MODERATE_')) and ttm.get('currency')==f.get('financial_currency');fmatch=cfy['support'].startswith(('STRONG_','MODERATE_'))
    basis='CURRENT_PROVIDER_UNSPECIFIED' if value is not None else 'INSUFFICIENT_EVIDENCE';confidence='LOW' if value is not None else 'INSUFFICIENT';end=None;reasons=[]
    if fy and provenance.get('source')==fy.get('source') and value==number(fy.get('value')):
        basis='LATEST_FY';end=fy['period_end'];confidence='HIGH';reasons=['DIRECT_FY_STATEMENT_SOURCE_IDENTITY']
    elif explicit in ('TTM','FY') and explicit_end:
        basis='TTM' if explicit=='TTM' else 'LATEST_FY';end=explicit_end;confidence='HIGH';reasons=['EXPLICIT_SAME_ACQUISITION_METRIC_PERIOD_METADATA']
    elif tmatch and fmatch:
        basis='AMBIGUOUS_TTM_VS_FY';confidence='MEDIUM';reasons=['AMBIGUOUS_TTM_VS_FY_MATCH']
    elif tmatch and ttm.get('currency')==f.get('financial_currency'):
        basis='TTM';end=ttm['period_end'];confidence='HIGH' if cttm['support']=='STRONG_TTM_MATCH' else 'MEDIUM';reasons=['FOUR_QUARTER_TTM_RECONSTRUCTION',cttm['support']]
    elif fmatch and fy.get('period_end')==metadata['provider_last_fiscal_year_end'] and metadata['provider_most_recent_quarter']==fy.get('period_end'):
        basis='LATEST_FY';end=fy['period_end'];confidence='MEDIUM';reasons=['FY_NUMERIC_MATCH','LAST_FISCAL_YEAR_END_AND_MOST_RECENT_QUARTER_MATCH_REFERENCE']
    else:reasons=['FY_MATCH_NOT_SUFFICIENT_TO_PROVE_PERIOD' if fmatch else 'NO_PROVEN_CURRENT_FLOW_BASIS']+ttm['reason_codes']
    if annual_conflict:reasons.append('CONFLICTING_LATEST_FY_REFERENCES')
    return {'input_value':value,'production_input_value':deepcopy(f.get(metric)),'input_source':provenance.get('source'),
        'raw_provider_value':(snapshot.get('provider_fields') or {}).get(METRICS[metric][0]),
        'value_confidence':'HIGH' if provenance.get('source_type')=='DIRECT' else 'INSUFFICIENT' if value is None else 'MEDIUM',
        'candidate_bases':candidates,'candidate_reference_values':{'TTM':ttm.get('value'),'LATEST_FY':fy.get('value')},
        'comparison_results':{'TTM':cttm,'LATEST_FY':cfy},'selected_basis':basis,'resolved_basis':basis,
        'resolved_period_end':end,'confidence':confidence,'basis_confidence':confidence,'selection_reason':reasons,
        'unresolved_reasons':reasons if end is None else [],'ttm_reconstruction_value':ttm.get('value'),
        'ttm_reconstruction_period_start':ttm.get('period_start'),'ttm_reconstruction_period_end':ttm.get('period_end'),
        'ttm_reconstruction_source':ttm.get('source'),'currency':f.get('financial_currency')}

def stock_resolution(metric,stock,snapshot,metadata):
    f=stock.get('normalized_inputs') or {};p=(f.get('acquisition_provenance') or {}).get(metric) or {}
    value=number(f.get(metric));raw=snapshot.get('provider_fields') or {}
    rows=[r for r in snapshot.get('series',{}).get(metric,[]) if iso(r.get('period_end')) and number(r.get('value')) is not None]
    reference=max(rows,key=lambda r:r['period_end']) if rows else {}
    reference_conflict=bool(reference and len({(r.get('value'),r.get('accounting_semantics'),r.get('currency')) for r in rows if r['period_end']==reference['period_end']})>1)
    if reference_conflict:reference={}
    semantics=reference.get('accounting_semantics');provider_field=METRICS[metric][0]
    semantic='SEMANTICS_MATCH' if metric=='debt' and semantics=='Total Debt' else 'SEMANTICS_BROADLY_COMPATIBLE' if metric=='cash' and semantics=='Cash Cash Equivalents And Short Term Investments' else 'SEMANTICS_DIFFER' if semantics else 'UNKNOWN'
    comp=comparison(value,number(reference.get('value')),'BS');diff=comp['relative_difference']
    currency_ok=bool(f.get('financial_currency') and reference.get('currency')==f.get('financial_currency'))
    direct=bool(reference and p.get('source')==reference.get('source') and value==number(reference.get('value')))
    basis='INSUFFICIENT_EVIDENCE' if value is None else 'CURRENT_PROVIDER_UNSPECIFIED';state='INSUFFICIENT_EVIDENCE';confidence='LOW' if value is not None else 'INSUFFICIENT';asof=None;reasons=[]
    if semantic=='SEMANTICS_DIFFER':basis='SEMANTICALLY_AMBIGUOUS';state='SEMANTICALLY_NOT_COMPARABLE';reasons=['CASH_OR_DEBT_LINE_SEMANTICS_DIFFER']
    elif reference and not currency_ok:state='SEMANTICALLY_NOT_COMPARABLE';reasons=['REFERENCE_CURRENCY_UNSAFE']
    elif direct and semantic in ('SEMANTICS_MATCH','SEMANTICS_BROADLY_COMPATIBLE'):
        basis='LATEST_BALANCE_SHEET';state='LATEST_BALANCE_SHEET_MATCH';confidence='HIGH';asof=reference['period_end'];reasons=['DIRECT_STATEMENT_SOURCE_IDENTITY']
    elif diff is not None and diff<=POLICY['strong_match'] and semantic in ('SEMANTICS_MATCH','SEMANTICS_BROADLY_COMPATIBLE') and currency_ok:
        basis='CURRENT_PROVIDER_CROSSVALIDATED_TO_LATEST_BS';state='CURRENT_PROVIDER_NEAR_LATEST_BALANCE_SHEET';confidence='MEDIUM';reasons=['VALUE_AND_SEMANTIC_CROSSVALIDATION_CURRENT_DATE_NOT_PROVEN']
    elif diff is not None and diff>POLICY['stock_material_difference']:
        state='CURRENT_PROVIDER_MATERIAL_DIFFERENCE';reasons=['MATERIAL_VALUE_DIFFERENCE_NO_DATE_INFERENCE']
    else:reasons=['NO_SUPPORTED_STOCK_BASIS']
    return {'input_value':value,'production_input_value':deepcopy(f.get(metric)),'input_source':p.get('source'),
        'raw_provider_value':raw.get(provider_field),'value_confidence':'INSUFFICIENT' if value is None else 'HIGH' if p.get('source_type')=='DIRECT' else 'MEDIUM',
        'reference_value':reference.get('value'),'reference_source':reference.get('source'),'latest_balance_sheet_as_of':reference.get('period_end'),
        'reference_currency':reference.get('currency'),'semantics_comparison':semantic,'reference_semantics':semantics,
        'candidate_bases':[{'basis':'LATEST_BALANCE_SHEET','value':reference.get('value'),'period_end':reference.get('period_end'),**comp}],
        'candidate_reference_values':{'LATEST_BALANCE_SHEET':reference.get('value')},'comparison_results':comp,
        'selected_basis':basis,'resolved_basis':basis,'resolution_state':state,'resolved_as_of':asof,
        'confidence':confidence,'basis_confidence':confidence,'selection_reason':reasons,
        'unresolved_reasons':(['CONFLICTING_LATEST_BALANCE_SHEET_REFERENCES'] if reference_conflict else [])+([] if asof else ['CURRENT_PROVIDER_REPORTING_DATE_NOT_PROVEN']),
        'currency':f.get('financial_currency')}

def shares_resolution(stock,snapshot):
    f=stock.get('normalized_inputs') or {};p=(f.get('acquisition_provenance') or {}).get('canonical_shares') or {}
    source=f.get('canonical_shares_source') or '';s=source.lower();value=number(f.get('canonical_shares'))
    basis='CURRENT_MARKET_IMPLIED' if any(k in s for k in ('implied','market_cap','marketcap','market cap')) else 'FY_DILUTED_AVERAGE' if 'diluted' in s else 'CURRENT_PROVIDER_SHARES' if 'sharesoutstanding' in s or 'shares_outstanding' in s else 'LATEST_BALANCE_SHEET_SHARES' if 'balance_sheet' in s else 'INSUFFICIENT_EVIDENCE'
    if value is None:basis='INSUFFICIENT_EVIDENCE'
    acquired=snapshot.get('retrieved_at') or (f.get('acquisition_metadata') or {}).get('acquired_at')
    market=basis in ('CURRENT_MARKET_IMPLIED','CURRENT_PROVIDER_SHARES')
    asof=acquired if market and iso(acquired) else iso(p.get('period') or p.get('as_of_date')) if not market else None
    refs=[deepcopy(r) for r in snapshot.get('series',{}).get('shares',[]) if number(r.get('value')) is not None]
    diluted=[r for r in refs if r.get('accounting_semantics')=='Diluted Average Shares' and r.get('frequency')=='ANNUAL']
    reference=max(diluted,key=lambda r:r.get('period_end') or '') if diluted else {}
    return {'input_value':value,'production_input_value':deepcopy(f.get('canonical_shares')),'input_source':source,
        'selected_basis':basis,'resolved_basis':basis,'basis_as_of':asof,'basis_as_of_type':'ACQUISITION_TIME_MARKET_SNAPSHOT' if market and asof else 'REPORTING_DATE' if asof else 'UNKNOWN',
        'reporting_period':None if market else asof,'shares_snapshot_at':asof if market else None,
        'reference':reference,'candidate_reference_values':{'FY_DILUTED_AVERAGE':reference.get('value')},
        'comparison_results':comparison(value,number(reference.get('value')),'FY_AVERAGE'),
        'metric_basis_crosscheck':'EXPECTED_DIFFERENT_BASIS' if market and reference else 'INSUFFICIENT_EVIDENCE',
        'value_confidence':'INSUFFICIENT' if value is None else 'HIGH' if basis!='INSUFFICIENT_EVIDENCE' else 'LOW',
        'confidence':'MEDIUM' if basis!='INSUFFICIENT_EVIDENCE' and asof else 'LOW','basis_confidence':'MEDIUM' if asof else 'LOW',
        'selection_reason':['CURRENT_COUNT_AND_FY_AVERAGE_ARE_DISTINCT'] if market else ['EXPLICIT_SHARE_SOURCE_SEMANTICS'],
        'unresolved_reasons':[] if asof else ['SHARE_BASIS_AS_OF_UNKNOWN']}

def bridge_resolution(stock,flows,stocks,shares):
    f=stock.get('normalized_inputs') or {};q=f.get('quote_currency');currency_safe=bool(isinstance(q,str) and len(q)==3 and q.isalpha() and q.isupper() and q==f.get('financial_currency') and not f.get('currency_mismatch'))
    stock_supported=all(r['selected_basis'] in ('LATEST_BALANCE_SHEET','CURRENT_PROVIDER_CROSSVALIDATED_TO_LATEST_BS') for r in stocks.values())
    fatal=not currency_safe or any(r['semantics_comparison']=='SEMANTICS_DIFFER' for r in stocks.values())
    results={};timings={};gaps={}
    for name,flow in flows.items():
        dates=[flow['resolved_period_end']]+[r['resolved_as_of'] or r['latest_balance_sheet_as_of'] if r['selected_basis'] in ('LATEST_BALANCE_SHEET','CURRENT_PROVIDER_CROSSVALIDATED_TO_LATEST_BS') else None for r in stocks.values()]
        dates=[iso(d) for d in dates];sharedate=iso(shares['basis_as_of'])
        if all(dates) and sharedate:
            parsed=[date.fromisoformat(d) for d in dates]+[date.fromisoformat(sharedate)];gap=(max(parsed)-min(parsed)).days
        else:gap=None
        t=timing(gap);gaps[name]=gap;timings[name]=t
        flow_known=flow['selected_basis'] in ('TTM','LATEST_FY') and flow['resolved_period_end']
        if fatal or t=='INCOMPATIBLE':state='INCOMPATIBLE'
        elif not (flow_known and stock_supported and shares['selected_basis']!='INSUFFICIENT_EVIDENCE'):state='INSUFFICIENT_EVIDENCE'
        elif t in ('UNKNOWN','STALE_RISK'):state='MIXED_BASIS'
        elif all(r['selected_basis']=='LATEST_BALANCE_SHEET' for r in stocks.values()) and t=='GOOD':state='COMPATIBLE'
        else:state='MOSTLY_COMPATIBLE'
        results['ev_'+name+'_basis_compatibility']=state
    resolved=[v for v in results.values() if v in ('COMPATIBLE','MOSTLY_COMPATIBLE','MIXED_BASIS')]
    overall='INCOMPATIBLE' if fatal or all(v=='INCOMPATIBLE' for v in results.values()) else 'COMPATIBLE' if all(v=='COMPATIBLE' for v in results.values()) else 'MOSTLY_COMPATIBLE' if len(resolved)==2 and all(v in ('COMPATIBLE','MOSTLY_COMPATIBLE') for v in results.values()) else 'MIXED_BASIS' if resolved else 'INSUFFICIENT_EVIDENCE'
    complete=len(resolved)==2
    semantic='INCOMPATIBLE' if fatal or overall=='INCOMPATIBLE' else 'MIXED_BUT_STANDARD' if complete and all(flow['selected_basis']=='TTM' for flow in flows.values()) else 'COMPATIBLE' if overall=='COMPATIBLE' else 'MOSTLY_COMPATIBLE' if resolved else 'INSUFFICIENT_EVIDENCE'
    known_gaps=[v for v in gaps.values() if v is not None]
    share_gaps={k:abs((date.fromisoformat(iso(shares['basis_as_of']))-date.fromisoformat(v['resolved_period_end'])).days) if iso(shares['basis_as_of']) and v['resolved_period_end'] else None for k,v in flows.items()}
    return {**results,'enterprise_input_basis_compatibility':overall,'enterprise_bridge_semantic_compatibility':semantic,
        'enterprise_bridge_timing_assessment':timing(max(known_gaps)) if len(known_gaps)==2 else 'UNKNOWN',
        'method_timing':timings,'method_as_of_gap_days':gaps,'share_snapshot_gap_days':share_gaps,
        'shares_snapshot_time_semantics':shares['basis_as_of_type'],'currency_safe':currency_safe,
        'reason_codes':['REFERENCE_BS_DATE_USED_FOR_CROSSVALIDATED_CURRENT_VALUES_NOT_ASSERTED_AS_PROVIDER_DATE'] if any(r['selected_basis']=='CURRENT_PROVIDER_CROSSVALIDATED_TO_LATEST_BS' for r in stocks.values()) else []}

def build_v49_reporting_basis_adapter(flows,bridge):
    adapter={'enterprise_bridge_timing':bridge['enterprise_bridge_timing_assessment']}
    for key,r in flows.items():
        if r['selected_basis'] in ('TTM','LATEST_FY'):adapter[key+'_metric_basis']='FY' if r['selected_basis']=='LATEST_FY' else 'TTM'
        state=bridge['ev_'+key+'_basis_compatibility']
        if state in ('COMPATIBLE','MOSTLY_COMPATIBLE','INCOMPATIBLE'):adapter['ev_'+key+'_basis_compatible']=state!='INCOMPATIBLE'
    return adapter

def diagnostic_v49(stock,closure,adapter,eligible):
    import enterprise_family_suitability as v49
    private=deepcopy(stock)
    inherited=(closure.get('v49_evidence_delta') or {}).get('adapter') or {}
    private['enterprise_structural_metadata']={**(private.get('enterprise_structural_metadata') or {}),**inherited,**adapter,'_evidence_policy_version':'v5.0'}
    for obj in (private['enterprise_structural_metadata'],private.get('normalized_inputs') or {},private.get('profile_assumptions') or {}):
        obj.pop('enterprise_input_basis_compatible',None)
    def method(name,stock,policy,ev,eligible):
        ev=deepcopy(ev);ev['explicit']['enterprise_input_basis_compatible']={'value':adapter.get(name+'_basis_compatible'),'source':'v5.2.method_specific_basis'}
        return v49.method_audit(name,stock,policy,ev,eligible)
    env=dict(v49.suitability_audit.__globals__);env['method_audit']=method
    runner=FunctionType(v49.suitability_audit.__code__,env,v49.suitability_audit.__name__,v49.suitability_audit.__defaults__,v49.suitability_audit.__closure__)
    runner.__kwdefaults__=v49.suitability_audit.__kwdefaults__
    after=runner(private,batch_eligibility='ELIGIBLE' if eligible else 'INELIGIBLE')
    # Preserve V5.1 candidate ceilings. Basis coverage cannot independently unlock a candidate.
    for key in ('ev_ebitda','ev_revenue'):
        if ((closure.get('v49_after') or {}).get(key) or {}).get('production_candidate')=='NO':after[key]['production_candidate']='NO'
    if (closure.get('v49_after') or {}).get('production_candidate')=='NO' or not eligible:
        after['company_level']['production_candidate']='NO';after['enterprise_family_production_candidate']='NO'
    after['enterprise_family_readiness']='DIAGNOSTIC_ONLY'
    return v49_projection(after)

def resolve_stock(stock,batch_eligibility=None):
    original=deepcopy(stock);closure=stock.get('enterprise_evidence_closure')
    if not closure:raise ValueError('V5.1 evidence closure required')
    snapshot=evidence_view(stock);metadata=reporting_metadata(snapshot)
    flows={key:flow_resolution(key,stock,snapshot,metadata) for key in ('ebitda','revenue')}
    stocks={key:stock_resolution(key,stock,snapshot,metadata) for key in ('cash','debt')};shares=shares_resolution(stock,snapshot)
    bridge=bridge_resolution(stock,flows,stocks,shares);adapter=build_v49_reporting_basis_adapter(flows,bridge)
    f=stock.get('normalized_inputs') or {};eligible=bool(batch_eligibility=='ELIGIBLE' and closure.get('formal_conclusion_allowed') and
        closure.get('ticker')==stock.get('ticker') and not snapshot.get('reason_codes') and all(closure.get(k)==f.get(k) and f.get(k) and stock.get(k)==f.get(k) for k in ('input_batch_id','fundamentals_acquisition_id')))
    before=deepcopy(closure['v49_after']);after=diagnostic_v49(stock,closure,adapter,eligible)
    states=[bridge['ev_'+k+'_basis_compatibility'] for k in flows]
    credit=POLICY['metric_basis_full_credit'] if all(s in ('COMPATIBLE','MOSTLY_COMPATIBLE') for s in states) else POLICY['metric_basis_partial_credit'] if any(s in ('COMPATIBLE','MOSTLY_COMPATIBLE','MIXED_BASIS') for s in states) else POLICY['metric_basis_no_credit']
    prior=((closure.get('coverage_component_delta') or {}).get('metric_basis') or {}).get('after',0)
    credit=max(prior,credit);coverage_before=closure['coverage_after'];coverage_after=coverage_before+credit-prior
    return {'version':'v5.2','mode':'DIAGNOSTIC_ONLY','ticker':stock.get('ticker'),
        'input_batch_id':f.get('input_batch_id'),'fundamentals_acquisition_id':f.get('fundamentals_acquisition_id'),
        'historical_evidence_acquisition_id':snapshot.get('historical_evidence_acquisition_id'),
        'provider_reporting_metadata':metadata,'provider_metric_semantics':registry(),
        **{k+'_resolution':r for k,r in {**flows,**stocks,'shares':shares}.items()},
        'enterprise_bridge_resolution':bridge,'metric_basis_before':deepcopy(closure['metric_basis_closure']),
        'metric_basis_after':deepcopy(bridge),'coverage_before':coverage_before,'coverage_after':coverage_after,
        'coverage_delta':coverage_after-coverage_before,'metric_basis_component_before':prior,'metric_basis_component_after':credit,
        'business_mix_component_unchanged':True,'v49_before':before,'v49_after':after,'v49_reporting_basis_adapter':adapter,
        'v49_evidence_delta':{k:{'score_before':before[k]['score'],'score_after':after[k]['score'],'component_changes':{name:{'before':before[k]['score_components'].get(name),'after':value} for name,value in after[k]['score_components'].items() if value!=before[k]['score_components'].get(name)}} for k in ('ev_ebitda','ev_revenue')},
        'formal_conclusion_allowed':eligible,'production_integration_performed':False,
        'production_invariants':{'stock_unchanged':stock==original},
        'telemetry':{'added_provider_calls':0,'added_logical_calls':0,'statement_reads':sum(len(v) for v in snapshot.get('series',{}).values()),'metadata_reads':1}}

def resolve_report(report):
    out=deepcopy(report)
    for s in out.get('stocks') or []:
        same_batch=(report.get('input_batch_id') or report.get('batch_id'))==(s.get('normalized_inputs') or {}).get('input_batch_id')
        s['reporting_basis_resolution']=resolve_stock(s,report.get('batch_calibration_eligibility') if same_batch else 'INELIGIBLE')
    out['reporting_basis_resolution_version']='v5.2'
    return out

def summary(stock):
    r=stock['reporting_basis_resolution'];b=r['enterprise_bridge_resolution']
    return {'Ticker':stock['ticker'],**{('EBITDA' if k=='ebitda' else k.title())+' Basis':r[k+'_resolution']['selected_basis'] for k in ('ebitda','revenue','cash','debt','shares')},
        'EV/EBITDA Basis Fit':b['ev_ebitda_basis_compatibility'],'EV/Revenue Basis Fit':b['ev_revenue_basis_compatibility'],
        'Bridge Timing':b['enterprise_bridge_timing_assessment'],'Enterprise Basis':b['enterprise_input_basis_compatibility'],
        'Coverage Before':r['coverage_before'],'Coverage After':r['coverage_after'],
        'V4.9 Before':r['v49_before']['company_level'].get('suitability'),'V4.9 After':r['v49_after']['company_level'].get('suitability')}

def export_report(report):
    return {'version':'v5.2','mode':'DIAGNOSTIC_ONLY','batch_id':report.get('batch_id'),'input_batch_id':report.get('input_batch_id'),
        'stocks':[deepcopy(s['reporting_basis_resolution']) for s in report.get('stocks') or []]}

def export_csv(report):
    rows=[summary(s) for s in report.get('stocks') or []];buffer=io.StringIO(newline='')
    if rows:
        writer=csv.DictWriter(buffer,fieldnames=list(rows[0]));writer.writeheader()
        writer.writerows({k:"'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v for k,v in row.items()} for row in rows)
    return buffer.getvalue().encode('utf-8-sig')
