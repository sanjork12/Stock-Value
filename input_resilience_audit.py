"""V4.8.1 public-field-only provider audit. Never supplies valuation inputs."""
from copy import deepcopy
from datetime import datetime, timezone
from importlib.metadata import version, PackageNotFoundError
from itertools import combinations
import platform
import time
from uuid import uuid4

from finnhub_service import number, TTL

TICKERS=('GOOG','MSFT','ORCL','NVDA','AMZN')
YAHOO_FIELDS={'current_price':'currentPrice','market_cap':'marketCap',
    'quote_currency':'currency','financial_currency':'financialCurrency',
    'forward_eps':'forwardEps','trailing_eps':'trailingEps','forward_pe':'forwardPE',
    'shares_outstanding':'sharesOutstanding','implied_shares':'impliedSharesOutstanding',
    'last_split_date':'lastSplitDate','last_split_factor':'lastSplitFactor',
    'cash':'totalCash','debt':'totalDebt','ebitda':'ebitda','revenue':'totalRevenue',
    'earnings_growth':'earningsGrowth','beta':'beta'}
FAST_FIELDS={'current_price':'last_price','market_cap':'market_cap',
    'quote_currency':'currency','shares_outstanding':'shares'}
PROFILE_FIELDS={'quote_currency':'currency','market_cap':'marketCapitalization',
    'shares_outstanding':'shareOutstanding','industry':'finnhubIndustry','exchange':'exchange'}
METRIC_FIELDS={'forward_pe':'forwardPE','trailing_eps':'epsTTM','pe_ttm':'peTTM',
    'beta':'beta','52w_high':'52WeekHigh','52w_low':'52WeekLow',
    'market_cap':'marketCapitalization','reported_forward_eps':'epsForward'}
STATEMENT_ROWS={'cash':('Cash Cash Equivalents And Short Term Investments','Cash And Cash Equivalents'),
    'debt':('Total Debt',),'ebitda':('EBITDA','Normalized EBITDA'),
    'revenue':('Total Revenue','Operating Revenue'),
    'diluted_average_shares':('Diluted Average Shares',),
    'operating_cash_flow':('Operating Cash Flow','Total Cash From Operating Activities'),
    'capital_expenditure':('Capital Expenditure','Capital Expenditures')}
PATHS=('yahoo.info','yahoo.get_info','yahoo.fast_info','yahoo.history_metadata',
       'yahoo.financials','yahoo.income_stmt','yahoo.cashflow','yahoo.balance_sheet',
       'yahoo.splits','yahoo.history_actions','finnhub.profile','finnhub.metric','finnhub.quote')
FIELDS=tuple(dict.fromkeys((*YAHOO_FIELDS,*STATEMENT_ROWS,*METRIC_FIELDS,'industry','exchange')))


def stamp():return datetime.now(timezone.utc).isoformat()


def public_value(field,value):
    # Strict whitelist: never serialize response objects, URLs or exception text.
    if field in ('quote_currency','financial_currency'):
        return value if isinstance(value,str) and len(value)==3 and value.isalpha() and value.isupper() else None
    if field in ('industry','exchange'):
        return value[:100] if isinstance(value,str) else None
    if field=='last_split_factor' and isinstance(value,str):
        import re
        return value if re.fullmatch(r'\d+(?:\.\d+)?[:/]\d+(?:\.\d+)?',value) else None
    return number(value)


def project(raw,mapping,*,millions=(),errors=None):
    values={}
    for field,key in mapping.items():
        try:
            value=public_value(field,raw.get(key))
            if value is None and field=='current_price' and key=='currentPrice':
                value=number(raw.get('regularMarketPrice'))
        except Exception as exc:
            if errors is not None:errors[field]=type(exc).__name__
            value=None
        if field in millions and isinstance(value,(int,float)):value*=1_000_000
        values[field]=value
    return values


def path_state(values,error=None):
    if error:return 'UNAVAILABLE'
    count=sum(v is not None for v in values.values())
    if not count:return 'UNAVAILABLE'
    fraction=count/max(len(values),1)
    return 'HEALTHY' if fraction==1 else 'PARTIAL' if fraction>=.5 else 'DEGRADED'


def numeric_disagreement(a,b):
    a,b=number(a),number(b)
    if a is None or b is None:return None
    pct=abs(a-b)/max(abs(a),abs(b),1e-12)*100
    return {'provider_disagreement_pct':pct,'status':
        'CONSISTENT' if pct<=2+1e-9 else 'MINOR_DIFFERENCE' if pct<=5+1e-9 else 'MATERIAL_DIFFERENCE'}


