from copy import deepcopy
from datetime import datetime,timezone,timedelta
import unittest
from unittest.mock import Mock,patch

from calibration_snapshot_guard import calibration_eligibility,batch_eligibility,reference_snapshot
from valuation_calibration_audit import audit_analysis,TICKERS
import production_snapshot_admin as admin


def healthy(ticker='GOOG'):
    return {'ticker':ticker,'production_analysis_fair':100,'source_status':'live','capture_status':'COMPLETE',
        'input_blend_alignment':'SAME_LIVE_EXECUTION','peer_in_blend':False,
        'normalized_inputs':{'forward_eps':5,'quote_currency':'USD','financial_currency':'USD',
            'canonical_shares':1000,'canonical_shares_source':'impliedSharesOutstanding',
            'split_context_known':True,'last_split_date':0,'last_split_factor':'0:1'},
        'live_blend':{'fair':100,'included':['forward_pe','growth_adjusted_pe'],
            'models':{'forward_pe':{'inputs':{'eps_used':5}},'growth_adjusted_pe':{'inputs':{'eps_used':5}}}}}


def proxy(ticker='GOOG'):
    stock=healthy(ticker)
    stock['normalized_inputs'].update(forward_eps=None,quote_currency=None,eps_proxy=4,
        eps_proxy_source='statement_derived',currency_mismatch=False)
    for model in stock['live_blend']['models'].values():
        model['inputs'].update(eps_proxy=True,eps_source='statement_derived')
    return stock


def reliable_row(ticker='GOOG',now=None):
    now=now or datetime.now(timezone.utc)
    return {'raw':{'last_reliable':{'ticker':ticker,'calculated_at':now.isoformat(),'source_status':'live',
        'inputs':{'forward_eps':5},'context':healthy(ticker)['normalized_inputs'],
        'valuation':{'fair_value':100,'confidence':'MEDIUM','blend':{
            'models':{'forward_pe':{'inputs':{'forward_eps':5,'eps_source':'forwardEps'}}}}}}}}


