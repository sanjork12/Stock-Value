import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from market_reference_provider import FinnhubMarketReferenceProvider, configured_api_key, format_consensus_target
from analysis_service import analyze_ticker
from test_v41_architecture import _ohlcv

class ProviderTests(unittest.TestCase):
    def provider(self, payload=None, **kwargs):
        fetch=Mock(return_value=payload)
        p=FinnhubMarketReferenceProvider(key_loader=lambda:'test-only-placeholder',fetch=fetch,interval=0,**kwargs)
        return p,fetch
    def test_missing_key(self):
        p=FinnhubMarketReferenceProvider(key_loader=lambda:None,fetch=Mock())
        self.assertEqual(p.get_price_target('AAPL')['source_status'],'NOT_CONFIGURED')
        p._fetch.assert_not_called()
        self.assertEqual(format_consensus_target({'source_status':'NOT_CONFIGURED'}),'未配置市场参考')
    def test_response(self):
        p,f=self.provider({'symbol':'AAPL','targetMean':328,'targetLow':250,'targetHigh':400,'lastUpdated':'2026-10-06'})
        r=p.get_price_target('aapl')
        self.assertEqual(r['target_mean'],328)
        self.assertEqual(r['target_low'],250)
        self.assertEqual(r['target_high'],400)
        self.assertEqual(r['last_updated'],'2026-10-06')
        self.assertIsNone(r['analyst_count'])
        self.assertEqual(r['source'],'Finnhub')
        self.assertEqual(format_consensus_target({'analyst_consensus_target':328}),'$328')
    def test_cache_and_expiry(self):
        now=[0]
        p,f=self.provider({'targetMean':100},clock=lambda:now[0],ttl=100)
        first=p.get_price_target('AAPL');first['target_mean']=999
        self.assertEqual(p.get_price_target('aapl')['target_mean'],100)
        self.assertEqual(f.call_count,1)
        now[0]=101;p.get_price_target('AAPL')
        self.assertEqual(f.call_count,2)
        self.assertNotIn('test-only-placeholder',repr(p._cache))
    def test_rate_limit_preserves_cached_and_cools_down(self):
        p,f=self.provider({'targetMean':100})
        p.get_price_target('AAPL')
        f.side_effect=HTTPError('safe',429,'rate',{},None)
        self.assertEqual(p.get_price_target('GOOG')['source_status'],'RATE_LIMIT')
        self.assertEqual(p.get_price_target('MSFT')['source_status'],'RATE_LIMIT')
        self.assertEqual(p.get_price_target('AAPL')['target_mean'],100)
        self.assertEqual(f.call_count,2)
    def test_errors_safe(self):
        for code,status in [(400,'INVALID_SYMBOL'),(404,'INVALID_SYMBOL'),(401,'AUTH_ERROR'),(403,'ACCESS_DENIED'),(500,'NETWORK_ERROR')]:
            p,f=self.provider();f.side_effect=HTTPError('secret',code,'secret',{},None)
            r=p.get_price_target('AAPL')
            self.assertEqual(r['source_status'],status)
            self.assertNotIn('secret',str(r))
        p,f=self.provider();f.side_effect=URLError('secret')
        self.assertEqual(p.get_price_target('AAPL')['source_status'],'NETWORK_ERROR')
    def test_invalid_empty_and_count(self):
        p,f=self.provider({})
        self.assertEqual(p.get_price_target('AAPL')['source_status'],'NO_DATA')
        self.assertEqual(p.get_price_target('invalid symbol')['source_status'],'INVALID_SYMBOL')
        p,f=self.provider({'targetMean':100,'numberAnalysts':12})
        self.assertEqual(p.get_price_target('X')['analyst_count'],12)
    def test_controlled_calls(self):
        sleeps=[]
        p=FinnhubMarketReferenceProvider(key_loader=lambda:'placeholder',fetch=lambda t,k:{'targetMean':100},clock=lambda:100,sleep=sleeps.append)
        p.get_price_target('AAPL');p.get_price_target('MSFT')
        self.assertAlmostEqual(sleeps[0],1.1)
    def test_environment_precedence(self):
        with patch.dict('os.environ',{'FINNHUB_API_KEY':'  placeholder  '}):
            self.assertEqual(configured_api_key(),'placeholder')
    def test_integration_internal_unchanged_and_specialized(self):
        p,f=self.provider({'targetMean':328})
        empty,_=self.provider({})
        args=dict(history_loader=lambda t,d:_ohlcv(213),fundamentals_loader=lambda t:{'forward_eps':5,'shares':1e9,'fcf':1e9})
        a=analyze_ticker('AAPL',market_reference_provider=p,**args)
        b=analyze_ticker('AAPL',market_reference_provider=empty,**args)
        for key in ['fair','zones','exit_zone','reliability_score']:
            self.assertEqual(a[key],b[key])
        ref=a['market_reference']
        self.assertAlmostEqual(ref['internal_vs_consensus_pct'],(a['fair']/328-1)*100)
        specialized=analyze_ticker('BMNR',market_reference_provider=p,**args)
        self.assertIsNone(specialized['fair'])
        self.assertEqual(specialized['market_reference']['analyst_consensus_target'],328)
        self.assertIsNone(specialized['market_reference']['internal_vs_consensus_pct'])
    def test_historical_does_not_fetch_current_targets(self):
        p,f=self.provider({'targetMean':328})
        r=analyze_ticker('AAPL',as_of='2020-01-01',history_loader=lambda t,d:_ohlcv(100),market_reference_provider=p)
        f.assert_not_called()
        self.assertEqual(r['market_reference']['source_status'],'HISTORICAL_UNAVAILABLE')
    def test_secret_example_only_placeholder(self):
        from pathlib import Path
        text=Path('.streamlit/secrets.toml.example').read_text(encoding='utf-8')
        self.assertIn('FINNHUB_API_KEY = "YOUR_FINNHUB_API_KEY"',text)
        self.assertIn('.streamlit/secrets.toml',Path('.gitignore').read_text())

    def test_transport_endpoint_header_and_timeout(self):
        import io
        from market_reference_provider import _fetch
        response=io.BytesIO(b'{"targetMean":328}')
        with patch('market_reference_provider.urlopen',return_value=response) as opener:
            self.assertEqual(_fetch('AAPL','test-placeholder')['targetMean'],328)
            req=opener.call_args.args[0]
            self.assertEqual(req.full_url,'https://finnhub.io/api/v1/stock/price-target?symbol=AAPL')
            self.assertNotIn('test-placeholder',req.full_url)
            self.assertEqual(req.get_header('X-finnhub-token'),'test-placeholder')
            self.assertEqual(opener.call_args.kwargs['timeout'],10)
