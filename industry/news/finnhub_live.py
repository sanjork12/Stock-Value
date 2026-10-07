"""Finnhub news -> bounded, deduplicated Chinese rule summaries and calendar events."""
from datetime import date, datetime, time, timedelta, timezone
from difflib import SequenceMatcher
import hashlib
from industry.news.grounded_summary import canonical, mentions, ticker_roles, summarize
import re
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo
from finnhub_service import get_finnhub_provider
from industry.news.schema import normalize_event, PER_TICKER_LIMITS

RULES=[
 ('earnings',90,'Revenue',r'\bearnings\b|quarterly results|reports.*results|财报', '财报可能影响盈利预期，需对照实际结果与此前预期。'),
 ('guidance',90,'Revenue',r'\bguidance\b|outlook|forecast|业绩指引','指引可能改变未来收入或利润预期，需核对适用期间与关键假设。'),
 ('regulation',95,'Regulation',r'export.*restrict|export.*ban|antitrust|regulat|sanction|监管','监管事项可能影响市场准入或经营成本，需核实适用范围与实施时间。'),
 ('M&A',90,'Valuation',r'acqui[rs]|merger|takeover|并购','并购事项可能改变业务结构和资本配置，需核对是否已签约及交易条件。'),
 ('management',85,'Valuation',r'\b(?:ceo|cfo)\b.*(?:resign|appoint|step down|retire)|management change|管理层变动','管理层变化可能影响战略执行，需关注正式任命与后续经营安排。'),
 ('capex',85,'CapEx',r'capex|capital expenditure|data cent(?:er|re).*invest|资本开支','资本开支可能影响现金流与产能，需核对投入规模、节奏和回报。'),
 ('legal',85,'Regulation',r'lawsuit|litigation|court|诉讼','法律事项可能带来成本或经营约束，需核实进展与实际责任。'),
 ('partnership',85,'Revenue',r'major contract|major deal|multi.year.*(?:deal|contract)|重大合同','合同事项可能影响收入可见度，需核实合同金额、履约时间及是否具约束力。'),
 ('partnership',65,'Revenue',r'partner|agreement|contract|合作|协议','合作可能影响渠道、供应或收入机会，需核对商业条款与兑现进度。'),
 ('product',85,'Product',r'major.*roadmap|major.*platform|重大.*路线图','产品路线图需要通过交付和客户采用转化为收入。'),
 ('product',65,'Product',r'launch|roadmap|unveil|new chip|ai infrastructure|产品发布','产品进展可能影响竞争力与收入结构，需关注交付时间和客户采用。'),
 ('competition',65,'Competition',r'market share|segment growth|竞争|市场份额','竞争或分部变化可能影响收入与利润率，需核对数据口径和持续性。'),
]
AREA_ZH={'Revenue':'收入','Margin':'利润率','CapEx':'资本开支','Product':'产品','Competition':'竞争','Regulation':'监管','Valuation':'估值'}
NOISE=re.compile(r'price target|analyst reiterat|stocks? (?:price )?(?:rise|rose|fall|fell|jump|drop|surge|sink|move|up |down )|shares? (?:rise|rose|fall|fell|jump|drop|surge|sink|up |down )|social.media|reddit|meme stock',re.I)


def classify_news(headline,summary=''):
    text=f'{headline} {summary}'.lower()
    for kind,score,area,pattern,why in RULES:
        if re.search(pattern,text,re.I):
            # A mere analyst earnings preview is not a reported earnings event.
            if re.search(r'analyst|price target|preview|what to expect',headline,re.I):score=min(score,40)
            return kind,score,area,why
    return 'other',30,'Valuation','这是一则业务相关消息，是否影响投资判断仍需核对公司披露与后续进展。'


