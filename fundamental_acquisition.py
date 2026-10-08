"""V4.8.2 acquisition-only resilience. No valuation/result/Last Reliable cache."""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime,timezone,timedelta
import os
import re
import threading
import time
from uuid import uuid4

from valuation_primitives import fnum

VERSION='v4.8.2'
HEALTH_TTLS={'HEALTHY':900,'PARTIAL':300,'DEGRADED':60,'UNAVAILABLE':60}
ENABLE_QUALITY_AWARE_FUNDAMENTALS_CACHE=True
ENABLE_ONE_SHOT_FRESH_RECOVERY=True
ENABLE_YAHOO_SPLIT_FALLBACK=True
ENABLE_QUOTE_CURRENCY_FALLBACK=True
ENABLE_FINNHUB_PRICE_FALLBACK=True
ENABLE_FINNHUB_TRAILING_EPS_FALLBACK=False
ENABLE_DERIVED_FORWARD_EPS_PRODUCTION=False


@dataclass(frozen=True)
class Flags:
    quality_cache:bool=True
    fresh_recovery:bool=True
    split_fallback:bool=True
    currency_fallback:bool=True
    price_fallback:bool=True
    trailing_fallback:bool=False
    derived_forward_eps:bool=False


def flags():
    names=('QUALITY_AWARE_FUNDAMENTALS_CACHE','ONE_SHOT_FRESH_RECOVERY','YAHOO_SPLIT_FALLBACK',
        'QUOTE_CURRENCY_FALLBACK','FINNHUB_PRICE_FALLBACK','FINNHUB_TRAILING_EPS_FALLBACK')
    values=[]
    for name in names:
        default=globals()['ENABLE_'+name]
        values.append(str(os.environ.get('ENABLE_'+name,str(default))).lower() in ('1','true','yes'))
    # Deliberately cannot enable derived EPS through configuration.
    return Flags(*values,False)


def now():return datetime.now(timezone.utc)


def positive(v):return fnum(v) is not None and fnum(v)>0


def currency(v):return v if isinstance(v,str) and re.fullmatch('[A-Z]{3}',v) else None


def split_ratio(v):
    if isinstance(v,str) and (':' in v or '/' in v):
        try:
            a,b=re.split('[:/]',v);value=float(a)/float(b)
        except (ValueError,ZeroDivisionError):return None
    else:value=fnum(v)
    return value if value is not None and value>0 else None


def split_day(v):
    try:
        if isinstance(v,(int,float)):return datetime.fromtimestamp(v,timezone.utc).date().isoformat()
        return datetime.fromisoformat(str(v).replace('Z','+00:00')).date().isoformat()
    except (TypeError,ValueError,OverflowError,OSError):return None


def field_policy(ticker,info,*,required_models=None,require_split=None):
    if required_models is None:
        from valuation_engine import build_profile
        required_models=build_profile(ticker,{'sector':info.get('sector'),'industry':info.get('industry'),
            'quote_type':info.get('quoteType'),'forward_eps':info.get('forwardEps')}).preferred_models
    models=set(required_models)
    enterprise=bool(models & {'normalized_fcf_dcf','ev_ebitda','revenue_multiple','price_to_book_roe','residual_income'})
    shares,implied=fnum(info.get('sharesOutstanding')),fnum(info.get('impliedSharesOutstanding'))
    basis_uncertain=bool(shares and implied and abs(implied/shares-1)>.2)
    return {'forward_eps_required':bool(models & {'forward_pe','growth_adjusted_pe'}),
        'financial_currency_required':enterprise,
        'share_context_required':enterprise,'split_context_required':basis_uncertain if require_split is None else require_split,
        'models':sorted(models)}


@dataclass(frozen=True)
class FundamentalFieldHealth:
    overall_state:str
    critical_missing_fields:tuple
    missing_fields:tuple
    groups:dict

    def to_dict(self):return {'overall_state':self.overall_state,
        'critical_missing_fields':list(self.critical_missing_fields),'missing_fields':list(self.missing_fields),
        'groups':deepcopy(self.groups)}


