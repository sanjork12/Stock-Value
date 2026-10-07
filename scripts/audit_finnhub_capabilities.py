"""Read-only Finnhub capability audit. No production imports or secret logging."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timedelta
import json
import math
import os
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
TICKERS = ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOG', 'JPM', 'TSLA']
# name: (official path, response shape, meaningful fields, product value)
SPECS = {
 'quote': ('quote','object', ['c','d','dp','h','l','o','pc','t'], 'P3 / 自选股：Yahoo 报价校验或 fallback'),
 'company_profile': ('stock/profile2','object',['name','ticker','exchange','finnhubIndustry','country','currency','marketCapitalization','shareOutstanding'],'LOW/MEDIUM / 产业链地图：辅助元数据'),
 'company_news_1d': ('company-news','list',['headline','datetime','source','summary','url','category','related'],'P0 HIGH / 头等大事：新闻输入'),
 'company_news_7d': ('company-news','list',['headline','datetime','source','summary','url','category','related'],'P0 HIGH / 头等大事：新闻输入'),
 'basic_financials': ('stock/metric','metric',['52WeekHigh','52WeekLow','peTTM','peExclExtraTTM','pbAnnual','roeTTM','revenueGrowth','epsGrowth','currentRatio','beta'],'P1 / 单股分析、自选股：财务交叉校验'),
 'earnings_calendar': ('calendar/earnings','earningsCalendar',['date','epsEstimate','epsActual','revenueEstimate','revenueActual','hour','quarter','year','symbol'],'P0 HIGH / 头等大事：未来30天财报'),
 'earnings_surprises': ('stock/earnings','list',['actual','estimate','period','quarter','surprise','surprisePercent'],'P1 HIGH/MEDIUM / 单股分析、头等大事：EPS 预期差'),
 'recommendations': ('stock/recommendation','list',['buy','hold','sell','strongBuy','strongSell','period','symbol'],'P2 MEDIUM / 单股分析：分析师观点趋势'),
 'price_target': ('stock/price-target','object',['targetMean','targetHigh','targetLow','targetMedian','lastUpdated'],'MEDIUM / 市场一致目标，需实际权限'),
 'eps_estimates': ('stock/eps-estimate','data',['epsAvg','epsHigh','epsLow','period','numberAnalysts'],'MEDIUM / 单股分析：前瞻 EPS 外部参考'),
 'revenue_estimates': ('stock/revenue-estimate','data',['revenueAvg','revenueHigh','revenueLow','period','numberAnalysts'],'MEDIUM / 单股分析：收入外部参考'),
 'candles': ('stock/candle','candles',['c','h','l','o','t','v','s'],'LOW / Yahoo 日线交叉校验'),
 'technical_indicator': ('indicator','candles',['c','h','l','o','t','v','s','sma'],'LOW / 技术指标交叉校验'),
 'support_resistance': ('scan/support-resistance','levels',['levels'],'LOW / 技术参考，保持现有区间规则'),
 'pattern_recognition': ('scan/pattern','points',['points'],'LOW / 技术参考'),
}
STATES = {'AVAILABLE','NO_DATA','NOT_ENTITLED','RATE_LIMIT','NETWORK_ERROR','INVALID_RESPONSE','NOT_AVAILABLE'}


def load_api_key(root=ROOT):
    """Environment or Streamlit TOML files, without importing the UI runtime."""
    key = os.environ.get('FINNHUB_API_KEY', '').strip()
    if not key:
        import tomllib
        for path in (Path(root)/'.streamlit/secrets.toml', Path.home()/'.streamlit/secrets.toml'):
            try:
                value = tomllib.loads(path.read_text(encoding='utf-8-sig')).get('FINNHUB_API_KEY')
                if isinstance(value, str) and value.strip():
                    key = value.strip()
                    break
            except (OSError, ValueError):
                continue
    return key if key and key not in {'...', 'YOUR_FINNHUB_API_KEY'} else None


def error_status(code=None, message=''):
    message = str(message).lower()
    if code == 429 or 'rate limit' in message or 'too many requests' in message:
        return 'RATE_LIMIT'
    if code in (401,403) or any(word in message for word in ("don't have access", 'do not have access', 'premium', 'not entitled', 'invalid api key', 'unauthorized')):
        return 'NOT_ENTITLED'
    if code in (404,405,410):
        return 'NOT_AVAILABLE'
    return 'NETWORK_ERROR' if code and code >= 500 else 'INVALID_RESPONSE'


def classify_response(name, payload):
    shape, expected = SPECS[name][1:3]
    if isinstance(payload, dict) and payload.get('error'):
        return {'status':error_status(message=payload['error']), 'fields':[], 'reason':'provider_error'}
    if payload is None or payload == {} or payload == []:
        return {'status':'NO_DATA','fields':[]}
    if not isinstance(payload,(dict,list)):
        return {'status':'INVALID_RESPONSE','fields':[]}
    top_keys = sorted(payload) if isinstance(payload,dict) else []
    if shape in ('metric','earningsCalendar','data','levels','points'):
        if not isinstance(payload,dict) or shape not in payload:
            return {'status':'INVALID_RESPONSE','fields':top_keys}
        value=payload[shape]
    else:
        value=payload
    if shape == 'candles':
        if not isinstance(value,dict):
            return {'status':'INVALID_RESPONSE','fields':[]}
        if value.get('s') == 'no_data':
            return {'status':'NO_DATA','fields':sorted(value)}
        if value.get('s') != 'ok' or not isinstance(value.get('c'),list) or not value['c']:
            return {'status':'INVALID_RESPONSE','fields':sorted(value)}
        count=len(value['c'])
        if not all(isinstance(value.get(k),list) and len(value[k])==count for k in ('h','l','o','t','v')):
            return {'status':'INVALID_RESPONSE','fields':sorted(value)}
    if value == [] or value == {}:
        return {'status':'NO_DATA','fields':[], 'top_level_fields':top_keys}
    if shape in ('list','data','earningsCalendar','points'):
        if not isinstance(value,list) or not all(isinstance(row,dict) for row in value):
            return {'status':'INVALID_RESPONSE','fields':top_keys}
        fields=sorted({k for row in value for k in row})
        count=len(value)
    elif shape == 'levels':
        if not isinstance(value,list) or not all(isinstance(x,(int,float)) and math.isfinite(x) for x in value):
            return {'status':'INVALID_RESPONSE','fields':top_keys}
        fields=top_keys;count=len(value)
    else:
        if not isinstance(value,dict):
            return {'status':'INVALID_RESPONSE','fields':[]}
        fields=sorted(value); count=1
    if not set(fields).intersection(expected):
        return {'status':'INVALID_RESPONSE','fields':fields}
    if name == 'quote' and (not isinstance(value.get('c'),(int,float)) or value['c'] <= 0 or not value.get('t')):
        return {'status':'NO_DATA','fields':fields}
    if name == 'price_target' and (not isinstance(value.get('targetMean'),(int,float)) or value['targetMean'] <= 0):
        return {'status':'NO_DATA','fields':fields}
    result={'status':'AVAILABLE','fields':fields,'top_level_fields':top_keys,'record_count':count,
            'expected_fields_present':sorted(set(fields).intersection(expected))}
    if shape == 'metric':
        result['non_null_fields']=sorted(k for k,v in value.items() if v is not None)
    if name == 'earnings_calendar':
        result['events']=[{k:row.get(k) for k in ('symbol','date','hour','quarter','year')} for row in value]
    return result


def params_for(name, ticker, today):
    params={'symbol':ticker}
    start=today-timedelta(days=90)
    if name.startswith('company_news'):
        days=1 if name.endswith('1d') else 7
        params.update({'from':(today-timedelta(days=days)).isoformat(),'to':today.isoformat()})
    elif name == 'earnings_calendar':
        params.update({'from':today.isoformat(),'to':(today+timedelta(days=30)).isoformat()})
    elif name == 'basic_financials':params['metric']='all'
    elif name in ('eps_estimates','revenue_estimates'):params['freq']='quarterly'
    elif name == 'earnings_surprises':params['limit']=4
    elif name in ('candles','technical_indicator'):
        params.update({'resolution':'D','from':int(datetime.combine(start,datetime.min.time(),ZoneInfo('Europe/London')).timestamp()),'to':int(datetime.combine(today,datetime.max.time(),ZoneInfo('Europe/London')).timestamp())})
        if name == 'technical_indicator':params.update({'indicator':'sma','timeperiod':30})
    elif name in ('support_resistance','pattern_recognition'):params['resolution']='D'
    return params


def probe(name,ticker,key,today,opener=urlopen):
    request=Request('https://finnhub.io/api/v1/'+SPECS[name][0]+'?'+urlencode(params_for(name,ticker,today)),headers={'X-Finnhub-Token':key,'Accept':'application/json'})
    try:
        with opener(request,timeout=15) as response:payload=json.load(response)
        return classify_response(name,payload)
    except HTTPError as exc:
        try:message=exc.read(8192).decode('utf-8',errors='replace')
        except Exception:message=''
        # Raw messages and URLs are never persisted.
        return {'status':error_status(exc.code,message),'http_status':exc.code,'fields':[],
                'reason':'authentication_or_entitlement' if exc.code in (401,403) else 'http_error'}
    except (URLError,TimeoutError,OSError):return {'status':'NETWORK_ERROR','fields':[]}
    except (ValueError,TypeError):return {'status':'INVALID_RESPONSE','fields':[]}


def run_audit(key, tickers=None, delay=1.2, sleep=time.sleep, probe_fn=probe, progress=None):
    now=datetime.now(ZoneInfo('Europe/London'))
    report={'tested_at':now.isoformat(),'timezone':'Europe/London','audit_status':'COMPLETED' if key else 'BLOCKED_MISSING_KEY',
            'tickers':tickers or TICKERS,'endpoints':{},'planned_endpoints':{k:v[0] for k,v in SPECS.items()},
            'requests_sent':0,'rate_limit_observed':False,'key_saved':False}
    if not key:
        report['limitation']='No configured FINNHUB_API_KEY. No endpoints were tested; no entitlement conclusions are possible.'
        return report
    for name in SPECS:
        report['endpoints'][name]={}
        for ticker in report['tickers']:
            if report['requests_sent']:sleep(max(1.2,delay))
            item=probe_fn(name,ticker,key,now.date())
            report['requests_sent']+=1
            report['endpoints'][name][ticker]=item
            if progress:
                progress(name,ticker,report['requests_sent'],len(SPECS)*len(report['tickers']))
            if item['status']=='RATE_LIMIT':
                report['rate_limit_observed']=True
                report['audit_status']='PARTIAL_RATE_LIMIT'
                report['limitation']='Stopped on first RATE_LIMIT; untested pairs are omitted, not inferred.'
                return report
    return report


def render_markdown(report):
    lines=['# Finnhub capability audit', '',f"Time: {report['tested_at']}",f"Audit: {report['audit_status']}",
           f"Actual requests: {report['requests_sent']}",report.get('limitation',''),'',
           '| Capability | Endpoint | Key status | Coverage | Product value (if AVAILABLE) |',
           '|---|---|---|---|---|']
    for name,(path,_,_,value) in SPECS.items():
        results=report['endpoints'].get(name,{})
        counts=Counter(r['status'] for r in results.values())
        status=', '.join(f'{k} {v}' for k,v in counts.items()) or 'NOT TESTED'
        coverage=f"{counts.get('AVAILABLE',0)}/{len(report['tickers'])} available; {len(results)} tested"
        lines.append(f'| {name} | `{path}` | {status} | {coverage} | {value} |')
    lines+=['','## Actual field coverage']
    for name,results in report['endpoints'].items():
        for ticker,result in results.items():
            lines.append(f"- {name} / {ticker}: {result['status']}; keys: {', '.join(result.get('fields',[])) or '(none)'}")
    lines+=['','## Page mapping and integration priorities',
      'All recommendations below are conditional on AVAILABLE results. No free capability is confirmed when the audit is blocked.',
      '- 头等大事 — P0/HIGH: company news → watchlist filter → deduplication → importance classification → Chinese structured summaries; earnings calendar → upcoming events. EPS surprises P1/HIGH–MEDIUM; this endpoint does not establish revenue beat/miss.',
      '- 单股分析 — P1: metrics and EPS surprises in external reference; P2/MEDIUM: recommendation trends and entitled EPS/revenue estimates. Recommendations are sentiment, not buy/sell instructions.',
      '- 自选股 — P3: Yahoo primary; Finnhub quote validation/fallback. Metrics are auxiliary sanity checks, not internal fair-value inputs.',
      '- 产业链地图 — LOW/MEDIUM: company profile for industry/country/exchange/market cap metadata. Preserve curated AI-stack classification.',
      '- 市场格局 — NO: Finnhub does not replace Market Snapshot sources such as Synergy/TrendForce for cloud, DRAM or HBM shares.',
      '- Price target — enable consensus columns only when usable. If NOT_ENTITLED/NOT_CONFIGURED, recommend hiding columns; this audit does not change production UI.',
      '', '## Limits and boundaries',
      'No model, weights, normalization, MOS, zones, RLS/Auth or production UI changes. No commit or push.',
      'One sequential request every >=1.2s; stop at first 429, no automatic retries. No key, URL credentials or raw error body in reports.',
      '401/403 classified NOT_ENTITLED in the requested seven-state schema; authentication_or_entitlement reason indicates invalid-key possibility. Do not infer plan access from an invalid key.',
      'NO_DATA means the tested window/symbol returned no data, not that the endpoint is unavailable. Next earnings dates can only be established from returned calendar events; a 30-day empty result is inconclusive.',
      'Source: [Finnhub official Python SDK endpoint definitions](https://github.com/Finnhub-Stock-API/finnhub-python/blob/master/finnhub/client.py). Documentation confirms routes, not this account’s entitlements.']
    return '\n'.join(lines)+'\n'


def write_reports(report, output, secret=None):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    texts={'finnhub_capability_report.json':json.dumps(report,ensure_ascii=False,indent=2),
           'finnhub_capability_report.md':render_markdown(report)}
    for name,text in texts.items():
        if secret and secret in text:text=text.replace(secret,'[REDACTED]')
        (output/name).write_text(text,encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extended',action='store_true')
    parser.add_argument('--output',type=Path,default=ROOT/'output')
    args=parser.parse_args()
    key=load_api_key()
    tickers=TICKERS+(['MU','META','AVGO','PLTR'] if args.extended else [])
    report=run_audit(key,tickers)
    write_reports(report,args.output,key)
    print('Audit:',report['audit_status'],'Requests:',report['requests_sent'])
    print('Reports:',args.output/'finnhub_capability_report.json',args.output/'finnhub_capability_report.md')
    return 2 if not key else 0

if __name__=='__main__':raise SystemExit(main())