def disagreements(paths):
    out=[]
    for field in FIELDS:
        sources=[(name,p['values'].get(field)) for name,p in paths.items()
                 if p['values'].get(field) is not None]
        for (a,x),(b,y) in combinations(sources,2):
            if field in ('quote_currency','financial_currency','industry','exchange','last_split_factor'):
                result={'provider_disagreement_pct':None,'status':'CONSISTENT' if x==y else 'MATERIAL_DIFFERENCE'}
            else:result=numeric_disagreement(x,y)
            if result:out.append({'field':field,'source_a':a,'source_b':b,'value_a':x,'value_b':y,**result})
    return out


def cache_amplification(path):
    c=path.get('cache',{})
    return ('DEGRADED_CACHE_AMPLIFICATION' if c.get('cache_hit') is True and
        path.get('state') in ('DEGRADED','UNAVAILABLE') and (number(c.get('cache_ttl')) or 0)>60
        else 'NOT_OBSERVED' if c.get('cache_hit') is not None else 'UNKNOWN')


def statement_values(frame):
    values={};periods=[]
    if frame is not None and not getattr(frame,'empty',True):
        # yfinance generally returns newest first; sort dates to avoid assuming order.
        columns=sorted(frame.columns,reverse=True)
        periods=[str(c)[:10] for c in columns[:6]]
        for field,rows in STATEMENT_ROWS.items():
            for row in rows:
                if row in frame.index:
                    values[field]=number(frame.loc[row,columns[0]])
                    break
    return values,periods


def expected_fields(path):
    if path in ('yahoo.info','yahoo.get_info'):return YAHOO_FIELDS
    if path=='yahoo.fast_info':return FAST_FIELDS
    if path=='yahoo.history_metadata':return {'quote_currency':None}
    if path in ('yahoo.splits','yahoo.history_actions'):return {'last_split_date':None,'last_split_factor':None}
    if path=='yahoo.balance_sheet':return {'cash':None,'debt':None}
    if path in ('yahoo.financials','yahoo.income_stmt'):return {'ebitda':None,'revenue':None,'diluted_average_shares':None}
    if path=='yahoo.cashflow':return {'operating_cash_flow':None,'capital_expenditure':None}
    return PROFILE_FIELDS if path=='finnhub.profile' else METRIC_FIELDS if path=='finnhub.metric' else {'current_price':None}


def split_values(series):
    if series is None or getattr(series,'empty',True):return {}
    series=series.dropna().sort_index()
    series=series[series!=0]
    if series.empty:return {}
    return {'last_split_date':int(series.index[-1].timestamp()),'last_split_factor':number(series.iloc[-1])}


def collect_yahoo(ticker,factory):
    paths={};calls={}
    try:t=factory(ticker)
    except Exception as exc:
        return {name:{'provider':'Yahoo/yfinance','method':name,'values':{},
            'exception':type(exc).__name__,'latency_ms':None,'acquired_at':stamp(),
            'periods':[],'success':False,'state':'UNAVAILABLE',
            'cache':{'cache_key':ticker+':'+name,'cache_hit':None,'cache_age':None,'cache_ttl':None}}
            for name in PATHS if name.startswith('yahoo.')},{'yahoo.Ticker':1}
    # info/get_info on same object deliberately tests shared yfinance cache behavior.
    def call(name,fetch,parse):
        start=time.monotonic();when=stamp();error=None;periods=[];values={}
        try:values,periods=parse(fetch())
        except Exception as exc:error=type(exc).__name__
        values={field:values.get(field) for field in expected_fields(name)}
        calls[name]=calls.get(name,0)+1
        paths[name]={'provider':'Yahoo/yfinance','method':name,'values':values,
            'exception':error,'latency_ms':round((time.monotonic()-start)*1000,2),
            'acquired_at':when,'periods':periods,'success':error is None and any(v is not None for v in values.values()),
            'state':path_state(values,error),'cache':{'cache_key':ticker+':'+name,
            'cache_hit':None,'cache_age':None,'cache_ttl':None,
            'note':'Fresh diagnostic Ticker; internal lazy/shared cache and HTTP request count unobservable.'}}
    for name,fetch,mapping in (
        ('yahoo.info',lambda:t.info,YAHOO_FIELDS),
        ('yahoo.get_info',lambda:t.get_info(),YAHOO_FIELDS),
        ('yahoo.fast_info',lambda:t.fast_info,FAST_FIELDS),
        ('yahoo.history_metadata',lambda:t.get_history_metadata(),{'quote_currency':'currency'})):
        errors={}
        call(name,fetch,lambda raw,m=mapping:(project(raw,m,errors=errors),[]))
        paths[name]['field_errors']=errors
        paths[name]['raw_source_names']={field:key for field,key in mapping.items()}
        if errors:paths[name]['success']=False
        if name in ('yahoo.info','yahoo.get_info') and any(paths[name]['values'].get(f) is None
            for f in ('forward_eps','quote_currency','financial_currency')) and paths[name]['state']!='UNAVAILABLE':
            paths[name]['state']='DEGRADED'
    for attr in ('financials','income_stmt','cashflow','balance_sheet'):
        call('yahoo.'+attr,lambda a=attr:getattr(t,a),statement_values)
    call('yahoo.splits',lambda:t.splits,lambda raw:(split_values(raw),[]))
    def actions(raw):
        values=split_values(raw['Stock Splits']) if 'Stock Splits' in raw else {}
        return values,[str(c)[:10] for c in raw.index[-6:]]
    call('yahoo.history_actions',lambda:t.history(period='10y',actions=True,auto_adjust=False),actions)
    return paths,calls