def health(ticker,info,*,policy=None):
    policy=policy or field_policy(ticker,info)
    available={'current_price':positive(info.get('currentPrice') or info.get('regularMarketPrice')),
        'market_cap':positive(info.get('marketCap')),'quote_currency':bool(currency(info.get('currency'))),
        'financial_currency':bool(currency(info.get('financialCurrency') or info.get('financialCurrencyCode'))),
        'forward_eps':positive(info.get('forwardEps')),'trailing_eps':positive(info.get('trailingEps')),
        'forward_pe':positive(info.get('forwardPE')),
        'share_candidate':positive(info.get('sharesOutstanding')) or positive(info.get('impliedSharesOutstanding'))
            or positive(info.get('marketCap')) and positive(info.get('currentPrice') or info.get('regularMarketPrice')),
        'split_context':info.get('lastSplitDate') is not None and split_ratio(info.get('lastSplitFactor')) is not None,
        'cash':fnum(info.get('totalCash')) is not None,'debt':fnum(info.get('totalDebt')) is not None,
        'ebitda':fnum(info.get('ebitda')) is not None,'revenue':positive(info.get('totalRevenue'))}
    groups={'CORE_MARKET_IDENTITY':['current_price','market_cap','quote_currency'],
        'EARNINGS_VALUATION':['forward_eps','trailing_eps','forward_pe'] if policy['forward_eps_required'] else [],
        'CURRENCY_CONTEXT':['quote_currency']+(['financial_currency'] if policy['financial_currency_required'] else []),
        'SHARE_CONTEXT':['share_candidate']+(['split_context'] if policy['split_context_required'] else []) if policy['share_context_required'] else [],
        'ENTERPRISE_INPUTS':[f for f in ('cash','debt','ebitda','revenue') if
            f in ('cash','debt') and bool(set(policy['models']) & {'normalized_fcf_dcf','ev_ebitda','revenue_multiple'})
            or f=='ebitda' and 'ev_ebitda' in policy['models'] or f=='revenue' and 'revenue_multiple' in policy['models']]}
    required={'current_price','market_cap','quote_currency'}
    if policy['forward_eps_required']:required.add('forward_eps')
    if policy['financial_currency_required']:required.add('financial_currency')
    if policy['share_context_required']:required.add('share_candidate')
    if policy['split_context_required']:required.add('split_context')
    critical=tuple(sorted(f for f in required if not available[f]))
    relevant=set(f for fields in groups.values() for f in fields)
    missing=tuple(sorted(f for f in relevant if not available[f]))
    state='UNAVAILABLE' if not any(available.values()) else 'DEGRADED' if critical else 'PARTIAL' if missing else 'HEALTHY'
    return FundamentalFieldHealth(state,critical,missing,
        {name:{'fields':fields,'missing':[f for f in fields if not available[f]]} for name,fields in groups.items()})


def exchange(v):
    text=re.sub('[^A-Z]','',str(v or '').upper())
    if text in ('NMS','NGM','NCM','NASDAQ','NASDAQGS','NASDAQGM','NASDAQCM') or text.startswith('NASDAQ'):return 'NASDAQ'
    if text in ('NYQ','NYSE','NEWYORKSTOCKEXCHANGE'):return 'NYSE'
    return text or None


def get_value(obj,key):
    try:return obj.get(key) if hasattr(obj,'get') else obj[key]
    except Exception:return None


