from copy import deepcopy
import unittest
from unittest.mock import patch
from capital_structure_overlay import capital_overlay,ascending_band,interest_band,sanity_band,weighted_burden,LEVERAGE_THRESHOLDS
from scripts.experiment_family_weighting import report_inputs


def fixture():
    s=next(s for s in report_inputs() if s['ticker']=='ORCL')
    s['normalized_inputs']={'cash':20.,'debt':100.,'market_cap':200.,'ebitda':20.,'revenue':100.,
        'interest_expense':5.,'ebit':25.,'canonical_shares':10.,'net_income':10.,
        'quote_currency':'USD','financial_currency':'USD'}
    s['profile_assumptions'].update(ev_ebitda_range=(10,16),sales_multiple_range=(3,6))
    return s


class CapitalOverlayTests(unittest.TestCase):
    def test_net_cash_band(self):
        s=fixture();s['normalized_inputs']['cash']=120
        self.assertEqual(capital_overlay(s)['bands']['net_debt_band'],'NET_CASH')

    def test_high_debt_band(self):
        self.assertEqual(capital_overlay(fixture())['bands']['net_debt_band'],'HIGH')
        s=fixture();s['normalized_inputs']['debt']=150
        self.assertEqual(capital_overlay(s)['bands']['net_debt_band'],'VERY_HIGH')

    def test_leverage_boundaries(self):
        self.assertEqual([ascending_band(x,LEVERAGE_THRESHOLDS) for x in (1,2,3.5,3.51,None)],['LOW','MODERATE','HIGH','VERY_HIGH','UNAVAILABLE'])

    def test_interest_boundaries(self):
        self.assertEqual([interest_band(x) for x in (8,4,2,1.9,None)],['STRONG','ADEQUATE','WEAK','VERY_WEAK','UNAVAILABLE'])

    def test_weighted_score(self):
        o=capital_overlay(fixture())
        self.assertAlmostEqual(o['burden_score'],70*.35+100*.30+35*.20+100*.15)
        self.assertAlmostEqual(sum(v['normalized_weight'] for v in o['score_components'].values()),1)

    def test_missing_component_reweights(self):
        s=fixture();s['normalized_inputs'].pop('interest_expense')
        o=capital_overlay(s)
        self.assertNotIn('interest_coverage',o['score_components_used'])
        self.assertAlmostEqual(o['burden_score'],(70*.35+100*.3+100*.15)/.8)
        self.assertIsNone(o['ratios']['interest_coverage'])
        self.assertIn('interest_expense',o['input_reasons'])

    def test_ratios_and_ev_bridge(self):
        o=capital_overlay(fixture())
        self.assertEqual(o['inputs']['net_debt'],80)
        self.assertEqual(o['inputs']['enterprise_value'],280)
        self.assertEqual(o['ratios']['interest_coverage'],5)
        self.assertEqual(o['ev_bridge_fair'],(13*20-80)/10)
        self.assertAlmostEqual(o['implied_enterprise_value'],o['earnings_family_fair']*10+80)

    def test_negative_equity_retained(self):
        s=fixture();s['normalized_inputs']['debt']=500
        o=capital_overlay(s)
        self.assertLess(o['ev_bridge_fair'],0)
        self.assertTrue(o['negative_equity_signal'])

    def test_discount_is_isolated(self):
        s=fixture();before=deepcopy(s);o=capital_overlay(s)
        self.assertAlmostEqual(o['burden_overlay_fair'],o['earnings_family_fair']*.85)
        self.assertEqual(s,before)
        self.assertEqual(s['blend']['fair'],237.75)

    def test_no_default_class_range(self):
        s=fixture();s['profile_assumptions'].pop('ev_ebitda_range')
        o=capital_overlay(s)
        self.assertIsNone(o['ev_bridge_fair'])
        self.assertEqual(o['consistency_status'],'UNAVAILABLE')

    def test_benchmark_price_peer_not_inputs(self):
        s=fixture();before=capital_overlay(s)
        s.update(benchmark=1,analyst_target=1e99,price=999,peer_comparable_result={'mid':1e99})
        s['normalized_inputs'].update(price=1e99,analyst_target=1)
        self.assertEqual(before,capital_overlay(s))

    def test_net_cash_low_burden(self):
        s=fixture();s['normalized_inputs'].update(cash=120,ebitda=100,ebit=100)
        o=capital_overlay(s)
        self.assertEqual(o['burden_band'],'LOW')
        self.assertEqual(o['burden_overlay_fair'],o['earnings_family_fair'])

    def test_high_debt_elevated_burden(self):
        self.assertEqual(capital_overlay(fixture())['burden_band'],'VERY_HIGH')

    def test_deterministic(self):
        self.assertEqual(capital_overlay(fixture()),capital_overlay(fixture()))

    def test_all_production_state_untouched(self):
        s=fixture();s.update(reliability_score=70,confidence='MEDIUM',exit_zone={'trim_price':300},
            last_reliable={'calculated_at':'original'},peer_comparable_result={'mid':10})
        before=deepcopy(s);capital_overlay(s)
        self.assertEqual(before,s)

    def test_currency_unsafe_refuses(self):
        for currency in (None,'EUR'):
            s=fixture();s['normalized_inputs']['financial_currency']=currency
            o=capital_overlay(s)
            self.assertFalse(o['applicability']['applicable'])
            self.assertIsNone(o['burden_score'])

    def test_unprofitable_refuses(self):
        s=fixture();s['normalized_inputs']['net_income']=-1
        self.assertFalse(capital_overlay(s)['applicability']['applicable'])

    def test_multiple_active_secondary_role(self):
        s=fixture();s['blend']['models']['normalized_fcf_dcf'].update(applicable=True,executed=True,valid=True,mid=200)
        s['models_before_outlier']['normalized_fcf_dcf']=deepcopy(s['blend']['models']['normalized_fcf_dcf'])
        s['blend']['included'].append('normalized_fcf_dcf')
        self.assertEqual(capital_overlay(s)['overlay_role'],'SECONDARY_DIAGNOSTIC')

    def test_no_capital_defaults(self):
        s=fixture();s['normalized_inputs'].pop('cash')
        o=capital_overlay(s)
        self.assertFalse(o['applicability']['applicable'])
        self.assertIsNone(o['inputs']['net_debt'])
        self.assertIn('net_debt',o['input_reasons'])

    def test_nonpositive_ebitda_and_zero_interest_unavailable(self):
        s=fixture();s['normalized_inputs'].update(ebitda=0,interest_expense=0)
        o=capital_overlay(s)
        self.assertEqual(o['bands']['leverage_band'],'UNAVAILABLE')
        self.assertEqual(o['bands']['interest_coverage_band'],'UNAVAILABLE')

    def test_sanity_boundaries(self):
        self.assertEqual([sanity_band(v,(10,20)) for v in (9,10,20,24,24.01)],
            ['BELOW_RANGE','WITHIN_RANGE','WITHIN_RANGE','ABOVE_RANGE','FAR_ABOVE_RANGE'])

    def test_stale_input_refuses(self):
        s=fixture();s['source_status']='cached_last_reliable'
        self.assertFalse(capital_overlay(s)['applicability']['applicable'])

    def test_no_io(self):
        s=fixture()
        with patch('builtins.open',side_effect=AssertionError('unexpected IO')):capital_overlay(s)

    def test_ticker_independent(self):
        s=fixture();before=capital_overlay(s);s['ticker']='UNKNOWN'
        self.assertEqual(before,capital_overlay(s))
