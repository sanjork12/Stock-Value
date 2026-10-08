"""V5.2 conservative registry: field names alone do not establish reporting periods."""
POLICY_VERSION='v5.2'
METRICS={
    'ebitda':('ebitda','CURRENT_PROVIDER_FLOW_METRIC'),
    'revenue':('totalRevenue','CURRENT_PROVIDER_FLOW_METRIC'),
    'cash':('totalCash','CURRENT_PROVIDER_CASH_AGGREGATE'),
    'debt':('totalDebt','CURRENT_PROVIDER_DEBT_AGGREGATE'),
    'canonical_shares':('impliedSharesOutstanding','CURRENT_MARKET_IMPLIED_CANDIDATE'),
}
POLICY={'strong_match':.05,'moderate_match':.10,'quarter_gap_min_days':75,'quarter_gap_max_days':105,
    'stock_material_difference':.15,
    'metric_basis_full_credit':10,'metric_basis_partial_credit':5,'metric_basis_no_credit':0}
QUARTERLY_PATHS=('quarterly_income_stmt','quarterly_financials','quarterly_cashflow','quarterly_balance_sheet')
REPORTING_EPOCHS=('lastFiscalYearEnd','nextFiscalYearEnd','mostRecentQuarter','earningsTimestamp','earningsTimestampStart','earningsTimestampEnd')

def registry():
    return {k:{'field_name':v[0],'provider_semantics':v[1],'period_semantics':'UNKNOWN_UNLESS_PROVEN',
        'source_evidence':'Accepted same-acquisition provider payload; explicit metadata or aligned statement reconstruction required',
        'confidence':'LOW','policy_version':POLICY_VERSION} for k,v in METRICS.items()}