def acquire(ticker,factory,*,provider=None,options=None,policy=None):
    options=options or flags();ticker=ticker.upper();t=factory(ticker);acquired=now().isoformat()
    calls={};errors={}
    def attempt(name,fn):
        calls[name]=calls.get(name,0)+1
        try:return fn()
        except Exception as exc:errors[name]=type(exc).__name__;return None
    primary=attempt('yahoo.get_info',lambda:t.get_info())
    primary=deepcopy(primary) if isinstance(primary,dict) else {}
    path='yahoo.get_info'
    if not primary:
        fallback=attempt('yahoo.info',lambda:t.info)
        if isinstance(fallback,dict):primary=deepcopy(fallback);path='yahoo.info'
    if str(primary.get('symbol') or ticker).upper()!=ticker:
        raise ValueError('Yahoo ticker identity mismatch')
    info=deepcopy(primary);policy=policy or field_policy(ticker,primary)
    before=health(ticker,primary,policy=policy);recovery=False;accepted=False;recovered=[]
    if primary and before.overall_state=='DEGRADED' and options.fresh_recovery:
        recovery=True
        fresh=attempt('yahoo.fresh_get_info',lambda:factory(ticker).get_info())
        if isinstance(fresh,dict) and str(fresh.get('symbol') or ticker).upper()==ticker:
            after=health(ticker,fresh,policy=policy)
            # Accept whole response only; never fill two partial info dictionaries.
            if set(after.critical_missing_fields)<set(before.critical_missing_fields):
                info=deepcopy(fresh);accepted=True;path='yahoo.fresh_get_info'
                recovered=sorted(set(before.critical_missing_fields)-set(after.critical_missing_fields))
    source={key:path+'.'+key for key in info}
    # Existing fast-info candidates; no canonical share resolver changes.
    fast=attempt('yahoo.fast_info',lambda:t.fast_info)
    for target,keys in (('sharesOutstanding',('shares','sharesOutstanding')),('marketCap',('market_cap','marketCap')),
        ('currentPrice',('last_price','lastPrice','regularMarketPrice'))):
        if fnum(info.get(target)) is None:
            value=next((get_value(fast,k) for k in keys if fnum(get_value(fast,k)) is not None),None)
            if value is not None:info[target]=value;source[target]='yahoo.fast_info.'+keys[0]
    used=[];validation='PRIMARY_DIRECT' if currency(info.get('currency')) else 'UNRESOLVED'
    listing_conflict=False;currency_sources={};profile=None
    def load_profile():
        nonlocal profile,provider
        if profile is None:
            if provider is None:
                from finnhub_service import get_finnhub_provider
                provider=get_finnhub_provider()
            result=attempt('finnhub.profile2',lambda:provider.get_company_profile(ticker)) or {}
            profile=result.get('data') if result.get('status')=='AVAILABLE' else {}
        return profile or {}
    def valid_profile(p,metadata):
        identity=str(p.get('ticker') or '').upper()==ticker
        a=exchange(info.get('exchange') or metadata.get('exchangeName'));b=exchange(p.get('exchange'))
        return identity and bool(a and b and a==b)
    if not currency(info.get('currency')) and options.currency_fallback:
        metadata=attempt('yahoo.history_metadata',lambda:t.get_history_metadata()) or {}
        if not isinstance(metadata,dict):metadata={}
        actual=str(metadata.get('symbol') or ticker).upper()
        listing_conflict=actual!=ticker or bool(exchange(info.get('exchange')) and exchange(metadata.get('exchangeName'))
            and exchange(info.get('exchange'))!=exchange(metadata.get('exchangeName')))
        if currency(metadata.get('currency')):currency_sources['yahoo.history_metadata.currency']=metadata['currency']
        fast_currency=currency(get_value(fast,'currency'))
        if fast_currency:currency_sources['yahoo.fast_info.currency']=fast_currency
        p=load_profile()
        if p:
            if valid_profile(p,metadata):
                if currency(p.get('currency')):currency_sources['finnhub.profile2.currency']=p['currency']
            elif p.get('ticker') and str(p['ticker']).upper()!=ticker or (exchange(p.get('exchange'))
                and exchange(info.get('exchange') or metadata.get('exchangeName'))
                and exchange(p.get('exchange'))!=exchange(info.get('exchange') or metadata.get('exchangeName'))):
                listing_conflict=True
        if listing_conflict:validation='LISTING_IDENTITY_CONFLICT'
        elif len(set(currency_sources.values()))>1:validation='CURRENCY_PROVIDER_CONFLICT'
        elif currency_sources:
            chosen=next(iter(currency_sources));info['currency']=currency_sources[chosen]
            source['currency']=chosen;used.append('quote_currency');validation='DIRECT_SOURCES_AGREE'
        if validation in ('LISTING_IDENTITY_CONFLICT','CURRENCY_PROVIDER_CONFLICT'):info.pop('currency',None)
    if not positive(info.get('currentPrice') or info.get('regularMarketPrice')) and options.price_fallback:
        p=load_profile()
        if valid_profile(p,{}) and currency(info.get('currency'))==currency(p.get('currency')) and currency(info.get('currency')):
            q=attempt('finnhub.quote',lambda:provider.get_quote(ticker)) or {}
            data=q.get('data') or {};qt=fnum(data.get('t'))
            if q.get('status')=='AVAILABLE' and positive(data.get('c')) and qt and 0<=now().timestamp()-qt<=600:
                info['currentPrice']=data['c'];source['currentPrice']='finnhub.quote.c';used.append('current_price')
    if options.split_fallback and (info.get('lastSplitDate') is None or split_ratio(info.get('lastSplitFactor')) is None):
        splits=attempt('yahoo.splits',lambda:t.splits)
        if splits is not None and not getattr(splits,'empty',True):
            try:
                valid=splits.dropna().sort_index();valid=valid[valid>0]
                # yfinance splits property uses full history (period=max); nonempty valid series.
                identity=getattr(t,'ticker',ticker)
                if len(valid) and (not isinstance(identity,str) or identity.upper()==ticker) and valid.index[-1].date()<=now().date():
                    info['lastSplitDate']=int(valid.index[-1].timestamp());info['lastSplitFactor']=split_ratio(valid.iloc[-1])
                    source['lastSplitDate']=source['lastSplitFactor']='yahoo.splits';used.append('split_context')
            except Exception:errors['yahoo.splits']='INVALID_SPLIT_SERIES'
    if options.trailing_fallback and not positive(info.get('trailingEps')):
        # Flag deliberately records a candidate only until period/basis validation exists.
        errors['finnhub.trailing_eps']='VALIDATION_REQUIRED_NOT_ENABLED_FOR_AUTOMATIC_USE'
    final=health(ticker,info,policy=policy)
    if validation in ('CURRENCY_PROVIDER_CONFLICT','LISTING_IDENTITY_CONFLICT'):
        final=health(ticker,info,policy=policy)
    meta={'input_resilience_policy_version':VERSION,'fundamentals_acquisition_id':str(uuid4()),
        'acquired_at':acquired,'source_path':path,'health_state':final.overall_state,
        'critical_missing_fields':list(final.critical_missing_fields),
        'primary_health':before.to_dict(),'final_health':final.to_dict(),
        'fresh_recovery_attempted':recovery,'fresh_recovery_reason':list(before.critical_missing_fields) if recovery else [],
        'fresh_recovery_result':'ACCEPT_RECOVERY' if accepted else 'REJECT_NO_HEALTH_IMPROVEMENT' if recovery else 'NOT_ATTEMPTED',
        'fresh_recovery_used':accepted,'quote_currency_source':source.get('currency'),
        'quote_currency_fallback_used':'quote_currency' in used,'quote_currency_validation':validation,
        'quote_currency_direct_sources':currency_sources,'split_source':source.get('lastSplitFactor'),
        'split_fallback_used':'split_context' in used,'logical_calls':calls,'http_count':'HTTP_COUNT_UNAVAILABLE',
        'exception_categories':errors,'field_sources':source,
        'provider_health':{'overall_state':final.overall_state,'critical_missing_fields':list(final.critical_missing_fields),
            'recovered_fields':recovered,'recovery_attempted':recovery,'recovery_succeeded':accepted,
            'fallback_fields_used':used,'degraded_cache_used':False,'health_reasons':list(final.missing_fields)}}
    return info,RecordingTicker(t),meta