def normalize_finnhub_news(raw,ticker):
    ticker=str(ticker).upper()
    aliases={ticker}|({'GOOG','GOOGL'} if ticker in ('GOOG','GOOGL') else set())
    related=set(re.findall(r'[A-Z0-9.\-]+',str(raw.get('related') or '').upper()))
    if not related.intersection(aliases):return None
    headline=str(raw.get('headline') or '').strip()
    url=str(raw.get('url') or '').strip()
    parsed_url=urlsplit(url)
    if not headline or parsed_url.scheme not in ('http','https') or not parsed_url.netloc or parsed_url.username:return None
    try:published=datetime.fromtimestamp(float(raw['datetime']),timezone.utc)
    except (TypeError,ValueError,KeyError,OverflowError,OSError):return None
    kind,score,area,why=classify_news(headline,str(raw.get('summary') or ''))
    if NOISE.search(headline) and (score<65 or re.search(r'before|ahead of|preview|rumou?r|speculat',headline,re.I)):
        return None
    summary = str(raw.get('summary') or '').strip()
    primary, secondary = ticker_roles(headline, summary, raw.get('related'))
    if canonical(ticker) not in primary:
        return None
    relevance = min(100, 35 + (25 if canonical(ticker) in ticker_roles(headline, '', '')[0] else 0)
                    + (10 if canonical(ticker) in mentions(summary) else 0)
                    + (5 if len(summary) >= 60 else 0)
                    + (15 if score >= 65 else 0) + (10 if score >= 85 else 0))
    if relevance < 60 or score < 60:
        return None
    detail = summarize(headline, summary, primary, kind, AREA_ZH[area])
    importance='重大' if score>=85 else '重要' if score>=60 else '一般'
    event=normalize_event({'ticker':ticker,'headline':detail['headline'],'published_at':published.isoformat(),
       'event_time':published.isoformat(),'event_type':kind,'importance':importance,
       'what_happened':detail['conclusion'], 'why_it_matters':detail['why_it_matters'],
       'impact_summary':detail['impact_summary'], 'impact_areas':list(detail['impact_summary']),
       'watch_next':detail['watch_next'],
       'source_name':f"{raw.get('source') or '新闻来源'} via Finnhub",'source_url':url,'source_type':'finnhub'},now=published.date())
    identity = str(raw.get('id') or urlunsplit((*urlsplit(url)[:3], '', '')))
    event.update(detail)
    event.update({'published_at':published.isoformat(),'event_time':published.isoformat(),
                  'event_id':hashlib.sha256(identity.encode()).hexdigest()[:20],
                  'primary_tickers':primary,'secondary_tickers':secondary,
                  'involved_tickers':sorted(set(primary+secondary)),
                  'finnhub_id':raw.get('id'),'original_headline':headline,
                  'original_summary':summary,'related':raw.get('related'),
                  'relevance_score':relevance,'event_importance_score':score,'impact_area':area,'source':'Finnhub',
                  'short_summary':detail['conclusion'],'what_happened':detail['conclusion'],
                  'summary_method':'grounded_extraction','status':'AVAILABLE'})
    return event


def _instant(value,end=False):
    if isinstance(value,datetime):dt=value
    elif isinstance(value,date):dt=datetime.combine(value,time.max if end else time.min)
    else:
        text=str(value)
        dt=datetime.fromisoformat(text.replace('Z','+00:00'))
        if len(text)==10 and end:dt=datetime.combine(dt.date(),time.max)
    return dt.replace(tzinfo=ZoneInfo('Europe/London')) if dt.tzinfo is None else dt


def deduplicate(events):
    """Global, transitive union by canonical URL, provider id, or original title."""
    groups=[]
    for ev in sorted((e for e in events if e),key=lambda x:x['event_time'],reverse=True):
        parsed=urlsplit(ev['source_url'])
        # Preserve identity query parameters, drop tracking only.
        from urllib.parse import parse_qsl, urlencode
        query=urlencode(sorted((k,v) for k,v in parse_qsl(parsed.query) if not k.lower().startswith(('utm_', 'fbclid', 'gclid', 'tracking'))))
        url=urlunsplit((parsed.scheme.lower(),parsed.netloc.lower(),parsed.path.rstrip('/'),query,''))
        headline=re.sub(r'\W+',' ',ev.get('original_headline',ev['headline']).lower()).strip()
        keys={('url',url),('headline',headline)}
        if ev.get('finnhub_id') is not None:keys.add(('id',str(ev['finnhub_id'])))
        matches=[g for g in groups if g[0]&keys]
        if not matches:
            groups.append((keys,dict(ev)));continue
        primary=set(ev.get('primary_tickers',[ev['ticker']]))
        secondary=set(ev.get('secondary_tickers',[]))
        # Prefer the richer supplied summary when overlapping feeds differ.
        target=dict(max([ev]+[g[1] for g in matches], key=lambda e: (len(e.get('fact_evidence') or []),len(e.get('original_summary') or ''))))
        for group in matches:
            keys |= group[0]
            primary.update(group[1].get('primary_tickers',[group[1]['ticker']]))
            secondary.update(group[1].get('secondary_tickers',[]))
            groups.remove(group)
        target.update(primary_tickers=sorted(primary),secondary_tickers=sorted(secondary-primary),involved_tickers=sorted(primary|secondary))
        groups.append((keys,target))
    return [event for _,event in groups]


