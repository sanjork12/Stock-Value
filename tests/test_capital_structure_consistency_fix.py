from copy import deepcopy
import json
from pathlib import Path
import unittest
from capital_structure_overlay import capital_overlay,consistency_assessment,overlay_summary
from test_capital_structure_overlay import fixture


def invariant_fields(value):
    excluded={'consistency_status','capital_structure_consistency_status','consistency_reason','governance',
        'capital_structure_governance','burden_overlay_materiality','ev_bridge_materiality',
        'burden_overlay_direction','ev_bridge_direction','consistency_rule_version'}
    return json.loads(json.dumps({k:v for k,v in value.items() if k not in excluded}))


class ConsistencyFixTests(unittest.TestCase):
    def test_burden_minus15_high(self):self.assertEqual(consistency_assessment(-15,-1)['burden_overlay_materiality'],'HIGH')
    def test_burden_minus10_moderate(self):self.assertEqual(consistency_assessment(-10,-1)['burden_overlay_materiality'],'MODERATE')
    def test_burden_minus5_low(self):self.assertEqual(consistency_assessment(-5,-1)['burden_overlay_materiality'],'LOW')
    def test_ev_minus30_high(self):self.assertEqual(consistency_assessment(-1,-30)['ev_bridge_materiality'],'HIGH')
    def test_ev_minus20_moderate(self):self.assertEqual(consistency_assessment(-1,-20)['ev_bridge_materiality'],'MODERATE')
    def test_ev_minus10_low(self):self.assertEqual(consistency_assessment(-1,-10)['ev_bridge_materiality'],'LOW')
    def test_high_high_same_direction(self):self.assertEqual(consistency_assessment(-15,-56)['consistency_status'],'CAPITAL_STRUCTURE_CONFLICT')
    def test_high_moderate_same_direction(self):self.assertEqual(consistency_assessment(-15,-20)['consistency_status'],'CAPITAL_STRUCTURE_CONFLICT')
    def test_high_low(self):self.assertEqual(consistency_assessment(-15,-5)['consistency_status'],'MATERIAL_CONCERN')
    def test_opposite_directions(self):self.assertEqual(consistency_assessment(-15,40)['consistency_status'],'MIXED_SIGNAL')
    def test_low_low(self):self.assertEqual(consistency_assessment(-5,10)['consistency_status'],'CONSISTENT')
    def test_both_moderate(self):self.assertEqual(consistency_assessment(-8,-20)['consistency_status'],'MATERIAL_CONCERN')
    def test_one_unavailable(self):
        for b,e in ((None,-5),(-15,None)):
            self.assertEqual(consistency_assessment(b,e)['consistency_status'],'MATERIAL_CONCERN')
    def test_both_unavailable(self):self.assertEqual(consistency_assessment(None,None)['consistency_status'],'UNAVAILABLE')
    def test_direction_flat_boundary(self):
        self.assertEqual(consistency_assessment(2,-2)['burden_overlay_direction'],'FLAT')
        self.assertEqual(consistency_assessment(2,-2)['ev_bridge_direction'],'FLAT')
        self.assertEqual(consistency_assessment(2.01,-2.01)['burden_overlay_direction'],'UP')
        self.assertEqual(consistency_assessment(2.01,-2.01)['ev_bridge_direction'],'DOWN')
    def test_positive_high_same_direction(self):self.assertEqual(consistency_assessment(15,30)['consistency_status'],'CAPITAL_STRUCTURE_CONFLICT')
    def test_rounding_boundary(self):
        self.assertEqual(consistency_assessment(-10.000000000000009,-25.00000000000001)['burden_overlay_materiality'],'MODERATE')
        self.assertEqual(consistency_assessment(-10,-25.00000000000001)['ev_bridge_materiality'],'MODERATE')
    def test_orcl_observed_classification(self):
        production=237.75
        g=consistency_assessment((202.09/production-1)*100,(104.09/production-1)*100)
        self.assertEqual(g['consistency_status'],'CAPITAL_STRUCTURE_CONFLICT')
        self.assertEqual((g['burden_overlay_direction'],g['ev_bridge_direction']),('DOWN','DOWN'))
    def test_overlay_calculation_baselines_unchanged(self):
        baseline=json.loads((Path(__file__).parent/'fixtures/v47_overlay_calculation_baselines.json').read_text())
        for case in baseline['cases']:
            with self.subTest(case=case['name']):
                s=fixture();s['normalized_inputs'].update(case['input_changes'])
                if case.get('remove_ev_range'):s['profile_assumptions'].pop('ev_ebitda_range')
                self.assertEqual(invariant_fields(capital_overlay(s)),invariant_fields(case['overlay']))
    def test_all_input_production_state_unchanged(self):
        s=fixture();s.update(reliability_score=75,confidence='MEDIUM',structural_governance={'severity':'MODERATE'},
            last_reliable={'fair':10},peer_comparable_result={'mid':300},exit_zone={'trim_price':300})
        before=deepcopy(s);capital_overlay(s)
        self.assertEqual(before,s)
    def test_conflict_governance_mapping(self):
        s=fixture();s['normalized_inputs'].update(debt=120,ebitda=120,ebit=100,interest_expense=5)
        o=capital_overlay(s)
        if o['consistency_status']=='CAPITAL_STRUCTURE_CONFLICT':
            self.assertEqual(o['governance'],'MATERIAL_CAPITAL_STRUCTURE_CONFLICT')
        # Generic heavy-debt fixture produces HIGH+HIGH, independent of ticker.
        o=capital_overlay(fixture())
        self.assertEqual(o['consistency_status'],'CAPITAL_STRUCTURE_CONFLICT')
        self.assertEqual(o['governance'],'MATERIAL_CAPITAL_STRUCTURE_CONFLICT')
    def test_summary_exposes_new_fields(self):
        s=fixture();s['capital_structure_overlay']=capital_overlay(s)
        summary=overlay_summary(s)
        self.assertEqual(summary['consistency_rule_version'],'v4.7.1')
        self.assertIn('burden_overlay_direction',summary)