class RecordingTicker:
    """Cache public raw statement/estimate payloads, never the network client."""
    def __init__(self,ticker=None,recorded=None):self._ticker=ticker;self.recorded=deepcopy(recorded or {})
    def __getattr__(self,name):
        method=name.startswith('get_')
        def read():
            if name not in self.recorded:
                try:
                    value=getattr(self._ticker,name,None) if self._ticker is not None else None
                    self.recorded[name]=deepcopy(value() if callable(value) else value)
                except Exception:self.recorded[name]=None
            return deepcopy(self.recorded[name])
        return (lambda *a,**kw:read()) if method else read()


_SCOPE=ContextVar('fundamentals_request_scope',default=None)


@contextmanager
def acquisition_batch(batch_id=None,*,force_refresh=False,simulation=False):
    context={'batch_id':batch_id or str(uuid4()),'request_scope_cache':{},'force_refresh':force_refresh,
        'simulation':simulation}
    token=_SCOPE.set(context)
    try:yield context
    finally:_SCOPE.reset(token)


class RawAcquisitionCache:
    def __init__(self,clock=time.monotonic):
        self.clock=clock;self.entries={};self.lock=threading.RLock()
        self.counters={k:0 for k in ('degraded_cache_write_count','degraded_cache_hit_count',
            'healthy_cache_hit_count','fresh_recovery_count','fresh_recovery_success_count','logical_acquisition_count')}

    def get(self,ticker,*,factory,normalize,provider=None,options=None,force_refresh=False,simulation=False,allow_estimates=True):
        options=options or flags();scope=_SCOPE.get();batch_id=scope['batch_id'] if scope else str(uuid4())
        key=(ticker.upper(),factory,options,allow_estimates,VERSION)
        request_key=(batch_id,ticker.upper(),'fundamentals',options,allow_estimates)
        if scope and request_key in scope['request_scope_cache']:return deepcopy(scope['request_scope_cache'][request_key])
        force_refresh=force_refresh or bool(scope and scope['force_refresh'])
        simulation=simulation or bool(scope and scope['simulation'])
        with self.lock:
            entry=None if simulation else self.entries.get(key)
            expired=True
            if entry:
                # Health-based TTL checked in addition to stored expiry.
                ttl=HEALTH_TTLS.get(entry['meta']['health_state'],60)
                expired=self.clock()>=min(entry['expires'],entry['written']+ttl)
            hit=entry is not None and not expired and not force_refresh
            old=entry
            if hit:
                info=deepcopy(entry['info']);t=RecordingTicker(recorded=entry['recorded']);meta=deepcopy(entry['meta'])
                if not simulation:
                    k='healthy_cache_hit_count' if meta['health_state']=='HEALTHY' else 'degraded_cache_hit_count' if meta['health_state'] in ('DEGRADED','UNAVAILABLE') else None
                    if k:self.counters[k]+=1
            else:
                info,t,meta=acquire(ticker,factory,provider=provider,options=options)
                if not simulation:
                    self.counters['logical_acquisition_count']+=1
                    self.counters['fresh_recovery_count']+=int(meta['fresh_recovery_attempted'])
                    self.counters['fresh_recovery_success_count']+=int(meta['fresh_recovery_used'])
            # Public three-field observation and identity before normalization.
            # No raw dictionary or credentials are retained in the diagnostic metadata.
            meta.update(input_batch_id=batch_id,production_raw_fields={
                field:{'value':deepcopy(info.get(raw) if raw!='financialCurrency' else
                    info.get('financialCurrency') or info.get('financialCurrencyCode')),
                    'source':meta['field_sources'].get(raw) or
                        (meta['field_sources'].get('financialCurrencyCode') if raw=='financialCurrency' else None)}
                for field,raw in (('forward_eps','forwardEps'),('quote_currency','currency'),
                    ('financial_currency','financialCurrency'))})
            result=normalize(deepcopy(info),t,deepcopy(meta))
            promoted=False;fresh_degraded=False
            if not hit:
                ttl=HEALTH_TTLS[meta['health_state']]
                meta.update(expires_at=(now()+timedelta(seconds=ttl)).isoformat(),cache_policy_version=VERSION)
                if old and not expired and old['meta']['health_state']=='HEALTHY' and meta['health_state'] in ('DEGRADED','UNAVAILABLE'):
                    # Keep healthy raw cache, but current caller receives explicit degraded fresh input.
                    fresh_degraded=True
                    if not simulation:old['meta']['fresh_degraded_attempt_observed']=True
                elif not simulation:
                    promoted=bool(old and old['meta']['health_state'] in ('DEGRADED','UNAVAILABLE') and meta['health_state']=='HEALTHY')
                    if len(self.entries)>=512:self.entries.pop(next(iter(self.entries)))
                    self.entries[key]={'info':deepcopy(info),'recorded':deepcopy(t.recorded),
                        'meta':deepcopy(meta),'written':self.clock(),'expires':self.clock()+ttl}
                    if meta['health_state'] in ('DEGRADED','UNAVAILABLE'):self.counters['degraded_cache_write_count']+=1
            meta.update(input_batch_id=batch_id,cache_hit=hit,
                cache_age=max(0,self.clock()-old['written']) if hit else 0,
                cache_ttl=HEALTH_TTLS[meta['health_state']],cache_quality_promoted=promoted,
                fresh_degraded_attempt_observed=fresh_degraded or meta.get('fresh_degraded_attempt_observed',False),
                cache_write_performed=not simulation and not hit and not fresh_degraded,
                simulation=simulation)
            meta['statement_estimate_payloads']=sorted(t.recorded)
            meta['statement_estimate_method_invocations']={name:0 if hit else 1 for name in t.recorded}
            if hit:
                meta['origin_logical_calls']=deepcopy(meta['logical_calls'])
                meta['logical_calls']={}
            meta['fundamentals_source_status']=('cached_healthy' if meta['health_state'] in ('HEALTHY','PARTIAL') else 'degraded_cached') if hit else (
                'degraded_live' if meta['health_state'] in ('DEGRADED','UNAVAILABLE') else 'fresh_recovered' if meta['fresh_recovery_used'] else 'live')
            meta['provider_health']['degraded_cache_used']=hit and meta['health_state'] in ('DEGRADED','UNAVAILABLE')
            result.update(acquisition_metadata=meta,provider_health=deepcopy(meta['provider_health']),
                input_resilience_policy_version=VERSION,input_batch_id=batch_id,
                fundamentals_acquisition_id=meta['fundamentals_acquisition_id'],
                fundamentals_source_status=meta['fundamentals_source_status'])
            if scope:scope['request_scope_cache'][request_key]=deepcopy(result)
            return result

    def telemetry(self):
        with self.lock:return deepcopy(self.counters)


