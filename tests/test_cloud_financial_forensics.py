"""Admin forensics: privacy, actual-path evidence and valuation invariants."""
from copy import deepcopy
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

import pandas as pd
from analysis_service import analyze_ticker
import financial_forensics_admin as admin
from financial_forensics import (build_input_snapshot,capture_financial_diagnostic,compare_financial_snapshots,
                                 finalize_snapshot,snapshot_json,snapshot_rows,TICKERS)
from financial_forensics_observer import observe_financial_inputs,public_observations,observe_info
from finnhub_service import FinnhubProvider
from mag7_monitor import get_live_fundamentals
from scripts.verify_peer_isolation import history,internal_snapshot
from test_peer_diagnostic_isolation import FINANCIALS


def client(email='admin@example.test',uid='u1'):
    c=Mock();c.auth.get_user.return_value=SimpleNamespace(user=SimpleNamespace(email=email,id=uid))
    return c


class YahooFixture:
    def __init__(self,partial=False):
        self.partial=partial
        self.info_calls=0
        self.fast_info={'shares':1e9,'market_cap':1e11,'last_price':100}
        columns=pd.to_datetime(['2025-12-31','2024-12-31','2023-12-31'])
        self.cashflow=pd.DataFrame([[8e9,7e9,6e9],[-2e9,-2e9,-2e9],[6e9,5e9,4e9]],
            index=['Operating Cash Flow','Capital Expenditure','Free Cash Flow'],columns=columns)
        self.income_stmt=pd.DataFrame([[4,3,2],[4e9,3e9,2e9],[1e9,1e9,1e9]],
            index=['Diluted EPS','Net Income','Diluted Average Shares'],columns=columns)
        self.balance_sheet=pd.DataFrame([[3e9],[2e9],[20e9]],
            index=['Cash And Cash Equivalents','Total Debt','Stockholders Equity'],columns=columns[:1])

    def get_info(self):
        info={'currentPrice':100,'marketCap':1e11,'sharesOutstanding':1e9,'impliedSharesOutstanding':1.1e9,
              'revenueGrowth':.2,'totalRevenue':20e9,'ebitda':5e9}
        if not self.partial:info.update(forwardEps=5,trailingEps=4,currency='USD',financialCurrency='USD')
        return info

    @property
    def info(self):
        self.info_calls+=1
        return {'forwardEps':5,'trailingEps':4,'currency':'USD','financialCurrency':'USD'}

    def get_earnings_estimate(self):return pd.DataFrame()


