"""Offline audit tests; no credentials or live requests required."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from datetime import date
from scripts.audit_finnhub_capabilities import (classify_response,error_status,load_api_key,probe,run_audit,write_reports,SPECS,TICKERS)

class FinnhubAuditTests(unittest.TestCase):
    def test_missing_key_never_requests(self):
        call=Mock()
        r=run_audit(None,probe_fn=call)
        call.assert_not_called()
        self.assertEqual(r['audit_status'],'BLOCKED_MISSING_KEY')
        self.assertEqual(r['endpoints'],{})
        self.assertEqual(r['requests_sent'],0)
    def test_entitlement(self):
        for msg in ["You don't have access to this resource",'Premium endpoint','Invalid API key']:
            self.assertEqual(error_status(message=msg),'NOT_ENTITLED')
        for code in [401,403]:self.assertEqual(error_status(code),'NOT_ENTITLED')
    def test_rate_limit(self):
        self.assertEqual(error_status(429),'RATE_LIMIT')
        self.assertEqual(error_status(message='API rate limit reached'),'RATE_LIMIT')
    def test_empty_and_invalid(self):
        for value in [{},[],None]:self.assertEqual(classify_response('quote',value)['status'],'NO_DATA')
        self.assertEqual(classify_response('company_news_1d',{'unexpected':'value'})['status'],'INVALID_RESPONSE')
        self.assertEqual(classify_response('basic_financials',{'metric':{}})['status'],'NO_DATA')
        self.assertEqual(classify_response('candles',{'s':'no_data'})['status'],'NO_DATA')
    def test_http_exception_and_timeout(self):
        for exception in [URLError('credential never logged'),TimeoutError('private')]:
            opener=Mock(side_effect=exception)
            r=probe('quote','AAPL','placeholder',date(2026,10,7),opener)
            self.assertEqual(r['status'],'NETWORK_ERROR')
            self.assertNotIn('private',str(r))
        e=HTTPError('url',403,'private',{},io.BytesIO(b"You don't have access"))
        r=probe('quote','AAPL','placeholder',date(2026,10,7),Mock(side_effect=e))
        self.assertEqual(r['status'],'NOT_ENTITLED')
        self.assertNotIn('private',str(r))
    def test_report_secret_redacted(self):
        r=run_audit(None)
        r['limitation']='deliberate-secret-placeholder'
        with tempfile.TemporaryDirectory() as directory:
            write_reports(r,directory,'deliberate-secret-placeholder')
            for path in Path(directory).iterdir():
                self.assertNotIn('deliberate-secret-placeholder',path.read_text(encoding='utf-8'))
    def test_stop_at_first_limit(self):
        call=Mock(side_effect=[{'status':'AVAILABLE','fields':['c']},{'status':'RATE_LIMIT','fields':[]}])
        sleep=Mock();r=run_audit('placeholder',sleep=sleep,probe_fn=call)
        self.assertEqual(r['requests_sent'],2)
        self.assertEqual(r['audit_status'],'PARTIAL_RATE_LIMIT')
        self.assertEqual(call.call_count,2)
        sleep.assert_called_once_with(1.2)
    def test_all_required_pairs_sequential(self):
        call=Mock(return_value={'status':'NO_DATA','fields':[]});sleep=Mock()
        r=run_audit('placeholder',probe_fn=call,sleep=sleep)
        self.assertEqual(call.call_count,len(SPECS)*len(TICKERS))
        self.assertEqual(sleep.call_count,call.call_count-1)
        self.assertEqual(r['audit_status'],'COMPLETED')
    def test_metric_keys_and_calendar_dates(self):
        r=classify_response('basic_financials',{'metric':{'beta':1.2,'extraField':None}})
        self.assertEqual(r['fields'],['beta','extraField'])
        self.assertEqual(r['non_null_fields'],['beta'])
        r=classify_response('earnings_calendar',{'earningsCalendar':[{'symbol':'AAPL','date':'2026-10-25','epsEstimate':1.2}]})
        self.assertEqual(r['events'][0]['date'],'2026-10-25')
    def test_toml_secret_loader_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'.streamlit';p.mkdir()
            (p/'secrets.toml').write_text('FINNHUB_API_KEY = "test-placeholder"',encoding='utf-8')
            with patch.dict('os.environ',{'FINNHUB_API_KEY':''}):
                self.assertEqual(load_api_key(directory),'test-placeholder')
    def test_transport_no_key_in_url(self):
        opener=Mock(return_value=io.BytesIO(b'{"c":100,"t":123}'))
        r=probe('quote','AAPL','test-placeholder',date(2026,10,7),opener)
        self.assertEqual(r['status'],'AVAILABLE')
        req=opener.call_args.args[0]
        self.assertNotIn('test-placeholder',req.full_url)
        self.assertEqual(req.get_header('X-finnhub-token'),'test-placeholder')