class CalibrationGuardTests(unittest.TestCase):
    def test_proxy_only_and_currency_reasons_preserved(self):
        result=calibration_eligibility(proxy())
        self.assertEqual(result['calibration_eligibility'],'INELIGIBLE_PROXY_ONLY_VALUATION')
        self.assertIn('quote_currency_unknown',result['calibration_eligibility_reasons'])

    def test_unavailable_priority_even_with_transient_reference(self):
        stock=proxy('NVDA');stock['production_analysis_fair']=None
        stock['live_blend'].update(fair=None,included=[])
        reference=reference_snapshot(reliable_row('NVDA'),'NVDA')
        result=calibration_eligibility(stock,reference)
        self.assertEqual(result['calibration_eligibility'],'INELIGIBLE_UNAVAILABLE_VALUATION')
        self.assertTrue(result['transient_input_degradation'])

    def test_unknown_currency_not_hidden_by_mismatch_false(self):
        stock=healthy();stock['normalized_inputs'].update(quote_currency=None,currency_mismatch=False)
        self.assertEqual(calibration_eligibility(stock)['calibration_eligibility'],'INELIGIBLE_CURRENCY_CONTEXT_UNKNOWN')

    def test_healthy_live_is_eligible(self):
        self.assertEqual(calibration_eligibility(healthy())['calibration_eligibility'],'ELIGIBLE')

    def test_reference_is_read_only_and_never_replaces_live(self):
        stock=proxy();row=reliable_row();before_stock,before_row=deepcopy(stock),deepcopy(row)
        reference=reference_snapshot(row,'GOOG')
        result=calibration_eligibility(stock,reference)
        self.assertEqual(result['calibration_eligibility'],'INELIGIBLE_TRANSIENT_INPUT_DEGRADATION')
        self.assertTrue(result['transient_input_degradation'])
        self.assertFalse(result['reference_snapshot_used_for_calibration'])
        self.assertEqual(stock,before_stock);self.assertEqual(row,before_row)
        self.assertEqual(reference['forward_eps_source'],'forwardEps')

    def test_expired_or_unknown_context_reference_cannot_prove_transience(self):
        now=datetime.now(timezone.utc)
        for row in (reliable_row(now=now-timedelta(hours=24)),reliable_row()):
            if row['raw']['last_reliable']['calculated_at']!= (now-timedelta(hours=24)).isoformat():
                row['raw']['last_reliable']['context']['split_context_known']=False
            reference=reference_snapshot(row,'GOOG',now)
            self.assertFalse(reference['healthy_reference'])
            self.assertFalse(calibration_eligibility(proxy(),reference)['transient_input_degradation'])
        self.assertIsNone(reference_snapshot(reliable_row('MSFT'),'GOOG'))

    def test_cached_display_never_eligible(self):
        stock=healthy();stock.update(source_status='cached_last_reliable',input_blend_alignment='CACHED_DISPLAY_WITH_CURRENT_LIVE_INPUTS_DO_NOT_CALIBRATE')
        result=calibration_eligibility(stock)
        self.assertNotEqual(result['calibration_eligibility'],'ELIGIBLE')
        self.assertFalse(result['transient_input_degradation'])

    def test_batch_all_required_must_be_eligible(self):
        stocks=[dict(healthy(t),**calibration_eligibility(healthy(t))) for t in TICKERS]
        self.assertEqual(batch_eligibility(stocks,TICKERS)['batch_calibration_eligibility'],'ELIGIBLE')
        stocks[0].update(calibration_eligibility(proxy()))
        result=batch_eligibility(stocks,TICKERS)
        self.assertEqual(result['batch_calibration_eligibility'],'INELIGIBLE')
        self.assertEqual(result['ineligible_tickers'],['GOOG'])
        self.assertEqual(batch_eligibility(stocks[:-1],TICKERS)['batch_calibration_eligibility'],'INELIGIBLE')

    def test_reported_cloud_batch_expected_statuses(self):
        stocks=[]
        for ticker in TICKERS:
            stock=proxy(ticker)
            if ticker=='NVDA':stock.update(production_analysis_fair=None);stock['live_blend'].update(fair=None,included=[])
            stock.update(calibration_eligibility(stock));stocks.append(stock)
        self.assertEqual([s['calibration_eligibility'] for s in stocks],[
            'INELIGIBLE_PROXY_ONLY_VALUATION','INELIGIBLE_PROXY_ONLY_VALUATION','INELIGIBLE_PROXY_ONLY_VALUATION',
            'INELIGIBLE_UNAVAILABLE_VALUATION','INELIGIBLE_PROXY_ONLY_VALUATION'])
        self.assertEqual(batch_eligibility(stocks,TICKERS)['batch_calibration_eligibility'],'INELIGIBLE')

    def test_audit_refuses_degraded_live_before_sensitivity(self):
        stock=proxy();stock['financials']=stock['normalized_inputs']
        with patch('valuation_calibration_audit.replay',side_effect=AssertionError('No calibration')):
            result=audit_analysis('GOOG',stock)
        self.assertEqual(result['status'],'CALIBRATION_INPUT_INELIGIBLE')
        self.assertIsNone(result['sensitivity'])

    def test_batch_reference_reads_do_not_write_or_replace_inputs(self):
        from types import SimpleNamespace
        client=Mock();client.auth.get_user.return_value=SimpleNamespace(user=SimpleNamespace(id='u',email='admin@test.com'))
        client.table.side_effect=AssertionError('No writes')
        originals={ticker:proxy(ticker) for ticker in TICKERS}
        rows={ticker:reliable_row(ticker) for ticker in TICKERS}
        before_stocks,before_rows=deepcopy(originals),deepcopy(rows)
        admin._LAST_RUN.clear()
        with patch.object(admin,'is_cloud_runtime',return_value=True),patch.object(admin,'capture_analysis',side_effect=lambda ticker,**k:deepcopy(originals[ticker])):
            report=admin.run_batch(client,'u',{'ADMIN_EMAIL':'admin@test.com'},
                history_loader=Mock(),fundamentals_loader=Mock(),reference_loader=lambda ticker:rows[ticker])
        self.assertEqual(report['batch_calibration_eligibility'],'INELIGIBLE')
        self.assertTrue(all(s['transient_input_degradation'] for s in report['stocks']))
        self.assertTrue(all(s['normalized_inputs']['forward_eps'] is None for s in report['stocks']))
        self.assertTrue(all(s['reference_snapshot_used_for_calibration'] is False for s in report['stocks']))
        self.assertEqual(originals,before_stocks);self.assertEqual(rows,before_rows)
        client.table.assert_not_called()


if __name__=='__main__':unittest.main()
