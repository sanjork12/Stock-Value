from copy import deepcopy
from contextlib import ExitStack
from datetime import datetime,timezone
import json
import unittest
from unittest.mock import Mock,patch
import pandas as pd

import input_resilience_audit as audit
import input_resilience_admin as admin
from finnhub_service import FinnhubProvider


class Yahoo:
    def __init__(self,ticker):
        self.info={'currentPrice':100,'marketCap':1000,'trailingEps':2}
        self.fast_info={'currency':'USD','shares':10,'last_price':100,'market_cap':1000}
        col=pd.Timestamp('2025-12-31')
        self.income_stmt=self.financials=pd.DataFrame({col:{'EBITDA':200,'Total Revenue':500,'Diluted Average Shares':10}})
        self.balance_sheet=pd.DataFrame({col:{'Total Debt':30,'Cash And Cash Equivalents':20}})
        self.cashflow=pd.DataFrame({col:{'Operating Cash Flow':100,'Capital Expenditure':-20}})
        self.splits=pd.Series([10.],index=pd.DatetimeIndex(['2024-06-10']))
    def get_info(self):return dict(self.info)
    def get_history_metadata(self):return {'currency':'USD'}
    def history(self,**kwargs):return pd.DataFrame({'Stock Splits':self.splits})


def provider(fetch=None):
    def response(path,params,key):
        if path=='stock/profile2':return {'name':'Public company','currency':'USD','marketCapitalization':.001,'shareOutstanding':.00001,'exchange':'NASDAQ','finnhubIndustry':'Technology'}
        if path=='stock/metric':return {'metric':{'forwardPE':20,'epsTTM':2,'peTTM':50,'beta':1,'52WeekHigh':120,'52WeekLow':60}}
        if path=='quote':return {'c':100,'t':int(datetime.now(timezone.utc).timestamp())}
        raise AssertionError('Forbidden endpoint')
    return FinnhubProvider(key_loader=lambda:'fake-secret',fetch=fetch or response,sleep=lambda _:None)