class ForensicsTests(unittest.TestCase):
    def setUp(self):
        self.old_last=admin._LAST_RUN.copy();admin._LAST_RUN.clear()

    def tearDown(self):admin._LAST_RUN.clear();admin._LAST_RUN.update(self.old_last)

    def capture(self,ticker='NVDA',fixture=None):
        provider=Mock()
        provider.get_diagnostic_basic_financials.return_value={'status':'AVAILABLE','fields':{'epsTTM':4,'forwardPE':20}}
        if fixture is None:
            return capture_financial_diagnostic(ticker,history_loader=history,
                fundamentals_loader=lambda _:deepcopy(FINANCIALS[ticker]),finnhub_provider=provider)
        with patch('mag7_monitor._yfinance',return_value=SimpleNamespace(Ticker=lambda _:fixture)):
            return capture_financial_diagnostic(ticker,history_loader=history,finnhub_provider=provider)

    def test_pre_valuation_capture_has_required_sections(self):
        snapshot=self.capture()
        self.assertEqual(snapshot['capture_phase'],'BEFORE_VALUATE')
        for key in ('ticker','run_timestamp','environment','market','eps','shares','cash_flow','balance_sheet','growth','currency','profile','model_applicability'):
            self.assertIn(key,snapshot)
        for entry in snapshot['fields'].values():
            self.assertTrue({'value','source','raw_source_name','status'}<=set(entry))

    def test_sink_runs_before_valuate_and_is_not_returned_to_users(self):
        import analysis_service
        events=[];original=analysis_service.valuate
        def sink(snapshot):
            events.append('snapshot')
            self.assertTrue(all(not row['executed'] for row in snapshot['model_applicability']))
        def engine(*a,**kw):
            self.assertEqual(events,['snapshot'])
            events.append('valuation');return original(*a,**kw)
        with patch('analysis_service.valuate',side_effect=engine):
            result=analyze_ticker('NVDA',history_loader=history,
                fundamentals_loader=lambda _:deepcopy(FINANCIALS['NVDA']),peer_mode='diagnostic',financial_diagnostic_sink=sink)
        self.assertEqual(events,['snapshot','valuation'])
        self.assertNotIn('financial_diagnostic',result)
        self.assertNotIn('raw_yahoo_observations',result)

    def test_sink_failure_and_mutation_cannot_change_valuation(self):
        args=dict(history_loader=history,fundamentals_loader=lambda _:deepcopy(FINANCIALS['NVDA']),peer_mode='diagnostic')
        baseline=analyze_ticker('NVDA',**args)
        def sink(snapshot):
            snapshot.clear();raise RuntimeError('injected observation failure')
        observed=analyze_ticker('NVDA',**args,financial_diagnostic_sink=sink)
        self.assertEqual(internal_snapshot(baseline),internal_snapshot(observed))
        self.assertEqual(baseline['financials'],observed['financials'])

    def test_real_loader_observer_does_not_change_payload(self):
        with patch('mag7_monitor._yfinance',return_value=SimpleNamespace(Ticker=lambda _:YahooFixture())):
            baseline=get_live_fundamentals('NVDA')
            with observe_financial_inputs():observed=get_live_fundamentals('NVDA')
        self.assertEqual(baseline,observed)

    def test_actual_yahoo_path_and_statement_periods_captured(self):
        s=self.capture(fixture=YahooFixture())
        self.assertEqual(s['fields']['eps.forward_eps']['raw_source_name'],'ticker.get_info.forwardEps')
        raw=s['raw_yahoo_observations']
        self.assertEqual(raw['statements']['income_stmt'][0]['periods'][0],'2025-12-31')
        self.assertIn('Diluted EPS',raw['statements']['income_stmt'][0]['rows_present'])
        self.assertEqual(s['shares']['implied_shares_outstanding'],1.1e9)

    def test_partial_get_info_preserves_existing_path_and_guard(self):
        fixture=YahooFixture(partial=True)
        s=self.capture(fixture=fixture)
        self.assertEqual(fixture.info_calls,0)
        self.assertTrue(s['hypotheses']['A_yahoo_forward_trailing']['forwardEps_missing'])
        self.assertTrue(s['hypotheses']['A_yahoo_forward_trailing']['trailingEps_missing'])
        self.assertEqual(s['eps']['trailing_eps_source'],'statement_derived')
        self.assertEqual(s['valuation_failure_trace']['internal_reason'],'forward_and_trailing_eps_unavailable')
        self.assertEqual(s['hypotheses']['G_proxy_guard'],'CORRECT_UNAVAILABLE_FOR_CAPTURED_INPUTS')
        self.assertEqual(s['currency']['currency_knowledge'],'UNKNOWN')

    def test_finnhub_available_never_fills_missing_yahoo_eps(self):
        s=self.capture(fixture=YahooFixture(partial=True))
        self.assertIsNone(s['eps']['forward_eps'])
        self.assertFalse(s['finnhub_diagnostic']['used_for_valuation'])
        self.assertTrue(s['hypotheses']['B_yahoo_missing_finnhub_available']['yahoo_trailing_missing_and_finnhub_epsTTM_available'])
        self.assertFalse(s['valuation_failure_trace']['available'])

    def test_missing_cash_debt_zero_fallback_identified(self):
        fixture=YahooFixture();fixture.balance_sheet=pd.DataFrame()
        s=self.capture(fixture=fixture)
        self.assertEqual(s['balance_sheet']['cash'],0)
        self.assertEqual(s['fields']['balance_sheet.cash']['raw_source_name'],'fallback_missing_assumed_zero')
        self.assertIsNone(s['fields']['balance_sheet.cash']['raw_value'])

    def test_comparison_critical_material_same_and_sources(self):
        a=self.capture();b=deepcopy(a)
        b['fields']['eps.forward_eps']['value']=None
        b['fields']['cash_flow.fcf_observation_count']['value']=1
        rows={row['field']:row for row in compare_financial_snapshots(a,b)}
        self.assertEqual(rows['eps.forward_eps']['severity'],'CRITICAL')
        self.assertEqual(rows['cash_flow.fcf_observation_count']['severity'],'MATERIAL')
        self.assertEqual(rows['market.price']['severity'],'SAME')
        self.assertIn('local_source',rows['eps.forward_eps'])
        with self.assertRaises(ValueError):compare_financial_snapshots(a,{**b,'ticker':'MSFT'})

    def test_failure_trace_retains_actual_model_reasons_counts(self):
        s=self.capture(fixture=YahooFixture(partial=True))
        trace=s['valuation_failure_trace']
        self.assertEqual(trace['UNAVAILABLE because'],'forward_and_trailing_eps_unavailable')
        self.assertIn('diagnostic only',trace['peer'])
        self.assertTrue(any(row['reason']=='forward_and_trailing_eps_unavailable' for row in trace['models']))

    def test_observer_does_not_capture_credentials_or_arbitrary_strings(self):
        secret='private-placeholder-material'
        with observe_financial_inputs():
            observe_info('ticker.get_info',{'access_token':secret,'cookie':secret,'refresh_token':secret,
                'currency':secret,'financialCurrency':secret,'forwardEps':secret})
            data=public_observations()
        self.assertNotIn(secret,json.dumps(data))
        self.assertEqual(public_observations(),{})

    def test_finnhub_diagnostic_only_free_endpoint_numeric_projection(self):
        fetch=Mock(return_value={'metric':{'epsTTM':4,'forwardPE':20,'access_token':'private'}})
        p=FinnhubProvider(key_loader=lambda:'fixture-only',fetch=fetch,sleep=lambda _:None)
        result=p.get_diagnostic_basic_financials('NVDA')
        self.assertEqual(fetch.call_args.args[0],'stock/metric')
        self.assertEqual(result['fields']['epsTTM'],4)
        self.assertNotIn('private',json.dumps(result))

    def test_local_and_non_admin_cloud_block_before_capture(self):
        with patch.object(admin,'is_cloud_runtime',return_value=False),patch.object(admin,'capture_financial_diagnostic') as capture:
            with self.assertRaises(PermissionError):admin.run_cloud_financial_diagnostic(client(),'u1',{'ADMIN_EMAIL':'admin@example.test'},'NVDA')
            capture.assert_not_called()
        with patch.object(admin,'is_cloud_runtime',return_value=True),patch.object(admin,'capture_financial_diagnostic') as capture:
            with self.assertRaises(PermissionError):admin.run_cloud_financial_diagnostic(client('other@example.test'),'u1',{'ADMIN_EMAIL':'admin@example.test'},'NVDA')
            capture.assert_not_called()

    def test_admin_success_redacts_nested_secret_values(self):
        s=self.capture();s['diagnostic_note']='private-placeholder-material'
        with patch.object(admin,'is_cloud_runtime',return_value=True),patch.object(admin,'capture_financial_diagnostic',return_value=s):
            safe=admin.run_cloud_financial_diagnostic(client(),'u1',{'ADMIN_EMAIL':'admin@example.test','nested':{'cookie_secret':'private-placeholder-material'}},'NVDA')
        self.assertNotIn('private-placeholder-material',json.dumps(safe))

    def test_unauthorized_render_clears_session_no_download(self):
        st=Mock();st.secrets={'ADMIN_EMAIL':'admin@example.test'}
        st.session_state={'_financial_diagnostic_result':{'owner':'u1'},'_financial_diagnostic_open':True}
        with patch.object(admin,'is_cloud_runtime',return_value=True):admin.render_financial_diagnostics(st,client('other@example.test'),'u1')
        self.assertNotIn('_financial_diagnostic_result',st.session_state)
        st.download_button.assert_not_called()

    def test_session_owner_switch_cannot_download_previous_snapshot(self):
        st=Mock();st.secrets={'ADMIN_EMAIL':'admin@example.test'};st.button.return_value=False
        st.selectbox.return_value='NVDA';st.session_state={'_financial_diagnostic_result':{'owner':'another','reports':{'NVDA':self.capture()}}}
        with patch.object(admin,'is_cloud_runtime',return_value=True):admin.render_financial_diagnostics(st,client(),'u1')
        st.download_button.assert_not_called()

    def test_allowed_tickers_and_field_table_contract(self):
        self.assertEqual(set(TICKERS),{'AVGO','NVDA','MU','PLTR','COIN','CRCL','AMZN','MSFT'})
        self.assertEqual(set(snapshot_rows(self.capture())[0]),{'Field','Value','Source','Status'})
        with self.assertRaises(ValueError):capture_financial_diagnostic('AAPL')

    def test_uploaded_local_snapshot_ignores_credentials(self):
        s=self.capture();local=deepcopy(s);local['access_token']='private-placeholder-material'
        local['fields']['eps.forward_eps']['value']='private-placeholder-material'
        raw=json.dumps(local).encode('utf-8')
        upload=SimpleNamespace(size=len(raw),getvalue=lambda:raw)
        projected=admin._local_for_comparison(upload,s)
        self.assertNotIn('private-placeholder-material',json.dumps(projected))

    def test_earnings_estimate_selected_period_is_captured(self):
        fixture=YahooFixture(partial=True)
        fixture.get_earnings_estimate=lambda:pd.DataFrame({'avg':[5.5]},index=['0y'])
        s=self.capture(fixture=fixture)
        self.assertEqual(s['eps']['forward_eps'],5.5)
        self.assertEqual(s['eps']['forward_eps_source'],'earnings_estimate')
        self.assertEqual(s['raw_yahoo_observations']['estimates'][0]['period'],'0y')

    def test_structural_redaction_handles_escaped_and_numeric_secrets(self):
        secret='private"placeholder'
        payload=snapshot_json({'note':secret,'number':12345},[secret,'12345'])
        safe=json.loads(payload)
        self.assertEqual(safe['note'],'[REDACTED]')
        self.assertIsNone(safe['number'])


if __name__=='__main__':unittest.main()
