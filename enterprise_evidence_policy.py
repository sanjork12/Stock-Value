"""Central diagnostic evidence thresholds. Never imported by valuation primitives."""
EVIDENCE_POLICY_VERSION='v5.0'
POLICY={
    'min_annual_period_gap_days':270,'highly_heterogeneous_material_segments':4,
    'min_annual_observations':3,'max_annual_observations':5,
    'ebitda_cv_stable':.25,'ebitda_cv_moderate':.50,'ebitda_cv_volatile':1.,
    'margin_stable_spread':.05,'margin_moderate_spread':.10,'margin_trend_slope':.015,
    'high_margin':.25,'low_margin':.10,
    'revenue_discontinuity_growth':1.,'revenue_growth_swing':.40,
    'growth_elevated':.10,'growth_possible':.25,'growth_material':.50,
    'capex_revenue_bands':(.05,.15,.30),'capex_ocf_bands':(.30,.70,1.),
    'leverage_bands':(1.,2.,3.5),'da_revenue_bands':(.05,.15),'sbc_revenue_bands':(.02,.05,.10),
    'sbc_ebitda_bands':(.10,.25,.50),'sbc_ocf_bands':(.10,.25,.50),
    'segment_material_share':.10,'segment_margin_dispersion':.15,'segment_growth_dispersion':.40,
    'unusual_items_revenue_materiality':.05,'basis_asof_max_days':550,'coverage_high':85,'coverage_medium':70,'coverage_low':50,
}
COVERAGE_WEIGHTS={'ebitda':15,'revenue':15,'margin_history':15,'capital_intensity':15,
    'business_mix':15,'accounting':10,'metric_basis':10,'growth_cycle':5}
