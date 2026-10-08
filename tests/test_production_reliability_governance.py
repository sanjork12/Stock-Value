from copy import deepcopy
from datetime import timedelta
import unittest
from unittest.mock import patch,Mock
from production_reliability_governance import evaluate_structural_governance as evaluate, govern_blend, cap_confidence
from scripts.experiment_family_weighting import report_inputs
from tests.test_last_reliable_valuation import analyze,NOW
from last_reliable_valuation import reliable_snapshot,apply_last_reliable
from valuation_engine import reliability_from_snapshot,reconstruct_blend_from_snapshot
from analysis_service import build_snapshot_record


def evidence(severity):
    return {'NONE':{'structural_valuation_readiness':'ROBUST','active_family_count':2},
        'LOW':{'structural_valuation_readiness':'CONCENTRATED','active_family_count':1},
        'MODERATE':{'structural_valuation_readiness':'ACCEPTABLE_WITH_CONFLICT','active_family_count':2,'cross_family_status':'CROSS_FAMILY_DISAGREEMENT'},
        'HIGH':{'structural_valuation_readiness':'CROSS_FAMILY_CONFLICT_SUPPRESSED','suppression_materiality':'MODERATE','suppressed_families':['CASH_FLOW_INTRINSIC']},
        'CRITICAL':{'structural_valuation_readiness':'CROSS_FAMILY_CONFLICT_SUPPRESSED','suppression_materiality':'HIGH','suppressed_families':['CASH_FLOW_INTRINSIC']}}[severity]