RAW_CACHE=RawAcquisitionCache()


def decorate_inputs(result,info,meta):
    """Provenance only; normalization and canonical resolver remain untouched."""
    sources=meta['field_sources'];acquired=meta['acquired_at'];records={}
    mapping={'current_price':'currentPrice','market_cap':'marketCap','quote_currency':'currency',
        'financial_currency':'financialCurrency','forward_eps':'forwardEps','trailing_eps':'trailingEps',
        'cash':'totalCash','debt':'totalDebt','ebitda':'ebitda','revenue':'totalRevenue',
        'shares_outstanding':'sharesOutstanding','implied_shares_outstanding':'impliedSharesOutstanding',
        'last_split_date':'lastSplitDate','last_split_factor':'lastSplitFactor'}
    for field,raw in mapping.items():
        source=sources.get(raw)
        if field=='financial_currency':source=source or sources.get('financialCurrencyCode')
        if field=='forward_eps' and result.get('forward_eps_source')=='earnings_estimate':source='existing_earnings_estimate_path'
        if field=='forward_eps' and result.get('forward_eps_source')=='epsForward':source=sources.get('epsForward')
        if field=='current_price':source=source or sources.get('regularMarketPrice')
        if not source and result.get(field) is not None:
            source='existing_normalization_or_statement_path'
        records[field]={'value':deepcopy(result.get(field)),'source':source or 'missing',
            'source_type':'DIRECT' if source and source!='existing_normalization_or_statement_path' else
                'EXISTING_NORMALIZATION' if source else 'UNAVAILABLE',
            'acquired_at':acquired,'fallback_used':bool(source and ('fresh_get_info' in source or
                source.startswith(('yahoo.history_metadata','yahoo.fast_info','finnhub.','yahoo.splits','existing_')))),
            'validation_status':meta['quote_currency_validation'] if field=='quote_currency' else 'EXISTING_RULES_UNCHANGED'}
    result['acquisition_provenance']=records
    result['forward_eps_acquisition_path']=records['forward_eps']['source']
    result['quote_currency_source']=meta['quote_currency_source']
    result['quote_currency_fallback_used']=meta['quote_currency_fallback_used']
    result['quote_currency_validation']=meta['quote_currency_validation']
    result['split_source']=meta['split_source'];result['split_fallback_used']=meta['split_fallback_used']
    statement=[]
    for name in ('cash','debt'):
        raw='totalCash' if name=='cash' else 'totalDebt'
        if fnum(info.get(raw)) is None:
            frames=[v for k,v in meta.get('statement_context',{}).items() if k=='balance_sheet']
            ctx=frames[0] if frames else {}
            statement.append({'field':name,'source':'existing_balance_sheet_fallback','period':ctx.get('period'),
                'field_name':ctx.get(name),'currency':result.get('financial_currency'),'as_of_date':ctx.get('period'),
                'metric_basis':'FY_OR_PROVIDER_STATEMENT_PERIOD','existing_rule':True})
            records[name].update(source='yahoo.balance_sheet.'+ctx[name] if ctx.get(name) else 'existing_missing_assumed_zero',
                source_type='DIRECT' if ctx.get(name) else 'INFERRED',fallback_used=True,
                period=ctx.get('period'),field_name=ctx.get(name),currency=result.get('financial_currency'),
                as_of_date=ctx.get('period'))
    ctx=meta.get('statement_context',{}).get('income_stmt',{})
    statement.append({'field':'diluted_average_shares','value':result.get('diluted_average_shares'),
        'source':'yahoo.income_stmt','period':ctx.get('period'),'field_name':ctx.get('diluted_average_shares'),
        'currency':result.get('financial_currency'),'as_of_date':ctx.get('period'),'metric_basis':'FY',
        'existing_rule':True})
    result['statement_acquisition_provenance']=statement
    result['enterprise_metric_basis']={k:'QUOTE_SUMMARY_TTM_OR_PROVIDER_CURRENT' if info.get(raw) is not None else 'UNKNOWN'
        for k,raw in (('ebitda','ebitda'),('revenue','totalRevenue'))}
    return result