def finnhub_cache(provider,path,params):
    key=(path,tuple(sorted(params.items())))
    # Observe existing cache only. No TTL mutation, no raw cached payload export.
    with provider._lock:
        entry=provider._cache.get(key);now=provider.clock()
        ttl=TTL[path]
        if entry:
            ttl=TTL[path] if entry[1].get('status') in ('AVAILABLE','NO_DATA') else 60
        return {'cache_key':path+':'+str(params.get('symbol')),
            'cache_hit':bool(entry and entry[0]>now),
            'cache_age':max(0,ttl-(entry[0]-now)) if entry else None,'cache_ttl':ttl}


def collect_finnhub(ticker,provider,blocked=False):
    paths={};calls={}
    for name,path,mapping in (('profile','stock/profile2',PROFILE_FIELDS),
        ('metric','stock/metric',METRIC_FIELDS),('quote','quote',{'current_price':'c'})):
        params={'symbol':ticker}
        if name=='metric':params['metric']='all'
        cache=finnhub_cache(provider,path,params);start=time.monotonic();when=stamp()
        status='SKIPPED_RATE_LIMIT';values={};raw_values={};fetched=None;quote_time=None;error=None
        if not blocked:
            try:
                # Existing endpoint allowlist, rate limiter, cache and credential loader.
                result=provider._symbol(path,ticker,**({'metric':'all'} if name=='metric' else {}))
                status=result['status'];fetched=result.get('fetched_at');raw=result.get('data') or {}
                if name=='metric':raw=raw.get('metric') or {}
                if isinstance(raw,dict):
                    raw_values=project(raw,mapping)
                    values=project(raw,mapping,millions=('market_cap','shares_outstanding'))
                    if name=='quote':quote_time=number(raw.get('t'))
                calls['finnhub.'+name]=1
            except Exception as exc:status='NETWORK_ERROR';error=type(exc).__name__
        if status=='RATE_LIMIT':blocked=True
        paths['finnhub.'+name]={'provider':'Finnhub','method':path,'values':values,
            'raw_values':raw_values,'raw_source_names':mapping,
            'raw_units':{'market_cap':'millions','shares_outstanding':'millions'} if name=='profile' else
                {'market_cap':'millions'} if name=='metric' else {},
            'status':status,'exception':error,'latency_ms':round((time.monotonic()-start)*1000,2),
            'acquired_at':when,'fetched_at':fetched,'quote_timestamp':quote_time,
            'cache':cache,'success':status=='AVAILABLE',
            'effective_timestamp':quote_time if name=='quote' else None,
            'effective_timestamp_status':'PROVIDER_QUOTE_TIME' if name=='quote' and quote_time else 'NOT_PROVIDED',
            'state':path_state(values,error or (status if status!='AVAILABLE' else None))}
        paths['finnhub.'+name]['cache']['amplification']=cache_amplification(paths['finnhub.'+name])
    return paths,calls,blocked