class ProductionGovernanceTests(unittest.TestCase):
    def test_severity_penalty_matrix(self):
        for severity,penalty in (('NONE',0),('LOW',-5),('MODERATE',-10),('HIGH',-15),('CRITICAL',-20)):
            with self.subTest(severity=severity):
                g=evaluate(evidence(severity));self.assertEqual(g['severity'],severity)
                self.assertEqual(g['total_structural_penalty'],penalty)

    def test_secondary_max_one_cap(self):
        g=evaluate({**evidence('CRITICAL'),'active_family_count':1,'growth_overlap_risk':'HIGH','structural_gaps':['x']})
        self.assertEqual(g['total_structural_penalty'],-25)
        self.assertLessEqual(len([p for p in g['penalties'] if p['role']=='secondary']),1)

    def test_high_growth_secondary(self):
        g=evaluate({'active_family_count':1,'growth_overlap_risk':'HIGH','structural_gaps':['FORECAST_GROWTH_WITHOUT_INDEPENDENT_CASH_FLOW_CONFIRMATION']})
        self.assertEqual(g['severity'],'MODERATE')
        self.assertEqual(g['secondary_penalty'],-5)
        self.assertEqual(g['penalties'][1]['code'],'high_growth_overlap')

    def test_high_growth_not_secondary_if_diversified(self):
        g=evaluate({**evidence('MODERATE'),'growth_overlap_risk':'HIGH'})
        self.assertEqual(g['secondary_penalty'],0)

    def test_gap_not_double_charged(self):
        g=evaluate({'active_family_count':1,'structural_gaps':['x']})
        self.assertEqual(g['total_structural_penalty'],-10)
        self.assertTrue(g['penalty_overlap_guard']['overlap_detected'])

    def test_dispersion_overlap_guard(self):
        g=evaluate(evidence('MODERATE'),[{'code':'dispersion_very_high','delta':-35}])
        self.assertTrue(g['penalty_overlap_guard']['overlap_detected'])
        self.assertEqual(g['secondary_penalty'],0)

    def test_confidence_downgrade_only(self):
        self.assertEqual(cap_confidence('HIGH','MEDIUM'),'MEDIUM')
        self.assertEqual(cap_confidence('LOW','MEDIUM'),'LOW')
        self.assertEqual(cap_confidence('UNAVAILABLE','LOW'),'UNAVAILABLE')
        self.assertEqual(cap_confidence('HIGH','NONE'),'HIGH')

    def test_critical_and_high_exit_block(self):
        for severity in ('HIGH','CRITICAL'):self.assertTrue(evaluate(evidence(severity))['precise_exit_block'])

    def test_low_none_no_structural_block(self):
        for severity in ('NONE','LOW'):self.assertFalse(evaluate(evidence(severity))['precise_exit_block'])

    def test_moderate_conflict_block(self):
        self.assertTrue(evaluate(evidence('MODERATE'))['precise_exit_block'])

    def test_single_gap_moderate(self):
        self.assertEqual(evaluate({'active_family_count':1,'structural_gaps':['x']})['severity'],'MODERATE')

    def test_msft_observed_signal(self):
        s=next(s for s in report_inputs() if s['ticker']=='MSFT')
        b=deepcopy(s['blend']);b['profile']={'model_weights':s['profile_assumptions']['weights']}
        b['reliability']={'reliability_score':85,'penalties':[]};b['confidence']='HIGH'
        b['exit_zone']={'eligible_for_precise_exit':True,'display_mode':'precise','trim_price':800}
        out=govern_blend('MSFT',{},b)
        self.assertEqual(out['structural_governance']['severity'],'CRITICAL')
        self.assertEqual(out['confidence'],'LOW')
        self.assertEqual(out['fair'],657.05)
        self.assertFalse(out['exit_zone']['eligible_for_precise_exit'])
        self.assertIsNone(out['exit_zone']['trim_price'])
        self.assertEqual(out['models'],b['models'])

    def test_production_invariants_all_fixtures(self):
        from tests.test_peer_diagnostic_isolation import FINANCIALS
        for ticker in FINANCIALS:
            with self.subTest(ticker=ticker):
                with patch('production_reliability_governance.govern_blend',side_effect=lambda t,f,b:b):before=analyze(ticker)
                after=analyze(ticker)
                for key in ('fair_value','blended_low','blended_mid','blended_high','zones','pe','dcf','growth'):
                    self.assertEqual(before.get(key),after.get(key),key)
                for key in ('models','weights_used','included','excluded','mos'):
                    self.assertEqual(before['blend'].get(key),after['blend'].get(key),key)
                audit=after['blend'].get('reliability_governance_audit')
                if audit:self.assertTrue(all(audit['invariants'].values()))

    def test_no_exit_unlock(self):
        r=analyze('AMZN');b=deepcopy(r['blend']);b.pop('reliability_governance_version',None)
        b['exit_zone']['eligible_for_precise_exit']=False
        with patch('production_reliability_governance.independent_evidence_audit',return_value=evidence('NONE')):
            self.assertFalse(govern_blend('AMZN',{},b)['exit_zone']['eligible_for_precise_exit'])

    def test_none_score_unchanged(self):
        r=analyze('AMZN');b=deepcopy(r['blend']);b.pop('reliability_governance_version',None)
        b['reliability']['reliability_score']=90;b['confidence']='HIGH'
        with patch('production_reliability_governance.independent_evidence_audit',return_value=evidence('NONE')):
            out=govern_blend('AMZN',{},b)
        self.assertEqual(out['reliability']['reliability_score'],90)
        self.assertEqual(out['confidence'],'HIGH')

    def test_idempotent(self):
        b=analyze('AMZN')['blend']
        self.assertEqual(govern_blend('AMZN',{},b),b)

    def test_score_clamped(self):
        b=analyze('AMZN')['blend'];b.pop('reliability_governance_version',None)
        b['reliability']['reliability_score']=3
        self.assertEqual(govern_blend('AMZN',{},b)['reliability']['reliability_score'],0)

    def test_benchmark_price_peer_independent(self):
        s=next(s for s in report_inputs() if s['ticker']=='MSFT');b=s['blend']
        b['profile']={'model_weights':s['profile_assumptions']['weights']};b['reliability']={'reliability_score':90};b['confidence']='HIGH'
        before=govern_blend('X',{},b)['structural_governance']
        b.update(benchmark=1,price=1e99,peer_comparable_result={'mid':1},analyst_target=1e99)
        self.assertEqual(before,govern_blend('Y',{'price':999},b)['structural_governance'])

    def test_old_snapshot_null_governance(self):
        self.assertIsNone(reliability_from_snapshot({'reliability_json':{'reliability_score':70}})['structural_governance'])

    def test_persistence_governance_and_version(self):
        r=analyze('AMZN');record=build_snapshot_record('owner',r)
        self.assertEqual(record['raw']['reliability_governance_version'],'v4.6.1')
        self.assertEqual(record['raw']['structural_governance'],r['blend']['structural_governance'])
        restored=reconstruct_blend_from_snapshot(record)
        self.assertEqual(restored['structural_governance'],r['blend']['structural_governance'])
        self.assertEqual(restored['model_version'],r['model_version'])

    def test_last_reliable_preserves_historical_governance(self):
        good=analyze();saved=reliable_snapshot(good,NOW)
        missing=analyze(book_value_per_share=None,tangible_book_value_per_share=None)
        out=apply_last_reliable(missing,{'raw':{'last_reliable':saved}},NOW+timedelta(hours=1))
        self.assertEqual(out['source_status'],'cached_last_reliable')
        self.assertEqual(out['blend'],good['blend'])
        self.assertEqual(out['calculated_at'],saved['calculated_at'])

    def test_fingerprint_metadata_invariant(self):
        r=analyze();before=reliable_snapshot(r,NOW)['input_fingerprint']
        r['blend']['structural_governance']={'severity':'CRITICAL'}
        r['structural_governance']={'severity':'CRITICAL'}
        self.assertEqual(before,reliable_snapshot(r,NOW)['input_fingerprint'])

    def test_governance_no_io(self):
        b=analyze('AMZN')['blend'];b.pop('reliability_governance_version',None)
        with patch('builtins.open',side_effect=AssertionError('unexpected IO')):govern_blend('AMZN',{},b)

    def test_peer_model_never_structural_evidence(self):
        b=analyze('AMZN')['blend'];b.pop('reliability_governance_version',None)
        before=govern_blend('AMZN',{},b)['structural_governance']
        b['models']['peer_comparable']={'valid':True,'applicable':True,'executed':True,'mid':999}
        b['included'].append('peer_comparable')
        self.assertEqual(before,govern_blend('AMZN',{},b)['structural_governance'])

    def test_governed_low_not_upgraded(self):
        b=analyze('AMZN')['blend'];b.pop('reliability_governance_version',None)
        b['confidence']='LOW';b['reliability']['reliability_score']=95
        with patch('production_reliability_governance.independent_evidence_audit',return_value=evidence('MODERATE')):
            self.assertEqual(govern_blend('AMZN',{},b)['confidence'],'LOW')

    def test_highest_severity_wins(self):
        g=evaluate({**evidence('CRITICAL'),'active_family_count':1,'structural_gaps':['x']})
        self.assertEqual(g['severity'],'CRITICAL')

    def test_legacy_last_reliable_no_metadata(self):
        good=analyze();saved=reliable_snapshot(good,NOW)
        for key in ('structural_governance','reliability_governance_version'):
            saved['valuation'].pop(key,None)
            saved['valuation']['blend'].pop(key,None)
        missing=analyze(book_value_per_share=None,tangible_book_value_per_share=None)
        out=apply_last_reliable(missing,{'raw':{'last_reliable':saved}},NOW+timedelta(hours=1))
        self.assertEqual(out['source_status'],'cached_last_reliable')
        self.assertIsNone(out['blend'].get('structural_governance'))

    def test_admin_five_stock_audit_no_database_write(self):
        import test_v45_snapshot_export as fixtures
        helper=fixtures.SnapshotExportTests();helper.setUp()
        try:
            helper.client.table.side_effect=AssertionError('No database access')
            report=helper.batch()
            self.assertEqual(len(report['stocks']),5)
            for stock in report['stocks']:
                audit=stock['reliability_governance_audit']
                if audit:self.assertTrue(audit['fair_unchanged'] and all(audit['invariants'].values()))
            helper.client.table.assert_not_called()
        finally:helper.doCleanups()
