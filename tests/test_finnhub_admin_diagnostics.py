import json
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

import finnhub_admin_diagnostics as diag


def client(email='admin@example.test',uid='u1'):
    c=Mock();c.auth.get_user.return_value=SimpleNamespace(user=SimpleNamespace(email=email,id=uid))
    return c

class AdminAuditTests(unittest.TestCase):
    def setUp(self):
        self.previous=diag._LAST_RUN;diag._LAST_RUN=None
    def tearDown(self):
        diag._LAST_RUN=self.previous
    def test_verified_email_and_id(self):
        self.assertTrue(diag.verified_admin(client(),'u1','ADMIN@example.test'))
        self.assertFalse(diag.verified_admin(client('other@example.test'),'u1','admin@example.test'))
        self.assertFalse(diag.verified_admin(client(),'other','admin@example.test'))
        self.assertFalse(diag.verified_admin(client(),'u1',''))
        c=client();c.auth.get_user.side_effect=RuntimeError('private')
        self.assertFalse(diag.verified_admin(c,'u1','admin@example.test'))
    def test_local_run_blocked_before_requests(self):
        with patch.object(diag,'is_cloud_runtime',return_value=False),patch.object(diag,'run_audit') as run:
            with self.assertRaises(PermissionError):diag.run_cloud_audit(client(),'u1',{'ADMIN_EMAIL':'admin@example.test','FINNHUB_API_KEY':'placeholder'})
            run.assert_not_called()
    def test_non_admin_cloud_blocked(self):
        with patch.object(diag,'is_cloud_runtime',return_value=True),patch.object(diag,'run_audit') as run:
            with self.assertRaises(PermissionError):diag.run_cloud_audit(client('other@example.test'),'u1',{'ADMIN_EMAIL':'admin@example.test','FINNHUB_API_KEY':'placeholder'})
            run.assert_not_called()
    def test_secret_only_no_environment_fallback(self):
        with patch.object(diag,'is_cloud_runtime',return_value=True),patch.object(diag,'run_audit') as run:
            with self.assertRaises(ValueError):diag.run_cloud_audit(client(),'u1',{'ADMIN_EMAIL':'admin@example.test'})
            run.assert_not_called()
    def test_success_redacts_and_cooldown(self):
        report={'tickers':['AAPL'],'endpoints':{'quote':{'AAPL':{'status':'AVAILABLE','fields':['sensitive-placeholder']}}}}
        secrets={'ADMIN_EMAIL':'admin@example.test','FINNHUB_API_KEY':'sensitive-placeholder'}
        with patch.object(diag,'is_cloud_runtime',return_value=True),patch.object(diag,'run_audit',return_value=report) as run:
            safe=diag.run_cloud_audit(client(),'u1',secrets)
            self.assertNotIn('sensitive-placeholder',json.dumps(safe))
            exported=diag.download_payloads(safe)
            for item in exported:self.assertNotIn(b'sensitive-placeholder',item)
            self.assertEqual(run.call_args.kwargs['tickers'],['AAPL','MSFT','NVDA','AMZN','GOOG','JPM','TSLA'])
            with self.assertRaises(RuntimeError):diag.run_cloud_audit(client(),'u1',secrets)
            self.assertEqual(run.call_count,1)
    def test_rows_only_allowed_statuses(self):
        report={'tickers':['AAPL','MSFT'],'endpoints':{'quote':{'AAPL':{'status':'AVAILABLE','fields':['c']},'MSFT':{'status':'RATE_LIMIT','fields':[]}},'price_target':{}}}
        rows=diag.capability_rows(report)
        self.assertEqual([r['Status'] for r in rows],['AVAILABLE','RATE_LIMIT'])
        self.assertTrue(all(r['Coverage']=='1/2' for r in rows))
        self.assertEqual(set(rows[0]),{'Capability','Endpoint','Status','Coverage','Notes'})
    def test_unauthorized_render_clears_result_no_download(self):
        st=Mock();st.secrets={'ADMIN_EMAIL':'admin@example.test'};st.session_state={'_finnhub_audit_result':{'owner':'another'}}
        with patch.object(diag,'is_cloud_runtime',return_value=True):diag.render_diagnostics(st,client('other@example.test'),'u1')
        self.assertNotIn('_finnhub_audit_result',st.session_state)
        st.download_button.assert_not_called()
    def test_owner_isolation(self):
        st=Mock();st.secrets={'ADMIN_EMAIL':'admin@example.test'};st.session_state={'_finnhub_audit_result':{'owner':'another','report':{}}}
        st.button.return_value=False
        with patch.object(diag,'is_cloud_runtime',return_value=True):diag.render_diagnostics(st,client(),'u1')
        st.download_button.assert_not_called()
    def test_render_exports_without_rerunning_audit(self):
        st=Mock();st.secrets={'ADMIN_EMAIL':'admin@example.test'};st.button.return_value=False
        st.session_state={'_finnhub_audit_result':{'owner':'u1','report':{'tested_at':'2026-10-07','requests_sent':1,'tickers':['AAPL'],'endpoints':{'quote':{'AAPL':{'status':'AVAILABLE','fields':['c']}}}}}}
        with patch.object(diag,'is_cloud_runtime',return_value=True),patch.object(diag,'run_audit') as run:
            diag.render_diagnostics(st,client(),'u1')
            run.assert_not_called()
        self.assertEqual(st.download_button.call_count,2)
    def test_actual_execution_button_uses_core(self):
        st=Mock();st.secrets={'ADMIN_EMAIL':'admin@example.test','FINNHUB_API_KEY':'placeholder'};st.session_state={}
        st.button.side_effect=[False,True]
        report={'tested_at':'2026-10-07','requests_sent':0,'tickers':['AAPL'],'endpoints':{}}
        with patch.object(diag,'is_cloud_runtime',return_value=True),patch.object(diag,'run_audit',return_value=report) as run:
            diag.render_diagnostics(st,client(),'u1')
            run.assert_called_once()
        self.assertEqual(st.session_state['_finnhub_audit_result']['owner'],'u1')
    def test_cloud_gate_false_here(self):
        self.assertFalse(diag.is_cloud_runtime())
