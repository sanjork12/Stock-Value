import unittest
from market_reference import build_market_reference, apply_reference_display_policy
from analysis_service import format_fair_value

class MarketReferenceTests(unittest.TestCase):
    def test_deviation_and_thresholds(self):
        for fair, status in [(81,'NORMAL'),(80,'REVIEW'),(65,'REVIEW'),(64,'HIGH_DIVERGENCE'),(136,'HIGH_DIVERGENCE')]:
            r=build_market_reference('X',{'analyst_consensus_target':100},fair)
            self.assertEqual(r['sanity_status'],status)
            self.assertAlmostEqual(r['internal_vs_consensus_pct'],fair-100)
    def test_no_reference_and_invalid(self):
        for target in [None,0,-1,float('nan'),float('inf')]:
            r=build_market_reference('X',{'analyst_consensus_target':target},100)
            self.assertEqual(r['sanity_status'],'NO_EXTERNAL_REFERENCE')
            self.assertEqual(r['internal_fair_mid'],100)
    def test_independent(self):
        f={'forward_eps':5,'analyst_consensus_target':500}
        before=dict(f)
        r=build_market_reference('X',f,100,150)
        self.assertEqual(f,before)
        self.assertEqual(r['internal_fair_mid'],100)
        self.assertEqual(r['internal_implied_forward_pe'],20)
        self.assertEqual(r['current_forward_pe'],30)
    def test_policy_preserves_numeric_model(self):
        zones={'core':(10.,20.)}
        r={'confidence':'LOW','blended_low':10.,'blended_mid':15.,'blended_high':20.,'zones':zones,'market_reference':{'sanity_status':'HIGH_DIVERGENCE'}}
        apply_reference_display_policy(r)
        self.assertTrue(r['hide_precise_trading_zones'])
        self.assertEqual(r['zones'],zones)
        self.assertEqual(r['valuation_mode'],'LOW_CONFIDENCE')
        self.assertIsInstance(r['valuation_low'],float)
    def test_specialized_reference(self):
        r={'confidence':'SPECIALIZED','market_reference':build_market_reference('TSLA',{'analyst_consensus_target':300},None)}
        apply_reference_display_policy(r)
        self.assertIsNone(r['confidence'])
        self.assertEqual(r['valuation_mode'],'SPECIALIZED')
        self.assertEqual(r['market_reference']['analyst_consensus_target'],300)
    def test_precision(self):
        self.assertEqual(format_fair_value({'confidence':'HIGH','fair':251.39999389648438}),'$251.40')
        self.assertEqual(format_fair_value({'confidence':'LOW','blended_low':37.123,'blended_high':63.987}),'$37 – $64')
    def test_missing_eps_and_dates(self):
        r=build_market_reference('X',{'forward_eps':-1},100)
        self.assertIsNone(r['internal_implied_forward_pe'])
        self.assertIsNone(r['consensus_updated_at'])
