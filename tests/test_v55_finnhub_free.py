"""V5.5 free data: contract, failure isolation, news pipeline and valuation isolation."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from finnhub_service import FinnhubProvider, external_sanity_warnings, TTL
from industry.news.finnhub_live import normalize_finnhub_news, classify_news, get_live_events, upcoming_events, deduplicate
from industry.news.service import range_bounds, get_company_events
from external_reference_ui import recommendation_summary, quote_reference, render_external_reference
from analysis_service import analyze_ticker
from test_v41_architecture import _ohlcv

NOW=datetime(2026,10,7,12,tzinfo=timezone.utc)
def raw(headline='Apple reports earnings results',ticker='AAPL',when=NOW,url='https://example.test/news/1'):
    return {'headline':headline,'related':ticker,'datetime':when.timestamp(),'url':url,'summary':'Revenue and earnings update.','source':'Publisher'}

def result(data,status='AVAILABLE'):
    return {'source':'Finnhub','fetched_at':NOW.isoformat(),'status':status,'data':data}

class FinnhubFreeIntegrationTests(unittest.TestCase):
    def provider(self,payload):
        fetch=Mock(return_value=payload)
        return FinnhubProvider(key_loader=lambda:'test-placeholder-key',fetch=fetch,sleep=lambda _:None),fetch
    def test_news_normalized(self):
        e=normalize_finnhub_news(raw(),'AAPL')
        self.assertEqual(e['source_url'],'https://example.test/news/1')
        self.assertEqual(e['event_type'],'earnings')
        self.assertEqual(e['importance'],'重大')
        self.assertEqual(e['event_importance_score'],90)
        self.assertIn('via Finnhub',e['source_name'])
        self.assertNotIn('Revenue and earnings update.',e['what_happened'])
        self.assertTrue(e['content_quality_ok'])
    def test_related_filter_and_alias(self):
        self.assertIsNone(normalize_finnhub_news(raw(ticker='MSFT'),'AAPL'))
        self.assertIsNone(normalize_finnhub_news(raw(ticker=''),'AAPL'))
        self.assertIsNotNone(normalize_finnhub_news(raw(ticker='GOOGL'),'GOOG'))
    def test_duplicates_headline_url_and_syndication(self):
        items=[raw(),raw(url='https://other.test/article'),raw(headline='Apple reports earnings results today',url='https://example.test/news/1?tracking=1')]
        self.assertEqual(len(deduplicate([normalize_finnhub_news(x,'AAPL') for x in items])),1)
    def test_classification_and_noise(self):
        expected=[('Company updates guidance','guidance'),('Export restrictions announced','regulation'),('Company signs major contract','partnership'),('CEO resigns','management'),('Company merger announced','M&A'),('New product launch','product')]
        for headline,kind in expected:self.assertEqual(classify_news(headline)[0],kind)
        self.assertIsNone(normalize_finnhub_news(raw('Apple shares rise ahead of earnings'),'AAPL'))
        self.assertIsNone(normalize_finnhub_news({**raw('Analyst reiterates price target'),'summary':''},'AAPL'))
    def test_bounds(self):
        for name,start in [('过去24小时','2026-10-06'),('本周','2026-10-05'),('本季度','2026-10-01')]:
            self.assertEqual(range_bounds(name,now=date(2026,10,7))['start_time'],start)
        bounds=range_bounds('过去24小时')
        a=datetime.fromisoformat(bounds['start_time']);b=datetime.fromisoformat(bounds['end_time'])
        self.assertEqual(b-a,timedelta(hours=24))
    def test_exact_window_future_and_limits(self):
        p=Mock();p.get_company_news.return_value=result([raw(when=NOW-timedelta(hours=25)),raw(when=NOW+timedelta(hours=1)),*[raw(headline,when=NOW-timedelta(hours=i),url=f'https://example.test/{i}') for i,headline in enumerate(['Apple announces new MacBook launch','New iPhone supply agreement signed','Company updates full-year guidance','Apple expands capital expenditure budget','CEO resigns from Apple'])]])
        rows=get_live_events(['AAPL'],(NOW-timedelta(hours=24)).isoformat(),NOW.isoformat(),now=NOW,range_key='24h',provider=p)
        self.assertEqual(len(rows),2)
        self.assertTrue(all(datetime.fromisoformat(e['event_time'])<=NOW for e in rows))
    def test_calendar_future_watchlist_no_data(self):
        p=Mock();p.get_earnings_calendar.return_value=result([
          {'symbol':'AAPL','date':'2026-10-10','hour':'amc','quarter':3,'year':2026,'epsEstimate':None},
          {'symbol':'MSFT','date':'2026-10-06'}, {'symbol':'OTHER','date':'2026-10-11'},
          {'symbol':'AAPL','date':'2026-12-20'}])
        rows,statuses=upcoming_events(['AAPL','MSFT','NVDA'],NOW.date(),provider=p)
        self.assertEqual(len(rows),1)
        self.assertEqual(statuses['NVDA'],'NO_DATA')
        self.assertEqual(rows[0]['calendar']['hour'],'amc')
        p.get_earnings_calendar.return_value=result([],'RATE_LIMIT')
        rows,statuses=upcoming_events(['AAPL'],NOW.date(),provider=p)
        self.assertEqual(rows,[]);self.assertEqual(statuses['AAPL'],'RATE_LIMIT')
    def test_recommendations(self):
        p,_=self.provider([{'period':'2026-10-01','strongBuy':10,'buy':5,'hold':3,'sell':1,'strongSell':0}, {'period':'2026-09-01','hold':2}])
        r=p.get_recommendation_trends('AAPL')
        self.assertEqual(r['data'][0]['Strong Buy'],10)
        self.assertIn('持有评级增加',recommendation_summary(r['data']))
        self.assertIn('整体偏积极',recommendation_summary(r['data']))
    def test_surprises(self):
        p,_=self.provider([{'period':'2026-06-30','actual':2,'estimate':1.5,'surprisePercent':33.33}])
        r=p.get_earnings_surprises('AAPL')
        self.assertEqual(r['data'][0]['Beat/Miss'],'Beat')
        self.assertEqual(r['data'][0]['EPS Actual'],2)
    def test_metrics_missing_forward_not_substituted(self):
        p,_=self.provider({'metric':{'peTTM':30,'peNormalizedAnnual':40,'roeTTM':20,'beta':1.2,'noise':999}})
        r=p.get_basic_financials('AAPL')
        self.assertEqual(r['data'],{'TTM PE':30.,'ROE TTM':20.,'Beta':1.2})
        self.assertNotIn('Forward PE',r['data'])
    def test_quote_sanity_and_fallback_readonly(self):
        internal={'price':100,'financials':{'forward_eps':5,'roe':.1}}
        before=deepcopy(internal)
        warnings=external_sanity_warnings(internal,result({'c':103}),result({'Forward PE':40,'ROE TTM':20}))
        self.assertEqual(len(warnings),2)
        self.assertEqual(internal,before)
        self.assertTrue(quote_reference(None,result({'c':103}))['fallback'])
        self.assertFalse(quote_reference(100,result({'c':103}))['fallback'])
    def test_missing_key_no_network_no_panel(self):
        fetch=Mock();p=FinnhubProvider(key_loader=lambda:None,fetch=fetch)
        self.assertEqual(p.get_quote('AAPL')['status'],'NOT_CONFIGURED')
        fetch.assert_not_called()
        st=Mock()
        with patch('external_reference_ui.get_finnhub_provider',return_value=p),patch('external_reference_ui.st',st):
            render_external_reference('AAPL',{})
        st.markdown.assert_not_called()
    def test_cache_ttl_and_retry(self):
        clock=[0];fetch=Mock(return_value={'c':100,'t':123})
        p=FinnhubProvider(key_loader=lambda:'placeholder',fetch=fetch,clock=lambda:clock[0],sleep=lambda _:None)
        p.get_quote('AAPL');p.get_quote('AAPL');self.assertEqual(fetch.call_count,1)
        clock[0]=TTL['quote']+1;p.get_quote('AAPL');self.assertEqual(fetch.call_count,2)
        fetch=Mock(side_effect=[URLError('private'),{'c':100,'t':123}])
        p=FinnhubProvider(key_loader=lambda:'placeholder',fetch=fetch,sleep=lambda _:None)
        self.assertEqual(p.get_quote('MSFT')['status'],'AVAILABLE')
        self.assertEqual(fetch.call_count,2)
    def test_rate_limit_no_retry_cached_survives(self):
        p,fetch=self.provider({'c':100,'t':123});p.get_quote('AAPL')
        fetch.side_effect=HTTPError('private',429,'private',{},None)
        self.assertEqual(p.get_quote('MSFT')['status'],'RATE_LIMIT')
        self.assertEqual(p.get_quote('NVDA')['status'],'RATE_LIMIT')
        self.assertEqual(p.get_quote('AAPL')['status'],'AVAILABLE')
        self.assertEqual(fetch.call_count,2)
    def test_no_paid_endpoints_or_valuation_changes(self):
        with patch('market_reference_provider.get_market_reference_provider') as paid:
            r=analyze_ticker('AAPL',history_loader=lambda t,d:_ohlcv(100),fundamentals_loader=lambda t:{'forward_eps':5,'shares':1e9,'fcf':1e9})
        paid.assert_not_called()
        self.assertEqual(r['market_reference']['source_status'],'NOT_ENTITLED')
        for path in ('stock/price-target','stock/eps-estimate','stock/revenue-estimate','stock/candle','indicator'):
            self.assertNotIn(path,TTL)
    def test_demo_hidden_and_live_used(self):
        p=Mock();p.get_company_news.return_value=result([raw()])
        with patch.dict(os.environ,{'NEWS_DEMO_MODE':'false'}),patch('industry.news.finnhub_live.get_finnhub_provider',return_value=p):
            events=get_company_events(['AAPL'],start_time='2026-10-01',end_time='2026-10-07',now=NOW.date())
        self.assertEqual(len(events),1)
        self.assertEqual(events[0]['source_type'],'finnhub')
    def test_integration_ui_hooks_and_deep_link_preserved(self):
        source=Path('streamlit_app.py').read_text(encoding='utf-8')
        self.assertIn('render_external_reference(current, r)',source)
        self.assertNotIn('        render_market_reference(r)',source)
        self.assertIn('open_headlines_cb=open_headlines',source)
        self.assertIn('headline_ticker_filter',source)
        self.assertIn('Finnhub 暂无该公司未来财报日期',source)
        self.assertIn('if col not in {"市场一致目标", "内部 vs 市场"}',source)
    def test_bad_schema_does_not_crash(self):
        p,_=self.provider({'unexpected':42})
        self.assertEqual(p.get_basic_financials('AAPL')['status'],'INVALID_RESPONSE')
        self.assertEqual(p.get_quote('AAPL')['status'],'INVALID_RESPONSE')
    def test_news_cache_before_filter_and_secrets_redacted(self):
        payload=[raw()];payload[0]['source']='test-placeholder-key'
        p,fetch=self.provider(payload)
        a=p.get_company_news('AAPL','2026-10-01','2026-10-07')
        p.get_company_news('AAPL','2026-10-01','2026-10-07')
        self.assertEqual(fetch.call_count,1)
        self.assertNotIn('test-placeholder-key',str(a))
        self.assertNotIn('test-placeholder-key',str(p._cache))

    def test_partial_news_failure_preserves_other_ticker(self):
        p=Mock();p.get_company_news.side_effect=[RuntimeError('private'),result([raw(ticker='MSFT')])]
        rows=get_live_events(['AAPL','MSFT'],'2026-10-01','2026-10-07',now=NOW.date(),provider=p)
        self.assertEqual([e['ticker'] for e in rows],['MSFT'])
    def test_all_metadata_and_calendar_without_estimates(self):
        p,_=self.provider({'earningsCalendar':[{'symbol':'AAPL','date':'2026-10-10'}]})
        r=p.get_earnings_calendar('2026-10-07','2026-11-06')
        self.assertEqual(r['source'],'Finnhub')
        self.assertEqual(r['status'],'AVAILABLE')
        self.assertTrue(r['fetched_at'])
        self.assertIsNone(r['data'][0]['epsEstimate'])
    def test_profile_numeric_fields_normalized(self):
        p,_=self.provider({'name':'Apple','marketCapitalization':'100.25','shareOutstanding':'20'})
        r=p.get_company_profile('AAPL')
        self.assertEqual(r['data']['marketCapitalization'],100.25)
        self.assertEqual(r['data']['shareOutstanding'],20.)
