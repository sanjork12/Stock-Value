"""V5.0 pure financial structural evidence plus opt-in statement observation.

No provider/database/cache clients, fair values, benchmark inputs or ticker rules.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from datetime import date
import math
import re
import statistics as stats
from uuid import uuid4

from valuation_primitives import fnum
from enterprise_evidence_policy import EVIDENCE_POLICY_VERSION,POLICY,COVERAGE_WEIGHTS

_OBSERVER=ContextVar('enterprise_statement_evidence',default=None)
ROWS={
    'income_stmt':{'revenue':('Total Revenue','Operating Revenue'),'operating_income':('Operating Income',),
        'ebit':('EBIT',),'ebitda':('EBITDA',),'eps':('Diluted EPS','Basic EPS'),
        'depreciation_and_amortization':('Reconciled Depreciation','Depreciation And Amortization In Income Statement'),
        'unusual_items':('Total Unusual Items',)},
    'cashflow':{'capex':('Capital Expenditure','Capital Expenditures','Purchase Of PPE'),
        'operating_cash_flow':('Operating Cash Flow','Total Cash From Operating Activities','Cash Flow From Continuing Operating Activities'),
        'free_cash_flow':('Free Cash Flow',),'sbc':('Stock Based Compensation',),
        'depreciation_and_amortization':('Depreciation And Amortization','Depreciation Amortization Depletion')},
}
SNAPSHOT_FIELDS=('revenue','operating_income','operating_margin','ebit','ebitda','eps','capex',
    'operating_cash_flow','free_cash_flow','sbc','depreciation_and_amortization','unusual_items')


def number(value):return None if isinstance(value,bool) else fnum(value)


def period(value):
    s=str(value)[:10]
    if re.fullmatch(r'FY\d{4}',s):return s
    try:return date.fromisoformat(s).isoformat()
    except (ValueError,TypeError):return None


@contextmanager
def observe_enterprise_statements(ticker):
    observed={'ticker':ticker,'historical_evidence_acquisition_id':str(uuid4()),'series':{},'statement_observations':0}
    token=_OBSERVER.set(observed)
    try:yield observed
    finally:_OBSERVER.reset(token)


def _observe_statement_values(stage,path,frame):
    """Observe only already-fetched annual statement numbers; never request data."""
    observed=_OBSERVER.get()
    if observed is None or stage not in ROWS or frame is None or getattr(frame,'empty',True):return
    observed['statement_observations']+=1
    for metric,aliases in ROWS[stage].items():
        row=next((name for name in aliases if name in frame.index),None)
        if row is None:continue
        for col in list(frame.columns)[:POLICY['max_annual_observations']]:
            p=period(col)
            observation={'period':p,'value':number(frame.loc[row,col]),'source':path+'.'+row,
                'basis':'FY','derivation':'DIRECT_STATEMENT_LINE','statement_stage':stage}
            observed['series'].setdefault(metric,[]).append(observation)



def observe_statement_values(stage,path,frame):
    # Diagnostic observation must never interrupt production financial loading.
    try:_observe_statement_values(stage,path,frame)
    except Exception as exc:
        observed=_OBSERVER.get()
        if observed is not None:observed.setdefault('observation_errors',[]).append({'stage':stage,'category':type(exc).__name__})


def safe_ratio(numerator,denominator):
    a,b=number(numerator),number(denominator)
    if a is None or b is None or b<=0:return None,'MISSING_NUMERATOR' if a is None else 'INVALID_DENOMINATOR'
    value=a/b
    return (value,None) if math.isfinite(value) else (None,'NONFINITE_RATIO')


def record(value='INSUFFICIENT_EVIDENCE',*,status=None,confidence='LOW',fields=(),periods=(),
           derivation='',reasons=(),missing=(),**extra):
    insufficient=value in ('UNKNOWN','INSUFFICIENT_EVIDENCE')
    return {'value':value,'status':status or ('INSUFFICIENT_EVIDENCE' if insufficient else 'SUPPORTED'),
        'confidence':confidence,'source_fields':list(fields),'source_periods':list(periods),
        'derivation':derivation,'reason_codes':list(reasons),'missing_inputs':list(missing),**extra}


def annual_stats(observations):
    raw=deepcopy(observations);valid=[];excluded=[];warnings=[]
    for obs in raw:
        reason=None
        if period(obs.get('period')) is None:reason='INVALID_OR_UNKNOWN_PERIOD'
        elif obs.get('basis')!='FY':reason='NON_ANNUAL_BASIS'
        elif number(obs.get('value')) is None:reason='MISSING_OR_NONFINITE_VALUE'
        if reason:excluded.append({'observation':obs,'reason':reason})
        else:valid.append({**obs,'value':number(obs['value'])})
    kinds={'FY_LABEL' if str(o['period']).startswith('FY') else 'FISCAL_END_DATE' for o in valid}
    duplicates={o['period'] for o in valid if sum(v['period']==o['period'] for v in valid)>1}
    if len(kinds)>1:
        warnings.append('PERIOD_ALIGNMENT_WARNING')
        excluded.extend({'observation':o,'reason':'MIXED_PERIOD_LABEL_SEMANTICS'} for o in valid);valid=[]
    if duplicates:
        excluded.extend({'observation':o,'reason':'DUPLICATE_PERIOD_NO_SILENT_SELECTION'} for o in valid if o['period'] in duplicates)
        valid=[o for o in valid if o['period'] not in duplicates];warnings.append('PERIOD_ALIGNMENT_WARNING')
    valid.sort(key=lambda o:o['period'])
    if kinds=={'FISCAL_END_DATE'} and any((date.fromisoformat(b['period'])-date.fromisoformat(a['period'])).days<POLICY['min_annual_period_gap_days'] for a,b in zip(valid,valid[1:])):
        warnings.append('PERIOD_ALIGNMENT_WARNING')
        excluded.extend({'observation':o,'reason':'ANNUAL_FREQUENCY_NOT_ESTABLISHED'} for o in valid);valid=[]
    currencies={o.get('currency') for o in valid if o.get('currency')}
    if len(currencies)>1:
        warnings.append('PERIOD_ALIGNMENT_WARNING')
        excluded.extend({'observation':o,'reason':'HISTORICAL_CURRENCY_MISMATCH'} for o in valid);valid=[]
    values=[number(o['value']) for o in valid];n=len(values)
    mean=stats.mean(values) if n else None;std=stats.pstdev(values) if n else None
    cv=std/abs(mean) if mean not in (None,0) else None
    years=[int(o['period'][2:6] if o['period'].startswith('FY') else o['period'][:4]) for o in valid]
    changes=[]
    for i in range(1,n):
        value,reason=safe_ratio(values[i]-values[i-1],values[i-1])
        if years[i]-years[i-1]!=1:value,reason=None,'NON_CONSECUTIVE_FISCAL_YEARS'
        changes.append({'period':valid[i]['period'],'value':value,'reason':reason})
    growth=[o['value'] for o in changes if o['value'] is not None]
    cagr=None
    if n>=2 and values[0]>0 and values[-1]>0 and years[-1]>years[0]:cagr=(values[-1]/values[0])**(1/(years[-1]-years[0]))-1
    slope=None
    if n>=2:
        center=stats.mean(years);variance=sum((x-center)**2 for x in years)
        if variance:slope=sum((x-center)*(v-mean) for x,v in zip(years,values))/variance
    anomalies=[{'period':o['period'],'reason':'LARGE_YOY_DISCONTINUITY','growth':o['value']} for o in changes
        if o['value'] is not None and abs(o['value'])>POLICY['revenue_discontinuity_growth']]
    return {'raw_series':raw,'filtered_series':valid,'excluded_observations':excluded,
        'filter_policy':'Only invalid/unaligned/duplicate data excluded; numeric outliers retained and labelled.',
        'observation_count':n,'periods':[o['period'] for o in valid],'mean':mean,'median':stats.median(values) if n else None,
        'std':std,'coefficient_of_variation':cv,'cv_reason':'ZERO_OR_MISSING_MEAN' if cv is None else None,
        'min':min(values) if n else None,'max':max(values) if n else None,
        'spread':max(values)-min(values) if n else None,'trend_slope':slope,
        'latest_vs_median':values[-1]-stats.median(values) if n else None,
        'yoy_changes':changes,'sign_changes':sum(a*b<0 for a,b in zip(values,values[1:])),
        'cagr':cagr,'cagr_reason':None if cagr is not None else 'INSUFFICIENT_POSITIVE_ENDPOINTS_OR_PERIOD_SPAN',
        'growth_cv_reason':None if len(growth)>1 and stats.mean(growth)!=0 else 'INSUFFICIENT_YOY_OR_ZERO_GROWTH_MEAN','growth_cv':stats.pstdev(growth)/abs(stats.mean(growth)) if len(growth)>1 and stats.mean(growth)!=0 else None,
        'negative_growth_frequency':sum(g<0 for g in growth)/len(growth) if growth else None,
        'negative_growth_frequency_reason':None if growth else 'NO_COMPARABLE_YOY_OBSERVATIONS',
        'growth_swing':max(growth)-min(growth) if growth else None,'anomalies':anomalies,'warnings':list(dict.fromkeys(warnings))}


def evidence_snapshot(stock,observed=None):
    f=stock.get('normalized_inputs') or {};observed=observed or {};warnings=[]
    series=deepcopy(observed.get('series') or {})
    if observed.get('ticker') not in (None,stock.get('ticker')):
        series={};warnings.append('HISTORICAL_TICKER_MISMATCH')
    for metric in SNAPSHOT_FIELDS:series.setdefault(metric,[])
    # Existing normalized annual series are fallback evidence, never current-input replacements.
    fallback={k:[] for k in SNAPSHOT_FIELDS}
    for row in f.get('historical_margins') or []:
        for metric in ('revenue','operating_income','operating_margin'):
            fallback[metric].append({'period':period(row.get('period')),'value':number(row.get(metric)),
                'source':'normalized_inputs.historical_margins.'+metric,'basis':'FY','derivation':'EXISTING_NORMALIZED_STATEMENT_SERIES'})
    for row in f.get('annual_cashflows') or []:
        for metric,keys in {'capex':('capital_expenditure','capex'),'operating_cash_flow':('operating_cash_flow',),
                           'free_cash_flow':('free_cash_flow','fcf')}.items():
            val=next((number(row.get(k)) for k in keys if number(row.get(k)) is not None),None)
            fallback[metric].append({'period':period(row.get('period')),'value':val,'source':'normalized_inputs.annual_cashflows.'+metric,
                'basis':'FY','derivation':'EXISTING_NORMALIZED_STATEMENT_SERIES'})
    for row in f.get('historical_eps') or []:
        fallback['eps'].append({'period':period(row.get('period')),'value':number(row.get('eps')),
            'source':'normalized_inputs.historical_eps.eps','basis':'FY','derivation':'EXISTING_NORMALIZED_STATEMENT_SERIES'})
    for metric in series:
        if not series[metric]:series[metric]=fallback[metric]
        for row in series[metric]:
            row.setdefault('currency',f.get('financial_currency'))
    if not series['operating_margin']:
        rev={r['period']:r for r in series['revenue'] if r.get('period')}
        for op in series['operating_income']:
            if op.get('period') in rev:
                value,reason=safe_ratio(op.get('value'),rev[op['period']].get('value'))
                series['operating_margin'].append({'period':op['period'],'value':value,'source':'aligned operating_income / revenue',
                    'basis':'FY','currency':f.get('financial_currency'),'derivation':'DERIVED_ALIGNED_RATIO','reason':reason})
    captured_id=observed.get('historical_evidence_acquisition_id') if observed.get('statement_observations',0)>0 else None
    if observed.get('observation_errors'):warnings.append('STATEMENT_EVIDENCE_OBSERVATION_ERROR')
    result={k:annual_stats(v) for k,v in series.items()}
    for values in result.values():warnings.extend(values['warnings'])
    return {'ticker':stock.get('ticker'),'input_batch_id':f.get('input_batch_id'),
        'fundamentals_acquisition_id':f.get('fundamentals_acquisition_id'),
        'historical_evidence_acquisition_id':captured_id or ('normalized:'+str(f['fundamentals_acquisition_id']) if f.get('fundamentals_acquisition_id') else None),
        'capture_mode':'OBSERVED_EXISTING_ANNUAL_STATEMENTS' if captured_id else 'EXISTING_NORMALIZED_SERIES_ONLY',
        'series':result,'warnings':list(dict.fromkeys(warnings)),
        'telemetry':{'logical_calls':0,'historical_statement_calls':0,'cache_hits':0,
            'statement_observations':observed.get('statement_observations',0),
            'source_historical_statement_calls':sum(v for k,v in ((f.get('acquisition_metadata') or {}).get('statement_estimate_method_invocations') or {}).items() if any(name in k for name in ('cashflow','cash_flow','income_stmt','financials','balance_sheet'))),
            'source_acquisition_logical_calls':deepcopy((f.get('acquisition_metadata') or {}).get('logical_calls') or {}),
            'source_cache_hit':(f.get('acquisition_metadata') or {}).get('cache_hit'),
            'notes':'No added requests; observation count is not a network call count.'}}


def band(value,thresholds,labels):
    return 'UNKNOWN' if number(value) is None else labels[sum(value>threshold for threshold in thresholds)]


def history_record(value,series,*,fields,derivation,reasons=(),missing=(),confidence='MEDIUM',**extra):
    return record(value,fields=fields,periods=series['periods'],derivation=derivation,reasons=reasons,
        missing=missing,confidence=confidence,statistics=deepcopy(series),**extra)


def stability(series):
    if series['observation_count']<POLICY['min_annual_observations']:
        value='INSUFFICIENT_EVIDENCE'
    elif series['sign_changes'] or series['min']<=0:value='HIGHLY_VOLATILE'
    else:value=band(series['coefficient_of_variation'],(POLICY['ebitda_cv_stable'],POLICY['ebitda_cv_moderate'],POLICY['ebitda_cv_volatile']),
        ('STABLE','MODERATELY_STABLE','VOLATILE','HIGHLY_VOLATILE'))
    return history_record(value,series,fields=('annual EBITDA',),derivation='Population CV / abs(mean), signs and >=3 comparable annual direct EBITDA observations.',
        missing=('three_comparable_annual_ebitda',) if value in ('INSUFFICIENT_EVIDENCE','UNKNOWN') else ())


def margin_regime(series):
    if series['observation_count']<POLICY['min_annual_observations']:value='INSUFFICIENT_EVIDENCE'
    elif series['min']<0<series['max']:value='TRANSITIONAL'
    elif series['spread']<=POLICY['margin_stable_spread']:
        value='STABLE_HIGH_MARGIN' if series['median']>=POLICY['high_margin'] else 'STABLE_LOW_MARGIN' if series['median']<POLICY['low_margin'] else 'STABLE_MODERATE_MARGIN'
    elif series['trend_slope']>=POLICY['margin_trend_slope']:value='EXPANDING'
    elif series['trend_slope']<=-POLICY['margin_trend_slope']:value='COMPRESSING'
    else:value='VOLATILE'
    return history_record(value,series,fields=('annual operating_income','annual revenue','historical_margins'),
        derivation='>=3 fiscal operating margins; spread, sign transitions and fiscal-year regression slope.',
        missing=('three_comparable_annual_operating_margins',) if value=='INSUFFICIENT_EVIDENCE' else (),
        variation_band='UNKNOWN' if series['spread'] is None else 'LOW' if series['spread']<=POLICY['margin_stable_spread'] else 'MODERATE' if series['spread']<=POLICY['margin_moderate_spread'] else 'HIGH')


def basis_compatibility(f):
    provenance=f.get('acquisition_provenance') or {};metric=f.get('enterprise_metric_basis') or {}
    statements={item.get('field'):item for item in f.get('statement_acquisition_provenance') or []}
    bases={};dates=[];currency=f.get('financial_currency');q=f.get('quote_currency');missing=[];incompatible=[]
    for key in ('ebitda','revenue','cash','debt','canonical_shares'):
        item=provenance.get(key) or {};line=statements.get(key) or {}
        basis=metric.get(key) or item.get('metric_basis') or line.get('metric_basis') or 'UNKNOWN'
        if key=='canonical_shares':basis=f.get('canonical_shares_basis') or 'UNKNOWN'
        p=line.get('as_of_date') or line.get('period') or item.get('as_of_date') or item.get('period')
        c=item.get('currency') or line.get('currency') or currency
        bases[key]={'basis':basis,'period':p,'currency':c,'source':item.get('source') or f.get('canonical_shares_source') if key=='canonical_shares' else item.get('source') or line.get('source'),
            'value_available':number(f.get(key)) is not None,'retrieved_at':item.get('acquired_at')}
        if number(f.get(key)) is None:missing.append(key)
        if not p:missing.append(key+'_as_of')
        allowed=('TTM','QUOTE_SUMMARY_TTM','FY') if key in ('ebitda','revenue') else ('FY','LATEST_BALANCE_SHEET','QUOTE_SUMMARY_CURRENT_BALANCE','CURRENT_BALANCE_SHEET') if key in ('cash','debt') else ('FY','CURRENT_SHARE_COUNT','DILUTED_ANNUAL_AVERAGE','LATEST_BALANCE_SHEET_SHARE_COUNT')
        if basis not in allowed:missing.append(key+'_explicit_basis')
        if c and currency and c!=currency:incompatible.append(key+'_currency_mismatch')
        if p and re.fullmatch(r'\d{4}-\d{2}-\d{2}',str(p)):
            try:dates.append(date.fromisoformat(p))
            except ValueError:missing.append(key+'_valid_as_of')
        elif p:missing.append(key+'_comparable_as_of')
    known_currency=lambda c:isinstance(c,str) and bool(re.fullmatch('[A-Z]{3}',c))
    if not known_currency(q) or not known_currency(currency):missing.append('known_quote_and_financial_currency')
    elif q!=currency or f.get('currency_mismatch'):incompatible.append('currency_context_mismatch')
    if incompatible:value='INCOMPATIBLE'
    elif dates and (max(dates)-min(dates)).days>POLICY['basis_asof_max_days']:value='MIXED_BASIS';incompatible.append('as_of_gap_exceeds_policy')
    elif any(k in missing for k in ('ebitda','revenue','cash','debt','canonical_shares','known_quote_and_financial_currency')):value='UNKNOWN'
    elif any(m.endswith('_explicit_basis') for m in missing):value='UNKNOWN'
    elif missing:value='MOSTLY_COMPATIBLE'
    else:
        operating=[str(bases[k]['basis']) for k in ('ebitda','revenue')]
        value='MIXED_BASIS' if any('TTM' in b for b in operating) and any(b=='FY' for b in operating) else 'COMPATIBLE'
    return record(value,fields=('enterprise_metric_basis','acquisition_provenance','statement_acquisition_provenance','canonical_shares'),
        derivation='Explicit currency, period and basis only; retrieval date is not a reporting as-of date.',
        reasons=incompatible,missing=missing,confidence='HIGH' if value in ('COMPATIBLE','INCOMPATIBLE') else 'LOW',metric_bases=bases)


def business_mix(stock):
    profile=((stock.get('live_blend') or stock.get('blend') or {}).get('profile') or {})
    explicit={}
    for obj in (profile,stock.get('profile_assumptions') or {},stock.get('normalized_inputs') or {},stock.get('enterprise_structural_metadata') or {}):
        for key in ('heterogeneous_business_mix','business_mix_warning','segment_complexity','company_level_multiple_risk'):
            if obj.get(key) is not None:explicit[key]=obj[key]
    curated=stock.get('curated_structural_metadata') or {};segments=stock.get('structural_segments') or {}
    reviewed=True;source='enterprise_structural_metadata'
    if curated:
        required=('source_type','source_note','effective_date','as_of','review_status','reviewed','confidence')
        if all(k in curated for k in required):
            explicit={**explicit,**curated};reviewed=curated['reviewed'] is True;source='curated_structural_metadata'
    value='INSUFFICIENT_EVIDENCE';count=None;material=[];margin_dispersion=None;growth_dispersion=None;concentration=None;reasons=[]
    if segments.get('basis')=='OPERATING_SEGMENTS' and segments.get('source') and isinstance(segments.get('segments'),list):
        entries=[s for s in segments['segments'] if number(s.get('revenue')) is not None and number(s['revenue'])>0]
        total=sum(number(s['revenue']) for s in entries)
        if total>0:
            material=[s for s in entries if number(s['revenue'])/total>=POLICY['segment_material_share']]
            count=len(material);concentration=max(number(s['revenue']) for s in entries)/total
            margins=[number(s.get('operating_margin')) for s in material if number(s.get('operating_margin')) is not None]
            growth=[number(s.get('growth')) for s in material if number(s.get('growth')) is not None]
            margin_dispersion=max(margins)-min(margins) if len(margins)>=2 else None
            growth_dispersion=max(growth)-min(growth) if len(growth)>=2 else None
            economics={s['economic_model'] for s in material if s.get('economic_model')}
            if segments.get('complete') is not True:reasons.append('SEGMENT_COVERAGE_NOT_CONFIRMED')
            elif count==0:reasons.append('NO_SEGMENT_ABOVE_MATERIALITY_THRESHOLD')
            elif count==1:value='HOMOGENEOUS'
            elif len(economics)>1 or margin_dispersion is not None and margin_dispersion>POLICY['segment_margin_dispersion']:
                value='HIGHLY_HETEROGENEOUS' if count>=POLICY['highly_heterogeneous_material_segments'] else 'HETEROGENEOUS'
            else:value='MODERATELY_DIVERSE'
            source=segments['source']
    elif segments.get('basis')=='GEOGRAPHIC':reasons.append('GEOGRAPHIC_SEGMENTS_ARE_NOT_OPERATING_MODELS')
    flag=explicit.get('heterogeneous_business_mix');warning=explicit.get('business_mix_warning')
    metadata_value='HETEROGENEOUS' if flag is True or warning=='EXPLICIT_HETEROGENEITY' else (
        'HIGHLY_HETEROGENEOUS' if warning=='COMPANY_LEVEL_MULTIPLE_RISK' or explicit.get('company_level_multiple_risk') is True else
        'HOMOGENEOUS' if flag is False or warning=='NONE' else 'MODERATELY_DIVERSE' if warning=='POSSIBLE_HETEROGENEITY' else
        'HETEROGENEOUS' if explicit.get('segment_complexity') in ('HIGH','VERY_HIGH') else None)
    if metadata_value is not None:
        if value=='INSUFFICIENT_EVIDENCE':value=metadata_value
        elif metadata_value!=value:
            reasons.append('EXPLICIT_METADATA_SEGMENT_CONFLICT')
            order=('HOMOGENEOUS','MODERATELY_DIVERSE','HETEROGENEOUS','HIGHLY_HETEROGENEOUS')
            value=max((value,metadata_value),key=order.index)
    if curated and source!='curated_structural_metadata':reasons.append('CURATED_METADATA_SCHEMA_INCOMPLETE_OR_UNUSED')
    if curated and not reviewed:reasons.append('UNREVIEWED_CURATED_METADATA_NO_CANDIDATE_YES')
    mix=record(value,fields=(source,),periods=([segments.get('period')] if segments.get('period') else [curated['as_of']] if curated.get('as_of') else []),
        derivation='Explicit operating-segment data or explicit governed structural metadata; never ticker/company-name inference.',
        confidence='MEDIUM' if reviewed else 'LOW',reasons=reasons,
        missing=('explicit_operating_segments_or_business_metadata',) if value=='INSUFFICIENT_EVIDENCE' else (),
        segment_count=count,segment_basis=segments.get('basis'),material_segments=[{'name':str(s.get('name',''))[:80],
            'revenue':number(s.get('revenue')),'operating_margin':number(s.get('operating_margin'))} for s in material],
        margin_heterogeneity=margin_dispersion,growth_dispersion=growth_dispersion,revenue_concentration=concentration,
        evidence_source=source,reviewed=reviewed,
        metadata_governance={k:deepcopy(curated.get(k)) for k in ('source_type','source_note','effective_date','as_of','review_status','reviewed','confidence')} if curated else None)
    complexity={'HOMOGENEOUS':'LOW','MODERATELY_DIVERSE':'MODERATE','HETEROGENEOUS':'HIGH','HIGHLY_HETEROGENEOUS':'VERY_HIGH'}.get(value,'UNKNOWN')
    return mix,record(complexity,fields=mix['source_fields'],periods=mix['source_periods'],
        derivation='Operating-model mix, material segment count and observed margin/growth dispersion; geography alone excluded.',
        reasons=reasons,missing=mix['missing_inputs'],confidence=mix['confidence'])


def aligned_ratios(snapshot,numerator,denominator,*,absolute=False):
    a={o['period']:o for o in snapshot['series'][numerator]['filtered_series']}
    b={o['period']:o for o in snapshot['series'][denominator]['filtered_series']}
    rows=[]
    for p in sorted(a.keys() & b.keys()):
        value,reason=safe_ratio(abs(a[p]['value']) if absolute else a[p]['value'],b[p]['value'])
        rows.append({'period':p,'value':value,'reason':reason,'source_fields':[a[p]['source'],b[p]['source']],
            'basis':'FY_ALIGNED','currency':a[p].get('currency')})
    return rows


def ratio_evidence(snapshot,f):
    definitions={'capex_to_revenue':('capex','revenue',True),'capex_to_ocf':('capex','operating_cash_flow',True),
        'capex_to_ebitda':('capex','ebitda',True),'fcf_to_ocf':('free_cash_flow','operating_cash_flow',False),
        'sbc_to_revenue':('sbc','revenue',True),'sbc_to_ebitda':('sbc','ebitda',True),'sbc_to_ocf':('sbc','operating_cash_flow',True)}
    ratios={}
    current_capex=next((number(f.get(k)) for k in ('normalized_capex','capital_expenditure','capital_expenditure_raw') if number(f.get(k)) is not None),None)
    current={**f,'capex':current_capex,'free_cash_flow':f.get('free_cash_flow',f.get('fcf'))}
    for name,(a,b,absolute) in definitions.items():
        rows=aligned_ratios(snapshot,a,b,absolute=absolute)
        available=[r for r in rows if r['value'] is not None]
        if available:
            latest=available[-1];value=latest['value'];reason=None;basis='FY_ALIGNED';fields=latest['source_fields']
        else:
            num=current.get(a);num=abs(number(num)) if absolute and number(num) is not None else num
            value,reason=safe_ratio(num,current.get(b));basis='CURRENT_MIXED_PROVIDER_PERIODS';fields=['normalized_inputs.'+a,'normalized_inputs.'+b]
        ratios[name]={'value':value,'reason':reason,'period':available[-1]['period'] if available else None,
            'basis':basis,'source_fields':fields,'historical_series':rows,
            'confidence':'MEDIUM' if available else 'LOW','status':'SUPPORTED' if available else 'PARTIALLY_SUPPORTED' if value is not None else 'INSUFFICIENT_EVIDENCE'}
    return ratios


def da_evidence(snapshot,f,basis):
    da=snapshot['series']['depreciation_and_amortization'];revenue=snapshot['series']['revenue']
    direct=aligned_ratios(snapshot,'depreciation_and_amortization','revenue',absolute=True)
    usable=[r for r in direct if r['value'] is not None]
    mode='DIRECT_STATEMENT_LINE';gap=None;ratio=None;ratio_reason=None;p=[];fields=['annual depreciation_and_amortization','annual revenue'];missing=[]
    if usable:ratio=usable[-1]['value'];p=[usable[-1]['period']]
    else:
        eb={o['period']:o for o in snapshot['series']['ebitda']['filtered_series']}
        op={o['period']:o for o in snapshot['series']['operating_income']['filtered_series']}
        rev={o['period']:o for o in revenue['filtered_series']}
        common=sorted(eb.keys() & op.keys() & rev.keys())
        if common:
            last=common[-1];gap=eb[last]['value']-op[last]['value']
            ratio,ratio_reason=safe_ratio(gap,rev[last]['value']);p=[last]
            mode='DERIVED_APPROXIMATION';fields=['annual EBITDA','annual operating_income','annual revenue']
        elif basis['value']=='COMPATIBLE' and f.get('operating_income_basis')==basis['metric_bases']['ebitda']['basis']:
            e,o=number(f.get('ebitda')),number(f.get('operating_income'))
            gap=e-o if e is not None and o is not None else None;ratio,ratio_reason=safe_ratio(gap,f.get('revenue'))
            mode='DERIVED_APPROXIMATION';fields=['ebitda','operating_income','revenue','operating_income_basis']
        else:missing=['direct_DA_or_period_aligned_EBITDA_operating_income_revenue']
    value=band(ratio,POLICY['da_revenue_bands'],('LOW','MODERATE','HIGH'))
    reasons=['NEGATIVE_DA_GAP_BASIS_REVIEW'] if ratio is not None and ratio<0 else []
    if reasons:value='UNKNOWN'
    return record(value,fields=fields,periods=p,derivation=mode,
        confidence='MEDIUM' if mode=='DIRECT_STATEMENT_LINE' else 'LOW',reasons=reasons,missing=missing,
        da_to_revenue=ratio,da_to_revenue_reason=ratio_reason or ('MISSING_ALIGNED_DA_REVENUE' if ratio is None else None),ebitda_operating_income_gap=gap,da_economic_materiality=value,
        source_kind=mode,approximation_caveat='EBITDA minus operating income can include other reconciliation differences; not a direct D&A observation.' if mode=='DERIVED_APPROXIMATION' else None)



def structural_input_view(stock):
    # An upstream legacy assumed-zero remains visible in the original input;
    # it cannot establish an observed zero in this evidence-only view.
    f=dict(stock.get('normalized_inputs') or {});excluded={}
    for key,provenance in (f.get('acquisition_provenance') or {}).items():
        if provenance.get('source')=='existing_missing_assumed_zero':
            f[key]=None;excluded[key]='UPSTREAM_ASSUMED_ZERO_IS_MISSING_EVIDENCE'
    return f,excluded


def build_structural_evidence(stock,*,batch_eligibility=None):
    original_f=stock.get('normalized_inputs') or {}
    f,excluded_inputs=structural_input_view(stock)
    profile=((stock.get('live_blend') or stock.get('blend') or {}).get('profile') or {})
    vclass=profile.get('valuation_class','UNKNOWN');snapshot=deepcopy(stock.get('evidence_snapshot') or evidence_snapshot(stock))
    histories=snapshot['series'];eb=histories['ebitda'];rev=histories['revenue'];margins=histories['operating_margin']
    basis=basis_compatibility(f);mix,segments=business_mix(stock);stable=stability(eb);margin=margin_regime(margins)
    ratios=ratio_evidence(snapshot,f);da=da_evidence(snapshot,f,basis)
    current_ebitda=number(f.get('ebitda'));current_revenue=number(f.get('revenue'))
    e_margin,e_margin_reason=safe_ratio(current_ebitda,current_revenue)
    op_margin=number(f.get('operating_margin'));blocked_class=vclass in ('bank','crypto_treasury','unsupported_specialized','space_optionality','auto_optionality')
    meaningful='INSUFFICIENT_EVIDENCE';meaning_reasons=[];meaning_missing=[]
    if current_ebitda is not None and current_ebitda<=0:meaningful='NOT_MEANINGFUL';meaning_reasons.append('NONPOSITIVE_EBITDA')
    elif e_margin is not None and e_margin>1:meaningful='LOW';meaning_reasons.append('UNUSUAL_EBITDA_REVENUE_RELATIONSHIP')
    elif blocked_class:meaningful='NOT_MEANINGFUL';meaning_reasons.append('NONOPERATING_OR_FINANCIAL_CLASS_ANCHOR')
    elif current_ebitda is None:meaning_missing.append('positive_current_ebitda')
    elif eb['observation_count']>=POLICY['min_annual_observations'] and margins['observation_count']>=POLICY['min_annual_observations'] and e_margin is not None:
        if eb['min']>0 and margins['median']>0:
            meaningful='HIGH' if stable['value']=='STABLE' and margin['value'].startswith('STABLE_') and da['value']=='LOW' else 'MODERATE'
            if da['value']=='HIGH':meaningful='LOW';meaning_reasons.append('MATERIAL_DA_ECONOMICS')
        else:meaningful='LOW';meaning_reasons.append('NONRECURRING_OR_TRANSITIONAL_OPERATING_PROFITABILITY')
    elif current_ebitda>0 and op_margin is not None and op_margin>0 and e_margin is not None:
        meaningful='MODERATE';meaning_missing.extend(('three_annual_ebitda','recurring_operating_profitability'))
    else:meaning_missing.extend(('operating_margin','historical_ebitda'))
    meaningful_record=record(meaningful,status='PARTIALLY_SUPPORTED' if meaning_missing and meaningful!='INSUFFICIENT_EVIDENCE' else None,
        fields=('ebitda','revenue','operating_margin','annual EBITDA','annual operating margins','valuation_class'),
        periods=eb['periods'],derivation='Positive EBITDA alone is insufficient; recurring profitability, direct history, margins and D&A qualify the operating anchor.',
        reasons=meaning_reasons,missing=meaning_missing,confidence='LOW' if da['value']=='HIGH' else 'HIGH' if meaningful=='HIGH' else 'MEDIUM' if not meaning_missing else 'LOW',
        current_ebitda_margin=e_margin,current_ebitda_margin_reason=e_margin_reason,current_operating_margin=op_margin)
    revenue='INSUFFICIENT_EVIDENCE';rev_missing=[];rev_reasons=[]
    explicit=stock.get('enterprise_structural_metadata') or {}
    if current_revenue is not None and current_revenue<=0 or explicit.get('non_operating_revenue') is True or blocked_class:
        revenue='NOT_INTERPRETABLE';rev_reasons.append('NONPOSITIVE_OR_NONOPERATING_REVENUE_ANCHOR')
    elif current_revenue is None:rev_missing.append('positive_revenue')
    elif rev['observation_count']>=POLICY['min_annual_observations']:
        if rev['anomalies'] or mix['value'] in ('HETEROGENEOUS','HIGHLY_HETEROGENEOUS') or margin['value'] in ('VOLATILE','TRANSITIONAL','COMPRESSING') or vclass=='cyclical_semiconductor':revenue='LOW'
        elif margin['value'].startswith('STABLE_') and mix['value']=='HOMOGENEOUS' and basis['value']=='COMPATIBLE':revenue='HIGH'
        else:revenue='MODERATE'
        if mix['value']=='INSUFFICIENT_EVIDENCE':rev_missing.append('business_mix')
        if margin['value']=='INSUFFICIENT_EVIDENCE':rev_missing.append('historical_margin_interpretation')
        if basis['value'] in ('UNKNOWN','MIXED_BASIS','INCOMPATIBLE'):rev_missing.append('revenue_basis_interpretation')
    else:rev_missing.append('three_comparable_annual_revenue')
    revenue_record=history_record(revenue,rev,fields=('revenue','annual revenue','annual margins','explicit business mix','enterprise metric basis','valuation_class'),
        derivation='Positive operating scale with fiscal revenue/margin history, discontinuity, class, mix and basis checks.',missing=rev_missing,reasons=rev_reasons)
    if rev_missing and revenue!='INSUFFICIENT_EVIDENCE':revenue_record['status']='PARTIALLY_SUPPORTED'
    cr=ratios['capex_to_revenue'];co=ratios['capex_to_ocf']
    severity=max((sum(r['value']>t for t in thresholds) for r,thresholds in ((cr,POLICY['capex_revenue_bands']),(co,POLICY['capex_ocf_bands'])) if r['value'] is not None),default=None)
    capital_value=('LOW','MODERATE','HIGH','VERY_HIGH')[severity] if severity is not None else 'UNKNOWN'
    capital_hist=cr['historical_series'];capital_values=[r['value'] for r in capital_hist if r['value'] is not None]
    cap_trend='INCREASING' if len(capital_values)>=2 and capital_values[-1]>capital_values[0] else 'DECREASING' if len(capital_values)>=2 and capital_values[-1]<capital_values[0] else 'STABLE' if len(capital_values)>=2 else 'UNKNOWN'
    capital=record(capital_value,fields=('annual capex','annual revenue','annual operating_cash_flow','annual EBITDA','annual FCF'),
        periods=[r['period'] for r in capital_hist],derivation='Max observed CapEx/revenue and CapEx/OCF band; signed CapEx converted to outflow magnitude for ratios only.',
        status='SUPPORTED' if cr['basis']=='FY_ALIGNED' and co['basis']=='FY_ALIGNED' else 'PARTIALLY_SUPPORTED' if severity is not None else 'INSUFFICIENT_EVIDENCE',
        confidence='MEDIUM' if cr['basis']=='FY_ALIGNED' else 'LOW',ratios={k:ratios[k] for k in ('capex_to_revenue','capex_to_ocf','capex_to_ebitda','fcf_to_ocf')},
        trend=cap_trend,coverage=len(capital_values),missing=() if severity is not None else ('valid_capex_and_positive_denominator',))
    growth_inputs={'revenue_cagr':rev['cagr'],'recent_revenue_growth':next((r['value'] for r in reversed(rev['yoy_changes']) if r['value'] is not None),None),
        'current_revenue_growth':number(f.get('revenue_growth')),'earnings_growth':number(f.get('earnings_growth')),
        'historical_eps_cagr':histories['eps']['cagr'],'forward_trailing_eps_change':None}
    forward,reason=safe_ratio(f.get('forward_eps'),f.get('trailing_eps'))
    if forward is not None:growth_inputs['forward_trailing_eps_change']=forward-1
    growth_values=[v for v in growth_inputs.values() if v is not None];maximum=max(growth_values) if growth_values else None
    mismatch='MATERIAL' if maximum is not None and maximum>=POLICY['growth_material'] else 'POSSIBLE' if (
        maximum is not None and maximum>=POLICY['growth_possible'] or vclass in ('semiconductor_growth','high_growth_software','pre_profit_growth') or margin['value']=='TRANSITIONAL') else False
    growth='INSUFFICIENT_EVIDENCE' if maximum is None else 'HIGH' if mismatch=='MATERIAL' else 'TRANSITIONAL' if margin['value']=='TRANSITIONAL' else 'ELEVATED' if maximum>=POLICY['growth_elevated'] else 'NORMAL'
    if vclass=='cyclical_semiconductor' and growth in ('HIGH','ELEVATED'):growth='CYCLICAL_REBOUND'
    if rev['anomalies'] and growth!='INSUFFICIENT_EVIDENCE':growth='DISTORTED'
    growth_record=record(growth,fields=tuple(growth_inputs)+('valuation_class','margin_regime'),periods=rev['periods'],
        derivation='Recorded historical CAGR/YoY, EPS history, current growth and EPS horizon comparison; V4.9 25%/50% mismatch thresholds retained.',
        status='SUPPORTED' if rev['observation_count']>=POLICY['min_annual_observations'] else 'PARTIALLY_SUPPORTED' if maximum is not None else 'INSUFFICIENT_EVIDENCE',
        inputs=growth_inputs,input_missing_reasons={'forward_trailing_eps_change':reason} if reason else {},v49_mismatch=mismatch,margin_trajectory=margin['value'],
        missing=() if maximum is not None else ('observed_growth_inputs',),
        reasons=('EPS_HORIZON_COMPARISON_NOT_FORECAST_CAGR',) if forward is not None else ())
    sbc_bands=[sum(ratios[key]['value']>t for t in thresholds) for key,thresholds in (
        ('sbc_to_revenue',POLICY['sbc_revenue_bands']),('sbc_to_ebitda',POLICY['sbc_ebitda_bands']),('sbc_to_ocf',POLICY['sbc_ocf_bands'])) if ratios[key]['value'] is not None]
    sbc_value=('LOW','MODERATE','HIGH','VERY_HIGH')[max(sbc_bands)] if sbc_bands else 'UNKNOWN'
    sbc=record(sbc_value,fields=('annual Stock Based Compensation','annual revenue','annual EBITDA','annual OCF'),
        periods=histories['sbc']['periods'],derivation='Direct SBC intensity; no industry/class proxy for missing SBC.',
        missing=() if sbc_bands else ('direct_SBC_and_valid_denominator',),
        ratios={key:value for key,value in ratios.items() if key.startswith('sbc_')})
    flags=[]
    if sbc_value in ('HIGH','VERY_HIGH'):flags.append('MATERIAL_SBC')
    if da['value']=='HIGH':flags.append('MATERIAL_DA')
    if basis['value'] in ('MIXED_BASIS','INCOMPATIBLE'):flags.append('METRIC_BASIS_CONCERN')
    unusual_ratios=aligned_ratios(snapshot,'unusual_items','revenue',absolute=True)
    unusual_values=[row['value'] for row in unusual_ratios if row['value'] is not None]
    if any(value>POLICY['unusual_items_revenue_materiality'] for value in unusual_values):flags.append('MATERIAL_REPORTED_UNUSUAL_ITEMS')
    fc=ratios['fcf_to_ocf']['value']
    fc_period=ratios['fcf_to_ocf']['period']
    same_period_ebitda=next((row['value'] for row in eb['filtered_series'] if row['period']==fc_period),None)
    if fc is not None and fc<0 and same_period_ebitda is not None and same_period_ebitda>0:flags.append('NEGATIVE_FCF_WITH_POSITIVE_EBITDA')
    acc_value='HIGH' if flags else 'MODERATE' if sbc_value=='MODERATE' or da['value']=='MODERATE' or any(value>0 for value in unusual_values) else 'LOW' if sbc_value=='LOW' and da['value']=='LOW' and histories['unusual_items']['observation_count']>=POLICY['min_annual_observations'] and basis['value']=='COMPATIBLE' else 'UNKNOWN'
    accounting=record(acc_value,fields=('SBC','D&A','unusual_items','FCF/OCF','enterprise_input_basis_compatibility'),
        derivation='Explicit measured accounting/basis concerns only; missing unusual-item coverage cannot establish absence of distortion.',
        reasons=flags,missing=('complete_accounting_distortion_coverage',) if acc_value=='UNKNOWN' else (),unusual_items_to_revenue=unusual_ratios)
    scalable='UNKNOWN'
    if rev['observation_count']>=POLICY['min_annual_observations'] and margins['observation_count']>=POLICY['min_annual_observations']:
        if rev['cagr'] is not None and rev['cagr']>0 and margin['value']=='EXPANDING' and cap_trend in ('STABLE','DECREASING'):scalable='SUPPORTED'
        elif margin['value']=='COMPRESSING' or cap_trend=='INCREASING':scalable='UNSUPPORTED'
        elif rev['cagr'] is not None and rev['cagr']>0:scalable='PARTIAL'
    eb_margin_trend=annual_stats([{'period':row['period'],'value':row['value'],'basis':'FY','source':'aligned reported EBITDA / revenue','currency':row.get('currency')} for row in aligned_ratios(snapshot,'ebitda','revenue')])
    operating_leverage,operating_leverage_reason=safe_ratio(histories['operating_income']['cagr'],rev['cagr'])
    scalability=record(scalable,fields=('annual revenue','annual operating margins','capital_intensity.trend'),periods=margins['periods'],
        derivation='Revenue growth with margin expansion and observed reinvestment trend; no scalability assumption from sector.',
        missing=('aligned_revenue_margin_capex_trends',) if scalable=='UNKNOWN' else (),
        status='PARTIALLY_SUPPORTED' if scalable=='PARTIAL' else None,
        operating_income_cagr=histories['operating_income']['cagr'],revenue_cagr=rev['cagr'],
        operating_leverage_growth_ratio=operating_leverage,operating_leverage_ratio_reason=operating_leverage_reason,
        ebitda_margin_trend_slope=eb_margin_trend['trend_slope'],capital_intensity_trend=cap_trend)
    optionality=str(profile.get('optionality_level','UNKNOWN')).lower();driver='UNKNOWN'
    if blocked_class:driver='NO' if vclass in ('crypto_treasury','bank','unsupported_specialized') else 'PARTIAL'
    elif optionality=='high':driver='PARTIAL'
    elif meaningful in ('HIGH','MODERATE') and revenue in ('HIGH','MODERATE') and optionality in ('low','medium'):
        driver='YES' if meaningful=='HIGH' and revenue=='HIGH' else 'MOSTLY'
    driver_record=record(driver,fields=('valuation_class','optionality_level','ebitda_meaningfulness','revenue_interpretability'),
        derivation='Class/optionality and measured operating economics jointly support value-driver relevance; optionality is not worthlessness.',
        missing=('operating_economics_and_optionality',) if driver=='UNKNOWN' else ())
    swing=rev['growth_swing'];cyclicality='UNKNOWN'
    if rev['observation_count']>=POLICY['min_annual_observations'] and swing is not None:cyclicality='VERY_HIGH' if swing>POLICY['growth_material'] or stable['value']=='HIGHLY_VOLATILE' else 'HIGH' if swing>POLICY['revenue_growth_swing'] or vclass=='cyclical_semiconductor' else 'MODERATE' if swing>POLICY['growth_possible'] or profile.get('cyclicality') in ('high','medium') else 'LOW'
    eb_margin_history=aligned_ratios(snapshot,'ebitda','revenue')
    eb_margin_values=[row['value'] for row in eb_margin_history if row['value'] is not None]
    eb_margin_swing=max(eb_margin_values)-min(eb_margin_values) if len(eb_margin_values)>=POLICY['min_annual_observations'] else None
    if eb_margin_swing is not None and eb_margin_swing>POLICY['margin_moderate_spread'] and cyclicality in ('LOW','MODERATE'):cyclicality='HIGH'
    cycle=record(cyclicality,fields=('annual revenue YoY','annual EBITDA','annual EPS','profile.cyclicality'),periods=rev['periods'],
        derivation='Observed revenue swings and direct EBITDA sign/CV evidence with existing class cyclicality; class assignment unchanged.',
        revenue_growth_swing=swing,ebitda_margin_swing=eb_margin_swing,ebitda_margin_history=eb_margin_history,earnings_growth_swing=histories['eps']['growth_swing'],ebitda_sign_changes=eb['sign_changes'],earnings_sign_changes=histories['eps']['sign_changes'],
        missing=('multi_year_growth_observations',) if cyclicality=='UNKNOWN' else ())
    debt,cash=number(f.get('debt')),number(f.get('cash'))
    leverage,leverage_reason=safe_ratio(debt-cash if debt is not None and cash is not None else None,f.get('ebitda'))
    leverage_record=record(band(leverage,POLICY['leverage_bands'],('LOW','MODERATE','HIGH','VERY_HIGH')),
        status='SUPPORTED' if leverage is not None and basis['value']=='COMPATIBLE' else 'PARTIALLY_SUPPORTED' if leverage is not None else 'INSUFFICIENT_EVIDENCE',
        fields=('debt','cash','ebitda'),derivation='Net debt / positive EBITDA; framework relevance only, never evidence of fair-value accuracy.',
        net_debt_to_ebitda=leverage,missing=(leverage_reason,) if leverage_reason else ())
    objects={'ebitda_meaningfulness':meaningful_record,'ebitda_stability':stable,'revenue_interpretability':revenue_record,
        'business_mix':mix,'segment_complexity':segments,'margin_regime':margin,'capital_intensity':capital,
        'growth_regime':growth_record,'sbc_distortion':sbc,'depreciation_amortization_distortion':da,
        'accounting_distortion':accounting,'enterprise_input_basis_compatibility':basis,
        'operating_fundamentals_primary_value_driver':driver_record,'scalable_operating_economics':scalability,'cyclicality':cycle,'capital_structure_relevance':leverage_record}
    groups={'ebitda':('ebitda_meaningfulness','ebitda_stability'),'revenue':('revenue_interpretability',),
        'margin_history':('margin_regime',),'capital_intensity':('capital_intensity',),'business_mix':('business_mix','segment_complexity'),
        'accounting':('sbc_distortion','depreciation_amortization_distortion','accounting_distortion'),
        'metric_basis':('enterprise_input_basis_compatibility',),'growth_cycle':('growth_regime','cyclicality')}
    completeness={'SUPPORTED':1.,'PARTIALLY_SUPPORTED':.5,'UNSUPPORTED':1.,'NOT_APPLICABLE':0.,'INSUFFICIENT_EVIDENCE':0.}
    components={name:weight*sum(completeness.get(objects[k]['status'],0) for k in groups[name])/len(groups[name]) for name,weight in COVERAGE_WEIGHTS.items()}
    coverage=round(sum(components.values()),4);coverage_band='HIGH' if coverage>=POLICY['coverage_high'] else 'MEDIUM' if coverage>=POLICY['coverage_medium'] else 'LOW' if coverage>=POLICY['coverage_low'] else 'INSUFFICIENT'
    f_batch=f.get('input_batch_id');acquisition=f.get('fundamentals_acquisition_id');warnings=list(snapshot['warnings'])
    identity_ok=bool(f_batch and acquisition and stock.get('input_batch_id')==f_batch and stock.get('fundamentals_acquisition_id')==acquisition and snapshot.get('input_batch_id')==f_batch and snapshot.get('fundamentals_acquisition_id')==acquisition and snapshot.get('ticker')==stock.get('ticker'))
    eligible=(batch_eligibility=='ELIGIBLE' and stock.get('calibration_eligibility')=='ELIGIBLE' and stock.get('source_status')=='live' and identity_ok)
    if not identity_ok:warnings.append('V5_BATCH_ACQUISITION_IDENTITY_UNVERIFIED_OR_DIVERGENT')
    state='COMPLETE' if coverage>=POLICY['coverage_high'] else 'PARTIAL' if coverage>=POLICY['coverage_low'] else 'INSUFFICIENT'
    audit_status='V5_INPUT_STATE_INELIGIBLE' if not eligible else 'V5_EVIDENCE_ELIGIBLE' if state=='COMPLETE' else 'V5_EVIDENCE_PARTIAL' if state=='PARTIAL' else 'V5_EVIDENCE_INSUFFICIENT'
    current_references={}
    for key in ('ebitda','revenue','operating_income','operating_margin','cash','debt','canonical_shares',
        'earnings_growth','revenue_growth','forward_eps','trailing_eps','normalized_capex','capital_expenditure',
        'operating_cash_flow','free_cash_flow','fcf'):
        source=(f.get('acquisition_provenance') or {}).get(key) or (f.get('provenance') or {}).get(key) or {}
        current_references[key]={'value':number(original_f.get(key)),'evidence_value':number(f.get(key)),
            'evidence_exclusion_reason':excluded_inputs.get(key),'source':source.get('source') or
            (f.get('canonical_shares_source') if key=='canonical_shares' else f.get(key+'_source')),
            'normalized_path':'normalized_inputs.'+key,'source_type':source.get('source_type'),
            'period':source.get('period'),'as_of_date':source.get('as_of_date'),
            'metric_basis':(f.get('enterprise_metric_basis') or {}).get(key) or source.get('metric_basis')}
    for key in ('quote_currency','financial_currency'):
        source=(f.get('acquisition_provenance') or {}).get(key) or {}
        current_references[key]={'value':f.get(key),'source':source.get('source') or f.get(key+'_source'),
            'normalized_path':'normalized_inputs.'+key}
    return {'version':EVIDENCE_POLICY_VERSION,'ticker':stock.get('ticker'),'valuation_class':vclass,
        'input_batch_id':f_batch,'fundamentals_acquisition_id':acquisition,
        'historical_evidence_acquisition_id':snapshot.get('historical_evidence_acquisition_id'),
        'evidence_status':state,'audit_status':audit_status,'formal_completion_conclusion_allowed':eligible,
        **objects,'evidence_coverage_score':coverage,'evidence_coverage_band':coverage_band,
        'evidence_coverage':{'score':coverage,'band':coverage_band,'components':components,'weights':deepcopy(COVERAGE_WEIGHTS),
            'meaning':'Evidence completeness only; negative findings count as known evidence. Not suitability or accuracy.'},
        'current_input_references':current_references,'excluded_current_input_evidence':excluded_inputs,
        'policy_version':EVIDENCE_POLICY_VERSION,'policy_thresholds':deepcopy(POLICY),
        'warnings':warnings,'telemetry':deepcopy(snapshot['telemetry']),
        'production_integration_performed':False,'mode':'DIAGNOSTIC_ONLY'}


def build_v49_evidence_adapter(evidence):
    """Only supported conclusions become explicit V4.9 booleans. Unknown is omitted."""
    adapter={};provenance={}
    def put(key,value,evidence_key):
        if value is not None:
            adapter[key]=value;provenance[key]={'evidence_key':evidence_key,
                'source_fields':deepcopy(evidence[evidence_key]['source_fields']),
                'source_periods':deepcopy(evidence[evidence_key]['source_periods']),
                'status':evidence[evidence_key]['status'],'derivation':evidence[evidence_key]['derivation']}
    e=evidence
    meaning=e['ebitda_meaningfulness']
    put('ebitda_economically_meaningful',True if meaning['value'] in ('HIGH','MODERATE') and meaning['status']=='SUPPORTED' else False if meaning['value']=='NOT_MEANINGFUL' else None,'ebitda_meaningfulness')
    put('ebitda_stable',True if e['ebitda_stability']['value']=='STABLE' else False if e['ebitda_stability']['value'] in ('VOLATILE','HIGHLY_VOLATILE') else None,'ebitda_stability')
    r=e['revenue_interpretability'];put('revenue_interpretable',True if r['value'] in ('HIGH','MODERATE') and r['status']=='SUPPORTED' else False if r['value']=='NOT_INTERPRETABLE' else None,'revenue_interpretability')
    mix={'HOMOGENEOUS':'NONE','MODERATELY_DIVERSE':'POSSIBLE_HETEROGENEITY','HETEROGENEOUS':'EXPLICIT_HETEROGENEITY','HIGHLY_HETEROGENEOUS':'COMPANY_LEVEL_MULTIPLE_RISK'}.get(e['business_mix']['value'])
    put('business_mix_warning',mix,'business_mix')
    put('heterogeneous_business_mix',False if mix=='NONE' else True if mix in ('EXPLICIT_HETEROGENEITY','COMPANY_LEVEL_MULTIPLE_RISK') else None,'business_mix')
    put('segment_complexity',None if e['segment_complexity']['value']=='UNKNOWN' else e['segment_complexity']['value'],'segment_complexity')
    margin=e['margin_regime']['value'];mapped={'STABLE_HIGH_MARGIN':'STABLE_HIGH_MARGIN','STABLE_MODERATE_MARGIN':'STABLE_MODERATE_MARGIN',
        'STABLE_LOW_MARGIN':'LOW_MARGIN','EXPANDING':'TRANSITIONAL','COMPRESSING':'TRANSITIONAL','TRANSITIONAL':'TRANSITIONAL','VOLATILE':'TRANSITIONAL'}.get(margin)
    put('margin_regime',mapped,'margin_regime')
    for key,ekey in (('sbc_distortion','sbc_distortion'),('unusual_da_economics','depreciation_amortization_distortion'),('accounting_distortion','accounting_distortion')):
        value=e[ekey]['value'];put(key,True if value in ('HIGH','VERY_HIGH') else False if value=='LOW' else None,ekey)
    basis=e['enterprise_input_basis_compatibility']['value']
    put('enterprise_input_basis_compatible',True if basis=='COMPATIBLE' else False if basis=='INCOMPATIBLE' else None,'enterprise_input_basis_compatibility')
    driver=e['operating_fundamentals_primary_value_driver']['value']
    put('operating_fundamentals_primary_value_driver',True if driver=='YES' else False if driver=='NO' else None,'operating_fundamentals_primary_value_driver')
    put('scalable_operating_economics',True if e['scalable_operating_economics']['value']=='SUPPORTED' else False if e['scalable_operating_economics']['value']=='UNSUPPORTED' else None,'scalable_operating_economics')
    if e['growth_regime']['value']!='INSUFFICIENT_EVIDENCE':
        put('growth_regime_mismatch_flag',e['growth_regime']['v49_mismatch'],'growth_regime')
        put('growth_regime_known',True,'growth_regime')
    if e['capital_intensity']['value']!='UNKNOWN':put('capital_intensity_assessment',e['capital_intensity']['value'],'capital_intensity')
    return {'version':EVIDENCE_POLICY_VERSION,'values':adapter,'provenance':provenance,
        'unknown_evidence_fields':[key for key,value in e.items() if isinstance(value,dict) and value.get('status')=='INSUFFICIENT_EVIDENCE']}


def v49_projection(audit):
    return {'audit_status':audit.get('audit_status'),'ev_ebitda':{k:deepcopy((audit.get('ev_ebitda') or {}).get(k)) for k in ('suitability','score','score_components','production_candidate','missing_evidence','hard_blocks','ceilings')},
        'ev_revenue':{k:deepcopy((audit.get('ev_revenue') or {}).get(k)) for k in ('suitability','score','score_components','production_candidate','missing_evidence','hard_blocks','ceilings')},
        'company_level':deepcopy(audit.get('company_level') or {}),
        'readiness':audit.get('enterprise_family_readiness'),'production_candidate':audit.get('enterprise_family_production_candidate')}


def complete_stock(stock,*,batch_eligibility=None):
    from enterprise_family_suitability import suitability_audit
    out=deepcopy(stock)
    if not out.get('evidence_snapshot'):
        out['evidence_snapshot']=evidence_snapshot(out)
    e=build_structural_evidence(out,batch_eligibility=batch_eligibility);adapter=build_v49_evidence_adapter(e)
    before=stock.get('enterprise_family_suitability') or suitability_audit(stock,batch_eligibility=batch_eligibility)
    private=deepcopy(stock)
    private['enterprise_structural_metadata']={**(private.get('enterprise_structural_metadata') or {}),**adapter['values'],
        '_evidence_policy_version':EVIDENCE_POLICY_VERSION}
    after=suitability_audit(private,batch_eligibility=batch_eligibility if e['formal_completion_conclusion_allowed'] else 'INELIGIBLE')
    ceiling=[]
    if not e['formal_completion_conclusion_allowed']:ceiling.append('V5_INPUT_STATE_INELIGIBLE')
    if not e['business_mix']['reviewed']:ceiling.append('UNREVIEWED_CURATED_METADATA')
    if ceiling:
        for method in ('ev_ebitda','ev_revenue'):
            after[method]['production_candidate']='NO';after[method]['ceilings'].extend(ceiling)
        after['company_level']['production_candidate']='NO';after['company_level']['reasons'].extend(ceiling)
        after['enterprise_family_production_candidate']='NO';after['enterprise_family_readiness']='DIAGNOSTIC_ONLY'
    delta={}
    for method in ('ev_ebitda','ev_revenue'):
        b=before.get(method) or {};a=after.get(method) or {}
        components={k:{'before':(b.get('score_components') or {}).get(k),'after':v,
            'delta':v-((b.get('score_components') or {}).get(k) or 0)} for k,v in (a.get('score_components') or {}).items()
            if v!=(b.get('score_components') or {}).get(k)}
        delta[method]={'score_before':b.get('score'),'score_after':a.get('score'),
            'delta':a['score']-b['score'] if a.get('score') is not None and b.get('score') is not None else None,
            'component_changes':components,'ceilings_before':deepcopy(b.get('ceilings')),'ceilings_after':deepcopy(a.get('ceilings')),
            'drivers':[{'field':key,'value':value,**adapter['provenance'][key]} for key,value in adapter['values'].items()
                if value!=(stock.get('enterprise_structural_metadata') or {}).get(key)]}
    out.update(enterprise_structural_evidence=e,v49_evidence_adapter=adapter,v49_before=v49_projection(before),v49_after=v49_projection(after),
        v49_evidence_delta={'methods':delta,'company_before':before.get('company_level'),'company_after':after.get('company_level'),
            'candidate_ceilings':ceiling,'production_unchanged':True,
            'production_fair_before':stock.get('production_analysis_fair',stock.get('fair_value')),
            'production_fair_after':out.get('production_analysis_fair',out.get('fair_value')),
            'production_fair_used_for_evidence':False,'explanation':'Only supported structural metadata changes enter a private diagnostic V4.9 rerun; no production valuation rerun.'},
        production_integration_performed=False)
    return out


def complete_report(report):
    out=deepcopy(report)
    for i,stock in enumerate(report.get('stocks') or []):
        out['stocks'][i]=complete_stock(stock,batch_eligibility=report.get('batch_calibration_eligibility'))
    out['enterprise_evidence_version']=EVIDENCE_POLICY_VERSION
    return out


def summary(stock):
    e=stock.get('enterprise_structural_evidence') or {};before=stock.get('v49_before') or {};after=stock.get('v49_after') or {}
    result={'ticker':stock['ticker'],'valuation_class':e.get('valuation_class'),'audit_status':e.get('audit_status'),
        'evidence_coverage_score':e.get('evidence_coverage_score'),'evidence_coverage_band':e.get('evidence_coverage_band')}
    for key in ('ebitda_meaningfulness','ebitda_stability','revenue_interpretability','business_mix','segment_complexity',
        'margin_regime','capital_intensity','sbc_distortion','accounting_distortion','enterprise_input_basis_compatibility',
        'operating_fundamentals_primary_value_driver'):
        result[key]=(e.get(key) or {}).get('value')
    for method in ('ev_ebitda','ev_revenue'):
        result['v49_'+method+'_before']=(before.get(method) or {}).get('suitability')
        result['v49_'+method+'_after']=(after.get(method) or {}).get('suitability')
        result['v49_'+method+'_score_before']=(before.get(method) or {}).get('score')
        result['v49_'+method+'_score_after']=(after.get(method) or {}).get('score')
    result.update(company_level_before=(before.get('company_level') or {}).get('suitability'),
        company_level_after=(after.get('company_level') or {}).get('suitability'),production_candidate_after=after.get('production_candidate'),
        readiness_after=after.get('readiness'))
    return result


def export_report(report):
    keys=('ticker','evidence_snapshot','enterprise_structural_evidence','v49_evidence_adapter','v49_before','v49_after','v49_evidence_delta','production_integration_performed')
    return {'version':EVIDENCE_POLICY_VERSION,'input_batch_id':report.get('input_batch_id'),
        'batch_id':report.get('batch_id'),'generated_at':report.get('generated_at'),
        'batch_calibration_eligibility':report.get('batch_calibration_eligibility'),'mode':'DIAGNOSTIC_ONLY',
        'stocks':[{k:deepcopy(s.get(k)) for k in keys} for s in report.get('stocks') or []]}


def export_csv(report):
    import csv,io
    rows=[summary(s) for s in report.get('stocks') or []];buffer=io.StringIO(newline='')
    if rows:
        writer=csv.DictWriter(buffer,fieldnames=list(rows[0]));writer.writeheader()
        for row in rows:writer.writerow({k:"'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v for k,v in row.items()})
    return buffer.getvalue().encode('utf-8-sig')
