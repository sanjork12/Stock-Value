"""Offline administrator-only EPS-loss simulation and read-only cache retrieval."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
import unittest
import json
from unittest.mock import Mock, patch

import analysis_service
import financial_forensics_admin as admin
from financial_forensics import capture_financial_diagnostic
from last_reliable_valuation import reliable_snapshot, apply_last_reliable, DISPLAY_FIELDS
from tests.test_last_reliable_valuation import analyze
from tests.test_peer_diagnostic_isolation import FINANCIALS
from scripts.verify_peer_isolation import history, internal_snapshot


class AdminFallbackSwitchTests(unittest.TestCase):
    def setUp(self):
        admin._LAST_RUN.clear()
        self.good=analyze('NVDA')
        self.row={'raw':{'last_reliable':reliable_snapshot(self.good)}}
        self.raw=deepcopy(FINANCIALS['NVDA'])
        self.raw.update(quote_currency='USD',financial_currency='USD',split_context_known=True,
                        last_split_date=960000000,last_split_factor='2:1')
        self.client=Mock()
        self.client.auth.get_user.return_value=SimpleNamespace(user=SimpleNamespace(id='owner',email='admin@example.test'))
        self.provider=Mock()
        self.provider.get_diagnostic_basic_financials.return_value={'status':'NO_DATA','fields':{}}

    def capture(self,ticker,**kwargs):
        return capture_financial_diagnostic(ticker,history_loader=history,
            fundamentals_loader=lambda _:self.raw,finnhub_provider=self.provider,**kwargs)

    def run_admin(self,simulate=True):
        admin._LAST_RUN.clear()
        with patch.object(admin,'is_cloud_runtime',return_value=True), \
             patch.object(admin,'capture_financial_diagnostic',side_effect=self.capture), \
             patch('analysis_service.fetch_historical_snapshot',return_value=self.row) as load:
            report=admin.run_cloud_financial_diagnostic(self.client,'owner',
                {'ADMIN_EMAIL':'admin@example.test'},'NVDA',simulate_missing_input=simulate)
        self.load=load
        return report

    def test_sets_eps_none_at_valuate_without_mutating_provider(self):
        before=deepcopy(self.raw)
        with patch('analysis_service.valuate',wraps=analysis_service.valuate) as valuate:
            report=self.run_admin()
        inputs=valuate.call_args.args[1]
        self.assertIsNone(inputs['forward_eps'])
        self.assertIsNone(inputs['trailing_eps'])
        self.assertTrue(inputs['simulated_missing_input'])
        self.assertEqual(self.raw,before)
        self.assertTrue(report['simulated_missing_input'])
        self.assertIsNone(report['fields']['eps.forward_eps']['value'])
        self.assertIsNone(report['fields']['eps.trailing_eps']['value'])

    def test_cloud_readback_exact_values_and_no_write_or_timestamp_refresh(self):
        before=deepcopy(self.row)
        report=self.run_admin()
        valuation=report['valuation']
        self.assertEqual(valuation['source_status'],'cached_last_reliable')
        self.assertEqual(valuation['stale_reason'],'current_financial_input_incomplete')
        for key in ('fair_value','blended_low','blended_mid','blended_high','zones','exit_zone'):
            self.assertEqual(valuation[key],json.loads(json.dumps(self.good[key])),key)
        self.assertEqual(valuation['calculated_at'],before['raw']['last_reliable']['calculated_at'])
        self.assertEqual(self.row,before)
        self.client.table.assert_not_called()
        self.load.assert_called_once()
        self.assertEqual(self.load.call_args.args[:3],(self.client,'owner','NVDA'))
        # The engine guard and its trace remain intact; only test display restores.
        self.assertFalse(report['valuation_failure_trace']['available'])
        self.assertEqual(report['valuation_failure_trace']['internal_reason'],'forward_and_trailing_eps_unavailable')

    def test_disabled_switch_returns_normal_live_without_loading_cache(self):
        report=self.run_admin(False)
        self.assertFalse(report.get('simulated_missing_input',False))
        self.assertEqual(report['valuation']['source_status'],'live')
        self.assertEqual(report['valuation']['fair_value'],self.good['fair_value'])
        self.load.assert_not_called()
        self.client.table.assert_not_called()

    def test_no_expired_or_mismatched_snapshot_never_restored(self):
        original=deepcopy(self.row)
        cases=[None, {}]
        expired=deepcopy(original)
        expired['raw']['last_reliable']['calculated_at']=(datetime.now(timezone.utc)-timedelta(hours=25)).isoformat()
        cases.append(expired)
        for key,value in (('quote_currency','EUR'),('last_split_factor','10:1'),
                          ('canonical_shares_source','impliedSharesOutstanding'),('canonical_shares',1)):
            row=deepcopy(original)
            row['raw']['last_reliable']['context'][key]=value
            cases.append(row)
        for row in cases:
            with self.subTest(row=row):
                self.row=row
                report=self.run_admin()
                self.assertEqual(report['valuation']['source_status'],'live')
                self.assertIsNone(report['valuation']['fair_value'])

    def test_flag_alone_cannot_bypass_production_guard_or_save_snapshot(self):
        results=[]
        self.capture('NVDA',simulate_missing_input=True,result_sink=lambda r:results.append(r) or {})
        result=results[0]
        self.assertIsNone(apply_last_reliable(result,self.row)['fair_value'])
        self.assertIsNone(reliable_snapshot(result))
        result['fair_value']=100
        self.assertIsNone(reliable_snapshot(result))

    def test_non_admin_and_non_cloud_cannot_simulate_or_read(self):
        for cloud,email in ((False,'admin@example.test'),(True,'other@example.test')):
            self.client.auth.get_user.return_value.user.email=email
            with patch.object(admin,'is_cloud_runtime',return_value=cloud), \
                 patch.object(admin,'capture_financial_diagnostic') as capture:
                with self.assertRaises(PermissionError):
                    admin.run_cloud_financial_diagnostic(self.client,'owner',{'ADMIN_EMAIL':'admin@example.test'},
                                                        'NVDA',simulate_missing_input=True)
                capture.assert_not_called()
            st=Mock();st.secrets={'ADMIN_EMAIL':'admin@example.test'};st.session_state={}
            with patch.object(admin,'is_cloud_runtime',return_value=cloud):
                admin.render_financial_diagnostics(st,self.client,'owner')
            st.checkbox.assert_not_called()
        self.client.table.assert_not_called()


if __name__=='__main__':unittest.main()