def candidate(field,source,value,kind,safety,validations):
    return {'field':field,'primary_source':'Yahoo current production source',
        'candidate_source':source,'value':value,'source_type':kind,'fallback_safety':safety,
        'tier':'TIER_1_DIRECT' if kind=='DIRECT' else 'TIER_2_DERIVED' if kind=='DERIVED' else 'NO_FALLBACK',
        'required_validations':validations,'recommended_action':
        'IMPLEMENT' if safety=='SAFE_DIRECT' else 'REVIEW' if safety=='SAFE_WITH_VALIDATION'
        else 'KEEP_DIAGNOSTIC_ONLY' if safety=='DIAGNOSTIC_ONLY' else 'REJECT',
        'implemented':False}


def candidates(paths,reference=None):
    p=lambda path,field:paths.get(path,{}).get('values',{}).get(field)
    out=[]
    q=p('finnhub.profile','quote_currency')
    out.append(candidate('quote_currency','finnhub.profile2.currency',q,
        'DIRECT' if q else 'UNAVAILABLE','SAFE_WITH_VALIDATION' if q else 'UNAVAILABLE',
        ['verified ticker/exchange identity','fresh profile','check all direct currency disagreements']))
    # Quote currency is never evidence of statement currency.
    fc_source=next((path for path in ('yahoo.get_info','yahoo.info') if p(path,'financial_currency') is not None),None)
    out.append(candidate('financial_currency',fc_source or 'quote_currency_inference',
        p(fc_source,'financial_currency') if fc_source else None,'DIRECT' if fc_source else 'INFERRED',
        'SAFE_WITH_VALIDATION' if fc_source else 'UNSAFE',['requires explicit statement reporting currency evidence']))
    for field in ('last_split_date','last_split_factor'):
        source=next((path for path in ('yahoo.splits','yahoo.history_actions') if p(path,field) is not None),None)
        out.append(candidate(field,source,p(source,field) if source else None,'DIRECT' if source else 'UNAVAILABLE',
            'SAFE_DIRECT' if source else 'UNAVAILABLE',['complete corporate action history','same listing/share basis']))
    for field in ('market_cap','shares_outstanding','current_price','trailing_eps'):
        source='finnhub.profile' if field in ('market_cap','shares_outstanding') else 'finnhub.quote' if field=='current_price' else 'finnhub.metric'
        value=p(source,field)
        out.append(candidate(field,source,value,'DIRECT' if value is not None else 'UNAVAILABLE',
            'SAFE_WITH_VALIDATION' if value is not None else 'UNAVAILABLE',
            ['provider units normalized','as-of period and split basis','provider agreement','same listing']))
    price,pe=p('finnhub.quote','current_price'),p('finnhub.metric','forward_pe')
    derived=price/pe if price and pe and price>0 and pe>0 else None
    quote=paths.get('finnhub.quote',{});metric=paths.get('finnhub.metric',{})
    qt=quote.get('quote_timestamp');mf=metric.get('fetched_at')
    try:age=abs(datetime.fromisoformat(mf).timestamp()-qt) if mf and qt else None
    except (TypeError,ValueError):age=None
    ref=reference if reference and reference.get('healthy_reference') else {}
    trailing=p('finnhub.metric','trailing_eps');healthy=number(ref.get('forward_eps'))
    item=candidate('forward_eps','finnhub.quote + finnhub.metric.forwardPE',derived,
        'DERIVED' if derived is not None else 'UNAVAILABLE','DIAGNOSTIC_ONLY' if derived is not None else 'UNAVAILABLE',
        ['price > 0','forwardPE > 0','same provider','quote/metric retrieval alignment',
         'metric effective timestamp not provided; retrieval time alone does not prove alignment'])
    reported=p('finnhub.metric','reported_forward_eps')
    item.update(derived_forward_eps=derived,current_price_used=price,forward_pe_used=pe,provider='Finnhub',
        calculated_at=stamp(),direct_forward_eps=reported,
        direct_forward_eps_status='REPORTED_EPSFORWARD_REQUIRES_HORIZON_VALIDATION' if reported is not None else 'NOT_RETURNED_BY_AUDITED_FIELDS',
        positive_check=derived is not None and derived>0,
        plausible_magnitude_check='PASS_DIAGNOSTIC_HEURISTIC' if derived and price and 0<derived<price else 'UNVERIFIED',
        quote_metric_retrieval_gap_seconds=age,timestamp_alignment='UNVERIFIED_METRIC_EFFECTIVE_TIME',
        trailing_eps_ratio=derived/trailing if derived is not None and trailing and trailing>0 else None,
        healthy_reference_forward_eps=healthy,healthy_reference_used_for_calculation=False,
        percent_difference_vs_healthy_reference=(derived/healthy-1)*100 if derived is not None and healthy and healthy>0 else None)
    out.append(item)
    if reported is not None:
        out.append(candidate('reported_forward_eps','finnhub.metric.epsForward',reported,'DIRECT',
            'DIAGNOSTIC_ONLY',['verify forecast horizon, provider semantics and split basis before treating as forward EPS']))
    for field in ('cash','debt','ebitda','revenue','diluted_average_shares'):
        source=next((path for path in ('yahoo.balance_sheet','yahoo.income_stmt','yahoo.financials') if p(path,field) is not None),None)
        out.append(candidate(field,source,p(source,field) if source else None,'DIRECT' if source else 'UNAVAILABLE',
            'SAFE_WITH_VALIDATION' if source else 'UNAVAILABLE',['statement period','units/currency','same share basis']))
    return out


