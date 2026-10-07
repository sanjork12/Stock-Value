"""Read-only Finnhub free-tier data, cached independently of valuation inputs."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from market_reference_provider import configured_api_key

TTL = {'quote':600,'stock/profile2':86400,'company-news':1200,'stock/metric':28800,
       'calendar/earnings':28800,'stock/earnings':86400,'stock/recommendation':43200}
METRICS = {'Forward PE':'forwardPE','TTM PE':'peTTM','P/B':'pbAnnual',
           'ROE TTM':'roeTTM','Operating Margin TTM':'operatingMarginTTM',
           'Revenue Growth TTM YoY':'revenueGrowthTTMYoy','EPS Growth TTM YoY':'epsGrowthTTMYoy',
           '52W High':'52WeekHigh','52W Low':'52WeekLow','Beta':'beta'}
# Forward PE is used only if the provider explicitly supplies a forward field.
STATUS_TEXT={'NOT_CONFIGURED':'实时新闻源未配置。','NO_DATA':'暂无数据','RATE_LIMIT':'请求限流，暂不可用',
             'NETWORK_ERROR':'网络异常，暂不可用','NOT_ENTITLED':'接口权限不足',
             'INVALID_RESPONSE':'数据格式异常','INVALID_SYMBOL':'股票代码无效'}


def number(value):
    if isinstance(value,bool):return None
    try:
        value=float(value)
        return value if math.isfinite(value) else None
    except (TypeError,ValueError):return None


def _fetch(path,params,key):
    request=Request('https://finnhub.io/api/v1/'+path+'?'+urlencode(params),
                    headers={'X-Finnhub-Token':key,'Accept':'application/json'})
    with urlopen(request,timeout=10) as response:return json.load(response)


class FinnhubProvider:
    def __init__(self,*,key_loader=configured_api_key,fetch=_fetch,clock=time.monotonic,sleep=time.sleep):
        self.key_loader,self.fetch,self.clock,self.sleep=key_loader,fetch,clock,sleep
        self._cache={};self._lock=threading.Lock();self._next=0;self._blocked=0

    def configured(self):return bool(self.key_loader())

    def _get(self,path,params):
        if path not in TTL:raise ValueError('Endpoint is not enabled for production')
        result={'source':'Finnhub','fetched_at':datetime.now(timezone.utc).isoformat(),'status':'NO_DATA','data':None}
        key=self.key_loader()
        if not key:result['status']='NOT_CONFIGURED';return result
        cache_key=(path,tuple(sorted(params.items())))
        with self._lock:
            now=self.clock()
            cached=self._cache.get(cache_key)
            if cached and cached[0]>now:return deepcopy(cached[1])
            if now<self._blocked:result['status']='RATE_LIMIT';return result
            for attempt in range(2):
                wait=self._next-self.clock()
                if wait>0:self.sleep(wait)
                self._next=self.clock()+1.2
                try:
                    payload=self.fetch(path,params,key)
                    if not isinstance(payload,(dict,list)):
                        result['status']='INVALID_RESPONSE'
                    elif isinstance(payload,dict) and payload.get('error'):
                        message=str(payload['error']).lower()
                        result['status']='RATE_LIMIT' if 'limit' in message else 'NOT_ENTITLED' if any(s in message for s in ('access','premium','api key')) else 'INVALID_RESPONSE'
                    else:
                        valid = True
                        if payload:
                            if path == 'stock/metric': valid = isinstance(payload,dict) and isinstance(payload.get('metric'),dict)
                            elif path == 'calendar/earnings': valid = isinstance(payload,dict) and isinstance(payload.get('earningsCalendar'),list)
                            elif path in ('company-news','stock/earnings','stock/recommendation'):
                                required = 'headline' if path == 'company-news' else 'period'
                                valid = isinstance(payload,list) and all(isinstance(row,dict) and required in row for row in payload)
                            elif path == 'quote': valid = isinstance(payload,dict) and 'c' in payload and 't' in payload
                            elif path == 'stock/profile2': valid = isinstance(payload,dict) and 'name' in payload
                        result['status']=('AVAILABLE' if payload else 'NO_DATA') if valid else 'INVALID_RESPONSE'
                        # Never cache provider strings containing credentials.
                        result['data']=json.loads(json.dumps(payload).replace(key,'[REDACTED]'))
                    break
                except HTTPError as exc:
                    if exc.code==429:
                        result['status']='RATE_LIMIT'
                        try:cooldown=min(3600,max(60,float(exc.headers.get('Retry-After',60))))
                        except (TypeError,ValueError,AttributeError):cooldown=60
                        self._blocked=self.clock()+cooldown
                        break
                    if exc.code>=500 and attempt==0:continue
                    result['status']='NOT_ENTITLED' if exc.code in (401,403) else 'INVALID_SYMBOL' if exc.code in (400,404) else 'NETWORK_ERROR'
                    break
                except (URLError,TimeoutError,OSError):
                    if attempt==0:continue
                    result['status']='NETWORK_ERROR'
                except (ValueError,TypeError):
                    result['status']='INVALID_RESPONSE';break
            if result['status']=='RATE_LIMIT':self._blocked=max(self._blocked,self.clock()+60)
            ttl=TTL[path] if result['status'] in ('AVAILABLE','NO_DATA') else 60
            # Bound process memory; cache contains only public market data.
            if len(self._cache)>=2048:self._cache.pop(next(iter(self._cache)))
            self._cache[cache_key]=(self.clock()+ttl,deepcopy(result))
            return result

    def _symbol(self,path,ticker,**params):
        ticker=str(ticker or '').strip().upper()
        if not re.fullmatch(r'[A-Z0-9][A-Z0-9.\-:]{0,24}',ticker):
            return {'source':'Finnhub','fetched_at':datetime.now(timezone.utc).isoformat(),'status':'INVALID_SYMBOL','data':None}
        return self._get(path,{'symbol':ticker,**params})

    @staticmethod
    def _normalize(result,data,valid=True):
        result=dict(result)
        if result['status']=='AVAILABLE':
            result['status']='AVAILABLE' if valid and data else 'NO_DATA' if valid else 'INVALID_RESPONSE'
        result['data']=data
        return result

    def get_quote(self,ticker):
        r=self._symbol('quote',ticker);p=r['data']
        valid=isinstance(p,dict)
        data={key:number(p.get(key)) for key in ('c','d','dp','h','l','o','pc','t')} if valid else None
        if data and (not data['c'] or data['c']<=0 or not data['t']):data=None
        return self._normalize(r,data,valid)

    def get_company_profile(self,ticker):
        r=self._symbol('stock/profile2',ticker);p=r['data']
        data={key:p.get(key) for key in ('name','ticker','country','exchange','finnhubIndustry','currency','marketCapitalization','shareOutstanding')} if isinstance(p,dict) and p.get('name') else None
        if data:
            for key in ('marketCapitalization','shareOutstanding'):data[key]=number(data.get(key))
        return self._normalize(r,data,isinstance(p,dict))

    def get_company_news(self,ticker,start_date,end_date):
        # The UI windows are bounded to one quarter; reject unbounded callers.
        from datetime import date
        start,end=date.fromisoformat(str(start_date)[:10]),date.fromisoformat(str(end_date)[:10])
        if end<start or (end-start).days>100:raise ValueError('News window must be <=100 days')
        r=self._symbol('company-news',ticker,**{'from':start.isoformat(),'to':end.isoformat()})
        rows=r['data'];valid=isinstance(rows,list) and all(isinstance(x,dict) for x in rows)
        data=[{key:row.get(key) for key in ('id','headline','datetime','source','summary','url','category','related')} for row in rows] if valid else []
        return self._normalize(r,data,valid)

    def get_basic_financials(self,ticker):
        r=self._symbol('stock/metric',ticker,metric='all');p=r['data']
        m=p.get('metric') if isinstance(p,dict) else None
        data={label:number(m.get(key)) for label,key in METRICS.items()} if isinstance(m,dict) else {}
        data={k:v for k,v in data.items() if v is not None}
        return self._normalize(r,data,isinstance(m,dict))

    def get_earnings_calendar(self,start_date,end_date):
        r=self._get('calendar/earnings',{'from':str(start_date)[:10],'to':str(end_date)[:10]})
        p=r['data'];rows=p.get('earningsCalendar') if isinstance(p,dict) else None
        valid=isinstance(rows,list) and all(isinstance(x,dict) for x in rows)
        data=[{k:row.get(k) for k in ('symbol','date','hour','quarter','year','epsEstimate','epsActual','revenueEstimate','revenueActual')} for row in rows] if valid else []
        return self._normalize(r,data,valid)

    def get_earnings_surprises(self,ticker):
        r=self._symbol('stock/earnings',ticker,limit=4);rows=r['data']
        valid=isinstance(rows,list) and all(isinstance(x,dict) for x in rows)
        data=[]
        for row in sorted(rows if valid else [],key=lambda x:str(x.get('period') or ''),reverse=True)[:4]:
            actual,estimate=number(row.get('actual')),number(row.get('estimate'))
            outcome='—' if actual is None or estimate is None else 'Beat' if actual>estimate else 'Miss' if actual<estimate else 'In line'
            data.append({'Period':row.get('period'),'EPS Actual':actual,'EPS Estimate':estimate,'Surprise %':number(row.get('surprisePercent')),'Beat/Miss':outcome})
        return self._normalize(r,data,valid)

    def get_recommendation_trends(self,ticker):
        r=self._symbol('stock/recommendation',ticker);rows=r['data']
        valid=isinstance(rows,list) and all(isinstance(x,dict) for x in rows)
        data=[{'Period':row.get('period'),**{label:number(row.get(key)) for label,key in [('Strong Buy','strongBuy'),('Buy','buy'),('Hold','hold'),('Sell','sell'),('Strong Sell','strongSell')]}} for row in sorted(rows if valid else [],key=lambda x:str(x.get('period') or ''),reverse=True)[:4]]
        return self._normalize(r,data,valid)


_provider=FinnhubProvider()
def get_finnhub_provider():return _provider


def external_sanity_warnings(internal,quote,metrics):
    warnings=[]
    primary=number(internal.get('price'));external=number((quote.get('data') or {}).get('c'))
    if primary and external and abs(external/primary-1)>.02:
        warnings.append('Finnhub 报价与当前价格差异超过 2%，请核对报价时点。')
    f=internal.get('financials') or {};m=metrics.get('data') or {}
    eps=number(f.get('forward_eps'))
    pairs=[(primary/eps if primary and eps and eps>0 else None,m.get('Forward PE')),
           (number(f.get('roe'))*100 if number(f.get('roe')) is not None else None,m.get('ROE TTM'))]
    if any(a is not None and b is not None and abs(a-b)/max(abs(a),1e-6)>.25 for a,b in pairs):
        warnings.append('外部财务参考与内部数据存在较大差异；数据期间和口径可能不同。')
    return warnings