class ResilienceAuditTests(unittest.TestCase):
    def setUp(self):
        admin._LAST_RUN.clear()
        self.paths,self.counts=audit.collect_yahoo('NVDA',Yahoo)
        f,_,_=audit.collect_finnhub('NVDA',provider());self.paths.update(f)

    def candidates(self):return {c['field']:c for c in audit.candidates(self.paths)}

    def test_missing_yahoo_currency_direct_candidate(self):
        c=self.candidates()['quote_currency']
        self.assertEqual(c['source_type'],'DIRECT');self.assertEqual(c['value'],'USD')
        self.assertEqual(c['fallback_safety'],'SAFE_WITH_VALIDATION')

    def test_quote_does_not_fill_financial_currency(self):
        c=self.candidates()['financial_currency']
        self.assertIsNone(c['value']);self.assertEqual(c['fallback_safety'],'UNSAFE')

    def test_derived_eps_is_not_direct(self):
        c=self.candidates()['forward_eps']
        self.assertEqual(c['derived_forward_eps'],5)
        self.assertEqual(c['source_type'],'DERIVED');self.assertEqual(c['fallback_safety'],'DIAGNOSTIC_ONLY')
        self.assertEqual(c['timestamp_alignment'],'UNVERIFIED_METRIC_EFFECTIVE_TIME')

    def test_reference_comparison_not_calculation(self):
        c={x['field']:x for x in audit.candidates(self.paths,{'healthy_reference':True,'forward_eps':50})}['forward_eps']
        self.assertEqual(c['value'],5);self.assertEqual(c['percent_difference_vs_healthy_reference'],-90)
        self.assertFalse(c['healthy_reference_used_for_calculation'])

    def test_derived_cannot_unlock_real_eligibility(self):
        stock={'calibration_eligibility':'INELIGIBLE_PROXY_ONLY_VALUATION',
            'calibration_eligibility_reasons':['proxy_only_eps_regime_forward_eps_missing','financial_currency_unknown']}
        original=deepcopy(stock)
        sims=audit.recovery_simulations(stock,audit.candidates(self.paths))
        self.assertEqual(stock,original)
        for s in sims:self.assertTrue(s['real_calibration_eligibility_unchanged'])
        self.assertIn('financial_currency_unknown',sims[-1]['simulated_missing_reasons_remaining'])

    def test_split_alternative(self):
        c=self.candidates()
        self.assertEqual(c['last_split_factor']['candidate_source'],'yahoo.splits')
        self.assertEqual(c['last_split_factor']['value'],10)
        self.assertEqual(c['last_split_factor']['fallback_safety'],'SAFE_DIRECT')

    def test_categorical_disagreement(self):
        self.paths['yahoo.get_info']['values']['quote_currency']='EUR'
        rows=audit.disagreements(self.paths)
        self.assertTrue(any(r['field']=='quote_currency' and r['status']=='MATERIAL_DIFFERENCE' for r in rows))

    def test_numeric_bands(self):
        for a,b,status in ((100,98,'CONSISTENT'),(100,96,'MINOR_DIFFERENCE'),(100,90,'MATERIAL_DIFFERENCE')):
            self.assertEqual(audit.numeric_disagreement(a,b)['status'],status)

    def test_degraded_cache_amplification(self):
        self.assertEqual(audit.cache_amplification({'state':'DEGRADED','cache':{'cache_hit':True,'cache_ttl':900}}),'DEGRADED_CACHE_AMPLIFICATION')
        self.assertEqual(audit.cache_amplification({'state':'DEGRADED','cache':{'cache_hit':None}}),'UNKNOWN')

    def test_missing_yahoo_does_not_crash(self):
        paths,calls=audit.collect_yahoo('NVDA',Mock(side_effect=RuntimeError('do not export secret')))
        self.assertEqual(paths['yahoo.info']['state'],'UNAVAILABLE')
        self.assertNotIn('do not export secret',json.dumps(paths))

    def test_finnhub_missing_key_does_not_crash(self):
        paths,_,_=audit.collect_finnhub('NVDA',FinnhubProvider(key_loader=lambda:None))
        self.assertEqual(paths['finnhub.metric']['status'],'NOT_CONFIGURED')

    def test_finnhub_rate_limit_stops_remaining_endpoints(self):
        fetch=Mock(return_value={'error':'API limit reached'})
        paths,_,blocked=audit.collect_finnhub('NVDA',provider(fetch))
        self.assertTrue(blocked);self.assertEqual(fetch.call_count,1)
        self.assertEqual(paths['finnhub.metric']['status'],'SKIPPED_RATE_LIMIT')

    def test_finnhub_cache_age_and_units(self):
        p=provider();audit.collect_finnhub('NVDA',p)
        paths,_,_=audit.collect_finnhub('NVDA',p)
        self.assertTrue(paths['finnhub.profile']['cache']['cache_hit'])
        self.assertEqual(paths['finnhub.profile']['values']['shares_outstanding'],10)
        self.assertEqual(paths['finnhub.profile']['values']['market_cap'],1000)

    def test_statement_survives_info_failure(self):
        row=audit.summarize_stock('NVDA',self.paths,self.counts)
        cash=next(r for r in row['statement_resilience'] if r['field']=='cash')
        self.assertIsNone(cash['quote_summary_value']);self.assertEqual(cash['statement_value'],20)
        self.assertTrue(cash['source_survives_info_degradation'])

    def test_matrix_and_invocations(self):
        row=audit.summarize_stock('NVDA',self.paths,self.counts)
        f=next(r for r in row['field_matrix'] if r['field']=='financial_currency')
        self.assertEqual(f['yahoo.info']['status'],'MISSING')
        self.assertEqual(f['finnhub.profile']['status'],'NOT_APPLICABLE')
        self.assertTrue(all(n==1 for n in self.counts.values()))

    def test_five_stock_coherent_batch_no_production_mutation(self):
        prior={'stocks':[{'ticker':'NVDA','normalized_inputs':{'cash':20},'fair_value':358,
            'calibration_eligibility':'INELIGIBLE_UNAVAILABLE_VALUATION','calibration_eligibility_reasons':['current_live_valuation_unavailable']} ]}
        before=deepcopy(prior)
        with patch('analysis_service.analyze_ticker',side_effect=AssertionError('No production run')):
            result=audit.run_audit(yahoo_factory=Yahoo,provider=provider(),production_report=prior)
        self.assertEqual(prior,before);self.assertEqual(len(result['stocks']),5)
        self.assertTrue(all(s['provider_batch_id']==result['batch_id'] for s in result['stocks']))
        self.assertFalse(result['production_fallback_implemented'])

    def test_admin_only(self):
        with patch.object(admin,'is_cloud_runtime',return_value=True),patch.object(admin,'verified_admin',return_value=False):
            with self.assertRaises(PermissionError):admin.run_cloud_audit(Mock(),'u',{})

    def test_cloud_only(self):
        with patch.object(admin,'is_cloud_runtime',return_value=False):
            with self.assertRaises(PermissionError):admin.run_cloud_audit(Mock(),'u',{})

    def test_no_database_writes_and_redacted_export(self):
        client=Mock();client.table.side_effect=AssertionError('No database calls')
        with patch.object(admin,'is_cloud_runtime',return_value=True),patch.object(admin,'verified_admin',return_value=True):
            r=admin.run_cloud_audit(client,'u',{'ADMIN_EMAIL':'admin@example.com','FINNHUB_API_KEY':'fake-secret'},
                yahoo_factory=Yahoo,provider=provider())
        client.table.assert_not_called();self.assertNotIn('fake-secret',json.dumps(r))
        self.assertEqual(len(admin.summary_rows(r)),5)

    def test_no_secret_exception_messages(self):
        p=provider(Mock(side_effect=RuntimeError('secret in URL')))
        paths,_,_=audit.collect_finnhub('NVDA',p)
        self.assertNotIn('secret in URL',json.dumps(paths))

    def test_no_inferred_or_derived_candidate_implemented(self):
        for c in audit.candidates(self.paths):
            self.assertFalse(c['implemented'])
            if c['source_type']=='INFERRED':self.assertEqual(c['recommended_action'],'REJECT')

    def test_incomplete_paths_no_eligibility_claim(self):
        sims=audit.recovery_simulations({},audit.candidates(self.paths))
        self.assertTrue(all(s['eligibility_recovery_potential']=='UNKNOWN_NO_CURRENT_BATCH' for s in sims))

    def test_no_production_governance_or_fallback_invocation(self):
        import analysis_service,valuation_engine,calibration_snapshot_guard,capital_structure_overlay
        import enterprise_aware_experiment,last_reliable_valuation,peer_comparable
        with ExitStack() as stack:
            for module,name in ((analysis_service,'analyze_ticker'),(valuation_engine,'valuate'),
                (calibration_snapshot_guard,'calibration_eligibility'),(capital_structure_overlay,'capital_overlay'),
                (enterprise_aware_experiment,'enterprise_experiment'),(last_reliable_valuation,'apply_last_reliable')):
                stack.enter_context(patch.object(module,name,side_effect=AssertionError('Production must remain isolated')))
            result=audit.run_audit(yahoo_factory=Yahoo,provider=provider())
        self.assertEqual(len(result['stocks']),5)

    def test_lazy_field_error_keeps_other_fields(self):
        class Lazy(dict):
            def get(self,key):
                if key=='shares':raise RuntimeError('never export message')
                return super().get(key)
        ticker=Yahoo('NVDA');ticker.fast_info=Lazy(currency='USD',last_price=100)
        paths,_=audit.collect_yahoo('NVDA',lambda _:ticker)
        self.assertEqual(paths['yahoo.fast_info']['values']['quote_currency'],'USD')
        self.assertEqual(paths['yahoo.fast_info']['field_errors']['shares_outstanding'],'RuntimeError')

    def test_reported_forward_eps_remains_diagnostic(self):
        self.paths['finnhub.metric']['values']['reported_forward_eps']=7
        candidates=audit.candidates(self.paths)
        direct=next(c for c in candidates if c['field']=='reported_forward_eps')
        self.assertEqual(direct['source_type'],'DIRECT')
        self.assertEqual(direct['fallback_safety'],'DIAGNOSTIC_ONLY')
        self.assertFalse(direct['implemented'])