def recovery_simulations(stock,proposals):
    reasons=list(stock.get('calibration_eligibility_reasons') or [])
    known=bool(stock) and 'calibration_eligibility' in stock
    def scenario(name,allowed,derived=False):
        available={c['field'] for c in proposals if c['field'] in allowed and c['value'] is not None
            and (c['source_type']=='DIRECT' or derived and c['source_type']=='DERIVED')}
        remaining=[];addressed=[]
        for reason in reasons:
            matched=next((f for f in available if reason==f+'_unknown' or reason=='healthy_reference_present_current_missing_'+f
                          or f in ('last_split_date','last_split_factor') and reason=='healthy_reference_present_current_missing_split_context'),None)
            # The two split components must both exist.
            if matched and matched.startswith('last_split') and not {'last_split_date','last_split_factor'}<=available:matched=None
            if derived and 'forward_eps' in available and 'forward_eps_missing' in reason:matched='forward_eps'
            (addressed if matched else remaining).append(reason)
        return {'scenario':name,'candidate_fields':sorted(available),
            'simulated_missing_reasons_remaining':remaining,'potentially_addressed_reasons':addressed,
            'eligibility_recovery_potential':'UNKNOWN_NO_CURRENT_BATCH' if not known else
                'POSSIBLE_REQUIRES_NEW_LIVE_PRODUCTION_RUN' if not remaining else 'BLOCKED',
            'real_calibration_eligibility_unchanged':True,'production_valuation_recomputed':False,
            'derived_cannot_unlock_real_eligibility':True}
    return [scenario('currency_only',{'quote_currency'}),scenario('split_only',{'last_split_date','last_split_factor'}),
        scenario('safe_direct_only',{c['field'] for c in proposals if c['fallback_safety']=='SAFE_DIRECT'}),
        scenario('direct_fields_validations_pending',{c['field'] for c in proposals if c['source_type']=='DIRECT'}),
        scenario('derived_eps_diagnostic_only',{c['field'] for c in proposals},True)]