def get_live_events(tickers,start_time=None,end_time=None,include_upcoming=False,*,now=None,range_key=None,apply_limits=True,provider=None):
    provider=provider or get_finnhub_provider()
    current=_instant(now,end=isinstance(now,date) and not isinstance(now,datetime)) if now else datetime.now(ZoneInfo('Europe/London'))
    if include_upcoming:
        return upcoming_events(tickers,current.date(),provider=provider)[0]
    end=min(_instant(end_time,True),current) if end_time else current
    start=_instant(start_time) if start_time else current-timedelta(days=90)
    start=max(start,current-timedelta(days=100))
    if end<start:return []
    events=[]
    for ticker in tickers:
        try:r=provider.get_company_news(ticker,start.date().isoformat(),end.date().isoformat())
        except Exception:continue
        for raw in r.get('data') or []:
            ev=normalize_finnhub_news(raw,ticker)
            if ev and start<=_instant(ev['event_time'])<=end:
                ev['fetched_at']=r['fetched_at'];events.append(ev)
    events=deduplicate(events)
    events.sort(key=lambda x:x['event_time'],reverse=True)
    events.sort(key=lambda x:x['event_importance_score'],reverse=True)
    counts={};output=[];limit=PER_TICKER_LIMITS.get(range_key or 'quarter',5)
    for ev in events:
        subjects=ev.get('primary_tickers') or [ev['ticker']]
        if not apply_limits or all(counts.get(t,0)<limit for t in subjects):
            output.append(ev)
            for t in subjects:counts[t]=counts.get(t,0)+1
    return output


def upcoming_events(tickers,today,*,provider=None):
    provider=provider or get_finnhub_provider();end=today+timedelta(days=30)
    result=provider.get_earnings_calendar(today.isoformat(),end.isoformat())
    statuses={ticker:result['status'] if result['status'] not in ('AVAILABLE','NO_DATA') else 'NO_DATA' for ticker in tickers}
    events=[]
    for row in result.get('data') or []:
        ticker=str(row.get('symbol') or '').upper()
        try:day=date.fromisoformat(str(row.get('date')))
        except ValueError:continue
        if ticker not in statuses or not today<day<=end:continue
        statuses[ticker]='AVAILABLE'
        hour={'bmo':'盘前','amc':'盘后','dmh':'盘中'}.get(row.get('hour'),'时间未提供')
        fiscal=f"FY{row.get('year') or '—'} Q{row.get('quarter') or '—'}"
        event=normalize_event({'ticker':ticker,'event_date':day.isoformat(),'headline':f'{ticker} 下一次财报 · {hour}',
           'event_status':'UPCOMING','event_type':'earnings','importance':'重大',
           'what_happened':f'Finnhub 财报日历列示日期为 {day.isoformat()}，{hour}，{fiscal}。',
           'why_it_matters':'财报可能更新盈利预期；日历日期可能调整，需以公司公告确认。',
           'impact_summary':{'收入':'关注已公布业绩与预期差异。'},'watch_next':['核对公司确认的公布时间','关注收入、EPS 与后续指引'],
           'source_name':'Finnhub Earnings Calendar','source_type':'finnhub','source_url':'https://finnhub.io/'},now=today)
        event.update({'source':'Finnhub','fetched_at':result['fetched_at'],'status':'AVAILABLE','calendar':row,'impact_area':'Revenue'})
        events.append(event)
    return sorted(events,key=lambda ev:ev['event_date']),statuses