def summarize_stock(ticker,paths,counts,stock=None):
    stock=stock or {};proposals=candidates(paths,stock.get('reference_snapshot'))
    matrix=[]
    for field in FIELDS:
        row={'ticker':ticker,'field':field}
        for path in PATHS:
            p=paths.get(path,{})
            applicable=field in expected_fields(path)
            row[path]={'value':p.get('values',{}).get(field),'status':'ERROR' if field in p.get('field_errors',{}) or p.get('exception') or p.get('status') in
                ('NETWORK_ERROR','RATE_LIMIT','SKIPPED_RATE_LIMIT','NOT_CONFIGURED','NOT_ENTITLED') else
                'DIRECT_VALUE' if p.get('values',{}).get(field) is not None else 'MISSING' if applicable else 'NOT_APPLICABLE'}
        matrix.append(row)
    derived=next(c for c in proposals if c['field']=='forward_eps')
    matrix.append({'ticker':ticker,'field':'derived_forward_eps','source_type':'DERIVED',
        'finnhub.quote_plus_metric':{'value':derived['value'],
            'status':'DERIVED_AVAILABLE' if derived['value'] is not None else 'MISSING'}})
    statement_comparison=[]
    normalized=stock.get('normalized_inputs') or {}
    for field in ('cash','debt','ebitda','revenue'):
        statement=next((p['values'][field] for name,p in paths.items() if name in ('yahoo.income_stmt','yahoo.financials','yahoo.balance_sheet') and p['values'].get(field) is not None),None)
        statement_comparison.append({'field':field,'quote_summary_value':paths['yahoo.info']['values'].get(field),
            'statement_value':statement,'normalized_value':normalized.get(field),
            'source_survives_info_degradation':statement is not None,
            'normalized_batch_id':stock.get('batch_id'),'normalized_batch_generated_at':stock.get('batch_generated_at'),
            'normalized_input_is_prior_batch_comparison_only':True})
    shares={name+':'+field:value for name,p in paths.items() for field,value in p['values'].items()
        if field in ('shares_outstanding','implied_shares','diluted_average_shares') and value is not None}
    info=paths['yahoo.get_info']['values'];cap=info.get('market_cap');price=info.get('current_price')
    if cap and price and price>0:shares['yahoo.get_info:market_cap_over_price']=cap/price
    agreement=[{'a':a,'b':b,**numeric_disagreement(x,y)} for (a,x),(b,y) in combinations(shares.items(),2)]
    return {'ticker':ticker,'provider_states':{name:p['state'] for name,p in paths.items()},'paths':paths,
        'yahoo_path_comparison':{field:{name:paths['yahoo.'+name]['values'].get(field) for name in ('info','get_info','fast_info')} for field in FIELDS},
        'field_matrix':matrix,'provider_disagreements':disagreements(paths),
        'fallback_candidates':proposals,'production_fallback_proposal':deepcopy(proposals),
        'source_precedence_proposal':{'primary':{'tier':'TIER_0','source':'current production Yahoo acquisition',
            'changed':False},'alternatives':[{'field':c['field'],'tier':c['tier'],'source':c['candidate_source'],
            'source_type':c['source_type'],'validation_required':c['required_validations']} for c in proposals]},
        'eligibility_recovery_simulation':recovery_simulations(stock,proposals),
        'current_calibration_eligibility':stock.get('calibration_eligibility','UNKNOWN_NO_CURRENT_BATCH'),
        'statement_resilience':statement_comparison,'shares_resilience':{'available_sources':shares,
            'agreement_pct':agreement,'candidate_safe_fallback':'REVIEW_PERIOD_AND_SPLIT_BASIS','canonical_algorithm_changed':False},
        'request_counts':{'method_invocations':counts,'total_method_invocations':sum(counts.values()),
            'http_request_count':None,'note':'Method counts are not HTTP counts; yfinance lazy calls and retries may differ.'},
        'production_inputs_modified':False}


def environment():
    out={'python':platform.python_version(),'runtime':'Streamlit Cloud','provider_client':'existing FinnhubProvider'}
    for name in ('yfinance','pandas','streamlit'):
        try:out[name]=version(name)
        except PackageNotFoundError:out[name]=None
    return out


def run_audit(*,yahoo_factory,provider,production_report=None):
    batch_id=str(uuid4());stocks=[];blocked=False
    prior={s['ticker']:s for s in (production_report or {}).get('stocks',[])}
    for ticker in TICKERS:
        paths,counts=collect_yahoo(ticker,yahoo_factory)
        fp,fc,blocked=collect_finnhub(ticker,provider,blocked)
        paths.update(fp);counts.update(fc)
        item=summarize_stock(ticker,paths,counts,prior.get(ticker))
        item.update(provider_batch_id=batch_id,generated_at=stamp());stocks.append(item)
    return {'batch_id':batch_id,'provider_batch_id':batch_id,'generated_at':stamp(),
        'mode':'READ_ONLY_PROVIDER_AUDIT','environment':environment(),'stocks':stocks,
        'production_fallback_implemented':False,'rate_limit_stopped_remaining_finnhub':blocked,
        'cache_audit':{'production_history_ttl_seconds':900,'production_fundamentals_ttl_seconds':900,
            'production_cache_key':'history_cached(ticker, as_of) / fundamentals_cached(ticker)',
            'production_cache_hit':None,'production_cache_age':None,
            'degraded_response_cached':'POSSIBLE_BY_SOURCE_CODE_NOT_RUNTIME_CONFIRMED',
            'session_batch_has_no_ttl':True,'session_batch_generated_at':(production_report or {}).get('generated_at'),
            'diagnostic_bypasses_streamlit_fundamentals_cache':True,'policy_changed':False},
        'source_audit':{'production_info_path':'get_info; info only when result empty; fast_info shares/market_cap/price',
            'partial_nonempty_info_skips_info_alternative':True,'info_get_info_independent':False,
            'forward_eps_estimate_path':'existing get_earnings_estimate fallback; not invoked by this provider audit',
            'root_network_failure':'UNCONFIRMED_UNTIL_CLOUD_RUNTIME_EXPORT',
            'production_repeated_http_requests':'UNOBSERVABLE_FROM_METHOD_COUNTS'}}
