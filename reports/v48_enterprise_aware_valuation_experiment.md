# V4.8 Enterprise-Aware Earnings Valuation Experiment

## A. Executive summary

Default report reuses prior approximate Cloud model observations, not a new Cloud execution. Full same-run cash/debt, shares, EBITDA/revenue and captured class ranges are unavailable. No values are inferred from supplied ratios or fair estimates.
New results are only under enterprise_aware_experiment in the administrator audit. No production family-map registration, fair/range, model weights, outlier, V4.6 reliability/confidence/exits, Peer, normal snapshot or Last Reliable changes. Structurally distinct family evidence does not imply statistical independence. Two correlated enterprise methods count as one family.

## B. Applicability

Each method requires its own positive EBITDA or revenue, positive canonical shares, available nonnegative cash/debt, known equal financial/quote currencies without mismatch, and its captured positive ordered class range. No default ranges or zero debt/cash substitution. Missing EBITDA does not block Revenue, and vice versa. Cached displays and explicitly ineligible calibration inputs fail closed; no historical/current financial mixing. Profitability is not an extra gate for these enterprise methods.

## C. EV/EBITDA methodology

Multiples = captured class low,(low+high)/2,high. Enterprise values = EBITDA×multiples. Equity values = enterprise values−(debt−cash). Per-share values = equity/canonical shares. Deduct net debt exactly once; net cash adds to equity. Preserve nonpositive values and mark negative_equity_signal; they remain diagnostic numeric signals. Nonfinite results are invalid.

## D. EV/Revenue methodology

Use captured sales_multiple_range identically: revenue×multiple−net debt, divided by canonical shares. No EPS, P/E discount or earnings fair is used to calculate either enterprise method. Both models are registered only in the experiment-local map as ENTERPRISE_MULTIPLE, experimental_family=true, production_included=false. The existing production revenue_multiple family mapping stays unchanged.

## E. Enterprise family aggregation

Two valid methods:50/50 weighted mean independently for low/mid/high. One valid method:100% of that method, single_method_only=true and LOW confidence. No valid method: null family and UNAVAILABLE. Two methods: spread = (max(mid)−min(mid))/median(mid)×100; <=20% CONSISTENT and MEDIUM confidence; (20%,40%] MODERATE_DISAGREEMENT and LOW; >40% METHOD_DISAGREEMENT and LOW plus warning. Nonpositive median prevents meaningful percentage spread: null spread, warning and LOW confidence. No HIGH confidence in V4.8.

## F. GOOG

Evidence: user_supplied_approximate_Cloud_model_observations. Production fair: 253.81 (unchanged).

```json
{
  "applicability": {
    "applicable": false,
    "valid_method_count": 0,
    "global_reasons": [],
    "currency_safe": false,
    "model_reasons": {
      "ev_ebitda": [
        "missing_or_nonpositive_ebitda",
        "missing_or_nonpositive_canonical_shares",
        "missing_or_negative_cash_debt",
        "capital_currency_unsafe_or_unknown",
        "missing_or_invalid_captured_class_range"
      ],
      "ev_revenue": [
        "missing_or_nonpositive_revenue",
        "missing_or_nonpositive_canonical_shares",
        "missing_or_negative_cash_debt",
        "capital_currency_unsafe_or_unknown",
        "missing_or_invalid_captured_class_range"
      ]
    }
  },
  "diagnostic_family_map": {
    "ev_ebitda": "ENTERPRISE_MULTIPLE",
    "ev_revenue": "ENTERPRISE_MULTIPLE"
  },
  "experimental_family": true,
  "production_included": false,
  "ev_ebitda_model": {
    "model_name": "ev_ebitda",
    "model_family": "ENTERPRISE_MULTIPLE",
    "experimental_family": true,
    "production_included": false,
    "valid": false,
    "applicable": false,
    "executed": false,
    "reasons": [
      "missing_or_nonpositive_ebitda",
      "missing_or_nonpositive_canonical_shares",
      "missing_or_negative_cash_debt",
      "capital_currency_unsafe_or_unknown",
      "missing_or_invalid_captured_class_range"
    ],
    "inputs_used": {
      "basis": null,
      "canonical_shares": null,
      "cash": null,
      "debt": null,
      "net_debt": null,
      "class_range": null
    },
    "low": null,
    "mid": null,
    "high": null,
    "enterprise_values": null,
    "equity_values": null,
    "negative_equity_signal": false
  },
  "ev_revenue_model": {
    "model_name": "ev_revenue",
    "model_family": "ENTERPRISE_MULTIPLE",
    "experimental_family": true,
    "production_included": false,
    "valid": false,
    "applicable": false,
    "executed": false,
    "reasons": [
      "missing_or_nonpositive_revenue",
      "missing_or_nonpositive_canonical_shares",
      "missing_or_negative_cash_debt",
      "capital_currency_unsafe_or_unknown",
      "missing_or_invalid_captured_class_range"
    ],
    "inputs_used": {
      "basis": null,
      "canonical_shares": null,
      "cash": null,
      "debt": null,
      "net_debt": null,
      "class_range": null
    },
    "low": null,
    "mid": null,
    "high": null,
    "enterprise_values": null,
    "equity_values": null,
    "negative_equity_signal": false
  },
  "enterprise_family": {
    "low": null,
    "mid": null,
    "high": null,
    "family": "ENTERPRISE_MULTIPLE",
    "confidence": "UNAVAILABLE",
    "weights": {},
    "single_method_only": false,
    "valid_method_count": 0,
    "negative_equity_signal": false
  },
  "enterprise_family_low": null,
  "enterprise_family_mid": null,
  "enterprise_family_high": null,
  "enterprise_family_confidence": "UNAVAILABLE",
  "single_method_only": false,
  "method_spread_pct": null,
  "enterprise_method_spread_pct": null,
  "method_consistency": "UNAVAILABLE",
  "method_spread_reason": "requires_two_methods_and_positive_median",
  "earnings_family_mid": 329.87166666666667,
  "difference_vs_earnings_pct": null,
  "difference_band": "UNAVAILABLE",
  "difference_direction": null,
  "enterprise_evidence_status": "UNAVAILABLE",
  "experimental_observed_families": [
    "CASH_FLOW_INTRINSIC",
    "EARNINGS_MULTIPLE"
  ],
  "experimental_independent_family_count": 2,
  "production_active_families": [
    "CASH_FLOW_INTRINSIC",
    "EARNINGS_MULTIPLE"
  ],
  "earnings_enterprise_equal_weight_fair": null,
  "production_fair": 253.81,
  "difference_vs_production_pct": null,
  "production_readiness": "NOT_READY",
  "enterprise_family_production_readiness": "NOT_READY",
  "capital_burden_band": "UNAVAILABLE",
  "business_mix_warning": null,
  "business_mix_warning_reason": "not_present_in_captured_production_fields",
  "cash_flow_family_mid": 139.72,
  "nearest_observed_family": null,
  "observed_family_distances": {},
  "warnings": [],
  "scope": "DIAGNOSTIC_ONLY_NOT_A_PRODUCTION_MODEL_OR_RELIABILITY_INPUT"
}
```

## G. MSFT

Evidence: user_supplied_approximate_Cloud_model_observations. Production fair: 657.05 (unchanged).

```json
{
  "applicability": {
    "applicable": false,
    "valid_method_count": 0,
    "global_reasons": [],
    "currency_safe": false,
    "model_reasons": {
      "ev_ebitda": [
        "missing_or_nonpositive_ebitda",
        "missing_or_nonpositive_canonical_shares",
        "missing_or_negative_cash_debt",
        "capital_currency_unsafe_or_unknown",
        "missing_or_invalid_captured_class_range"
      ],
      "ev_revenue": [
        "missing_or_nonpositive_revenue",
        "missing_or_nonpositive_canonical_shares",
        "missing_or_negative_cash_debt",
        "capital_currency_unsafe_or_unknown",
        "missing_or_invalid_captured_class_range"
      ]
    }
  },
  "diagnostic_family_map": {
    "ev_ebitda": "ENTERPRISE_MULTIPLE",
    "ev_revenue": "ENTERPRISE_MULTIPLE"
  },
  "experimental_family": true,
  "production_included": false,
  "ev_ebitda_model": {
    "model_name": "ev_ebitda",
    "model_family": "ENTERPRISE_MULTIPLE",
    "experimental_family": true,
    "production_included": false,
    "valid": false,
    "applicable": false,
    "executed": false,
    "reasons": [
      "missing_or_nonpositive_ebitda",
      "missing_or_nonpositive_canonical_shares",
      "missing_or_negative_cash_debt",
      "capital_currency_unsafe_or_unknown",
      "missing_or_invalid_captured_class_range"
    ],
    "inputs_used": {
      "basis": null,
      "canonical_shares": null,
      "cash": null,
      "debt": null,
      "net_debt": null,
      "class_range": null
    },
    "low": null,
    "mid": null,
    "high": null,
    "enterprise_values": null,
    "equity_values": null,
    "negative_equity_signal": false
  },
  "ev_revenue_model": {
    "model_name": "ev_revenue",
    "model_family": "ENTERPRISE_MULTIPLE",
    "experimental_family": true,
    "production_included": false,
    "valid": false,
    "applicable": false,
    "executed": false,
    "reasons": [
      "missing_or_nonpositive_revenue",
      "missing_or_nonpositive_canonical_shares",
      "missing_or_negative_cash_debt",
      "capital_currency_unsafe_or_unknown",
      "missing_or_invalid_captured_class_range"
    ],
    "inputs_used": {
      "basis": null,
      "canonical_shares": null,
      "cash": null,
      "debt": null,
      "net_debt": null,
      "class_range": null
    },
    "low": null,
    "mid": null,
    "high": null,
    "enterprise_values": null,
    "equity_values": null,
    "negative_equity_signal": false
  },
  "enterprise_family": {
    "low": null,
    "mid": null,
    "high": null,
    "family": "ENTERPRISE_MULTIPLE",
    "confidence": "UNAVAILABLE",
    "weights": {},
    "single_method_only": false,
    "valid_method_count": 0,
    "negative_equity_signal": false
  },
  "enterprise_family_low": null,
  "enterprise_family_mid": null,
  "enterprise_family_high": null,
  "enterprise_family_confidence": "UNAVAILABLE",
  "single_method_only": false,
  "method_spread_pct": null,
  "enterprise_method_spread_pct": null,
  "method_consistency": "UNAVAILABLE",
  "method_spread_reason": "requires_two_methods_and_positive_median",
  "earnings_family_mid": 657.0441666666667,
  "difference_vs_earnings_pct": null,
  "difference_band": "UNAVAILABLE",
  "difference_direction": null,
  "enterprise_evidence_status": "UNAVAILABLE",
  "experimental_observed_families": [
    "CASH_FLOW_INTRINSIC",
    "EARNINGS_MULTIPLE"
  ],
  "experimental_independent_family_count": 2,
  "production_active_families": [
    "EARNINGS_MULTIPLE"
  ],
  "earnings_enterprise_equal_weight_fair": null,
  "production_fair": 657.05,
  "difference_vs_production_pct": null,
  "production_readiness": "NOT_READY",
  "enterprise_family_production_readiness": "NOT_READY",
  "capital_burden_band": "UNAVAILABLE",
  "business_mix_warning": null,
  "business_mix_warning_reason": "not_present_in_captured_production_fields",
  "cash_flow_family_mid": 203.34,
  "nearest_observed_family": null,
  "observed_family_distances": {},
  "warnings": [],
  "scope": "DIAGNOSTIC_ONLY_NOT_A_PRODUCTION_MODEL_OR_RELIABILITY_INPUT"
}
```

## H. ORCL

Evidence: user_supplied_approximate_Cloud_model_observations. Production fair: 237.75 (unchanged).

```json
{
  "applicability": {
    "applicable": false,
    "valid_method_count": 0,
    "global_reasons": [],
    "currency_safe": false,
    "model_reasons": {
      "ev_ebitda": [
        "missing_or_nonpositive_ebitda",
        "missing_or_nonpositive_canonical_shares",
        "missing_or_negative_cash_debt",
        "capital_currency_unsafe_or_unknown",
        "missing_or_invalid_captured_class_range"
      ],
      "ev_revenue": [
        "missing_or_nonpositive_revenue",
        "missing_or_nonpositive_canonical_shares",
        "missing_or_negative_cash_debt",
        "capital_currency_unsafe_or_unknown",
        "missing_or_invalid_captured_class_range"
      ]
    }
  },
  "diagnostic_family_map": {
    "ev_ebitda": "ENTERPRISE_MULTIPLE",
    "ev_revenue": "ENTERPRISE_MULTIPLE"
  },
  "experimental_family": true,
  "production_included": false,
  "ev_ebitda_model": {
    "model_name": "ev_ebitda",
    "model_family": "ENTERPRISE_MULTIPLE",
    "experimental_family": true,
    "production_included": false,
    "valid": false,
    "applicable": false,
    "executed": false,
    "reasons": [
      "missing_or_nonpositive_ebitda",
      "missing_or_nonpositive_canonical_shares",
      "missing_or_negative_cash_debt",
      "capital_currency_unsafe_or_unknown",
      "missing_or_invalid_captured_class_range"
    ],
    "inputs_used": {
      "basis": null,
      "canonical_shares": null,
      "cash": null,
      "debt": null,
      "net_debt": null,
      "class_range": null
    },
    "low": null,
    "mid": null,
    "high": null,
    "enterprise_values": null,
    "equity_values": null,
    "negative_equity_signal": false
  },
  "ev_revenue_model": {
    "model_name": "ev_revenue",
    "model_family": "ENTERPRISE_MULTIPLE",
    "experimental_family": true,
    "production_included": false,
    "valid": false,
    "applicable": false,
    "executed": false,
    "reasons": [
      "missing_or_nonpositive_revenue",
      "missing_or_nonpositive_canonical_shares",
      "missing_or_negative_cash_debt",
      "capital_currency_unsafe_or_unknown",
      "missing_or_invalid_captured_class_range"
    ],
    "inputs_used": {
      "basis": null,
      "canonical_shares": null,
      "cash": null,
      "debt": null,
      "net_debt": null,
      "class_range": null
    },
    "low": null,
    "mid": null,
    "high": null,
    "enterprise_values": null,
    "equity_values": null,
    "negative_equity_signal": false
  },
  "enterprise_family": {
    "low": null,
    "mid": null,
    "high": null,
    "family": "ENTERPRISE_MULTIPLE",
    "confidence": "UNAVAILABLE",
    "weights": {},
    "single_method_only": false,
    "valid_method_count": 0,
    "negative_equity_signal": false
  },
  "enterprise_family_low": null,
  "enterprise_family_mid": null,
  "enterprise_family_high": null,
  "enterprise_family_confidence": "UNAVAILABLE",
  "single_method_only": false,
  "method_spread_pct": null,
  "enterprise_method_spread_pct": null,
  "method_consistency": "UNAVAILABLE",
  "method_spread_reason": "requires_two_methods_and_positive_median",
  "earnings_family_mid": 237.74923076923076,
  "difference_vs_earnings_pct": null,
  "difference_band": "UNAVAILABLE",
  "difference_direction": null,
  "enterprise_evidence_status": "UNAVAILABLE",
  "experimental_observed_families": [
    "EARNINGS_MULTIPLE"
  ],
  "experimental_independent_family_count": 1,
  "production_active_families": [
    "EARNINGS_MULTIPLE"
  ],
  "earnings_enterprise_equal_weight_fair": null,
  "production_fair": 237.75,
  "difference_vs_production_pct": null,
  "production_readiness": "NOT_READY",
  "enterprise_family_production_readiness": "NOT_READY",
  "capital_burden_band": "UNAVAILABLE",
  "business_mix_warning": null,
  "business_mix_warning_reason": "not_present_in_captured_production_fields",
  "cash_flow_family_mid": null,
  "nearest_observed_family": null,
  "observed_family_distances": {},
  "warnings": [],
  "scope": "DIAGNOSTIC_ONLY_NOT_A_PRODUCTION_MODEL_OR_RELIABILITY_INPUT"
}
```

## I. NVDA

Evidence: user_supplied_approximate_Cloud_model_observations. Production fair: 358.45 (unchanged).

```json
{
  "applicability": {
    "applicable": false,
    "valid_method_count": 0,
    "global_reasons": [],
    "currency_safe": false,
    "model_reasons": {
      "ev_ebitda": [
        "missing_or_nonpositive_ebitda",
        "missing_or_nonpositive_canonical_shares",
        "missing_or_negative_cash_debt",
        "capital_currency_unsafe_or_unknown",
        "missing_or_invalid_captured_class_range"
      ],
      "ev_revenue": [
        "missing_or_nonpositive_revenue",
        "missing_or_nonpositive_canonical_shares",
        "missing_or_negative_cash_debt",
        "capital_currency_unsafe_or_unknown",
        "missing_or_invalid_captured_class_range"
      ]
    }
  },
  "diagnostic_family_map": {
    "ev_ebitda": "ENTERPRISE_MULTIPLE",
    "ev_revenue": "ENTERPRISE_MULTIPLE"
  },
  "experimental_family": true,
  "production_included": false,
  "ev_ebitda_model": {
    "model_name": "ev_ebitda",
    "model_family": "ENTERPRISE_MULTIPLE",
    "experimental_family": true,
    "production_included": false,
    "valid": false,
    "applicable": false,
    "executed": false,
    "reasons": [
      "missing_or_nonpositive_ebitda",
      "missing_or_nonpositive_canonical_shares",
      "missing_or_negative_cash_debt",
      "capital_currency_unsafe_or_unknown",
      "missing_or_invalid_captured_class_range"
    ],
    "inputs_used": {
      "basis": null,
      "canonical_shares": null,
      "cash": null,
      "debt": null,
      "net_debt": null,
      "class_range": null
    },
    "low": null,
    "mid": null,
    "high": null,
    "enterprise_values": null,
    "equity_values": null,
    "negative_equity_signal": false
  },
  "ev_revenue_model": {
    "model_name": "ev_revenue",
    "model_family": "ENTERPRISE_MULTIPLE",
    "experimental_family": true,
    "production_included": false,
    "valid": false,
    "applicable": false,
    "executed": false,
    "reasons": [
      "missing_or_nonpositive_revenue",
      "missing_or_nonpositive_canonical_shares",
      "missing_or_negative_cash_debt",
      "capital_currency_unsafe_or_unknown",
      "missing_or_invalid_captured_class_range"
    ],
    "inputs_used": {
      "basis": null,
      "canonical_shares": null,
      "cash": null,
      "debt": null,
      "net_debt": null,
      "class_range": null
    },
    "low": null,
    "mid": null,
    "high": null,
    "enterprise_values": null,
    "equity_values": null,
    "negative_equity_signal": false
  },
  "enterprise_family": {
    "low": null,
    "mid": null,
    "high": null,
    "family": "ENTERPRISE_MULTIPLE",
    "confidence": "UNAVAILABLE",
    "weights": {},
    "single_method_only": false,
    "valid_method_count": 0,
    "negative_equity_signal": false
  },
  "enterprise_family_low": null,
  "enterprise_family_mid": null,
  "enterprise_family_high": null,
  "enterprise_family_confidence": "UNAVAILABLE",
  "single_method_only": false,
  "method_spread_pct": null,
  "enterprise_method_spread_pct": null,
  "method_consistency": "UNAVAILABLE",
  "method_spread_reason": "requires_two_methods_and_positive_median",
  "earnings_family_mid": 358.44384615384615,
  "difference_vs_earnings_pct": null,
  "difference_band": "UNAVAILABLE",
  "difference_direction": null,
  "enterprise_evidence_status": "UNAVAILABLE",
  "experimental_observed_families": [
    "EARNINGS_MULTIPLE"
  ],
  "experimental_independent_family_count": 1,
  "production_active_families": [
    "EARNINGS_MULTIPLE"
  ],
  "earnings_enterprise_equal_weight_fair": null,
  "production_fair": 358.45,
  "difference_vs_production_pct": null,
  "production_readiness": "NOT_READY",
  "enterprise_family_production_readiness": "NOT_READY",
  "capital_burden_band": "UNAVAILABLE",
  "business_mix_warning": null,
  "business_mix_warning_reason": "not_present_in_captured_production_fields",
  "cash_flow_family_mid": null,
  "nearest_observed_family": null,
  "observed_family_distances": {},
  "warnings": [],
  "scope": "DIAGNOSTIC_ONLY_NOT_A_PRODUCTION_MODEL_OR_RELIABILITY_INPUT"
}
```

## J. AMZN

Evidence: user_supplied_approximate_Cloud_model_observations. Production fair: 290.44 (unchanged).

```json
{
  "applicability": {
    "applicable": false,
    "valid_method_count": 0,
    "global_reasons": [],
    "currency_safe": false,
    "model_reasons": {
      "ev_ebitda": [
        "missing_or_nonpositive_ebitda",
        "missing_or_nonpositive_canonical_shares",
        "missing_or_negative_cash_debt",
        "capital_currency_unsafe_or_unknown",
        "missing_or_invalid_captured_class_range"
      ],
      "ev_revenue": [
        "missing_or_nonpositive_revenue",
        "missing_or_nonpositive_canonical_shares",
        "missing_or_negative_cash_debt",
        "capital_currency_unsafe_or_unknown",
        "missing_or_invalid_captured_class_range"
      ]
    }
  },
  "diagnostic_family_map": {
    "ev_ebitda": "ENTERPRISE_MULTIPLE",
    "ev_revenue": "ENTERPRISE_MULTIPLE"
  },
  "experimental_family": true,
  "production_included": false,
  "ev_ebitda_model": {
    "model_name": "ev_ebitda",
    "model_family": "ENTERPRISE_MULTIPLE",
    "experimental_family": true,
    "production_included": false,
    "valid": false,
    "applicable": false,
    "executed": false,
    "reasons": [
      "missing_or_nonpositive_ebitda",
      "missing_or_nonpositive_canonical_shares",
      "missing_or_negative_cash_debt",
      "capital_currency_unsafe_or_unknown",
      "missing_or_invalid_captured_class_range"
    ],
    "inputs_used": {
      "basis": null,
      "canonical_shares": null,
      "cash": null,
      "debt": null,
      "net_debt": null,
      "class_range": null
    },
    "low": null,
    "mid": null,
    "high": null,
    "enterprise_values": null,
    "equity_values": null,
    "negative_equity_signal": false
  },
  "ev_revenue_model": {
    "model_name": "ev_revenue",
    "model_family": "ENTERPRISE_MULTIPLE",
    "experimental_family": true,
    "production_included": false,
    "valid": false,
    "applicable": false,
    "executed": false,
    "reasons": [
      "missing_or_nonpositive_revenue",
      "missing_or_nonpositive_canonical_shares",
      "missing_or_negative_cash_debt",
      "capital_currency_unsafe_or_unknown",
      "missing_or_invalid_captured_class_range"
    ],
    "inputs_used": {
      "basis": null,
      "canonical_shares": null,
      "cash": null,
      "debt": null,
      "net_debt": null,
      "class_range": null
    },
    "low": null,
    "mid": null,
    "high": null,
    "enterprise_values": null,
    "equity_values": null,
    "negative_equity_signal": false
  },
  "enterprise_family": {
    "low": null,
    "mid": null,
    "high": null,
    "family": "ENTERPRISE_MULTIPLE",
    "confidence": "UNAVAILABLE",
    "weights": {},
    "single_method_only": false,
    "valid_method_count": 0,
    "negative_equity_signal": false
  },
  "enterprise_family_low": null,
  "enterprise_family_mid": null,
  "enterprise_family_high": null,
  "enterprise_family_confidence": "UNAVAILABLE",
  "single_method_only": false,
  "method_spread_pct": null,
  "enterprise_method_spread_pct": null,
  "method_consistency": "UNAVAILABLE",
  "method_spread_reason": "requires_two_methods_and_positive_median",
  "earnings_family_mid": 290.44666666666666,
  "difference_vs_earnings_pct": null,
  "difference_band": "UNAVAILABLE",
  "difference_direction": null,
  "enterprise_evidence_status": "UNAVAILABLE",
  "experimental_observed_families": [
    "EARNINGS_MULTIPLE"
  ],
  "experimental_independent_family_count": 1,
  "production_active_families": [
    "EARNINGS_MULTIPLE"
  ],
  "earnings_enterprise_equal_weight_fair": null,
  "production_fair": 290.44,
  "difference_vs_production_pct": null,
  "production_readiness": "NOT_READY",
  "enterprise_family_production_readiness": "NOT_READY",
  "capital_burden_band": "UNAVAILABLE",
  "business_mix_warning": null,
  "business_mix_warning_reason": "not_present_in_captured_production_fields",
  "cash_flow_family_mid": null,
  "nearest_observed_family": null,
  "observed_family_distances": {},
  "warnings": [],
  "scope": "DIAGNOSTIC_ONLY_NOT_A_PRODUCTION_MODEL_OR_RELIABILITY_INPUT"
}
```

ORCL supplied high net-debt and multiple-stretch observations motivate the experiment but cannot reconstruct exact same-run shares, cash/debt, EBITDA and revenue. Five-company numerical/readiness comparisons remain unavailable until Cloud capture. No ORCL-specific condition is implemented. GOOG net-cash and MSFT/NVDA/AMZN controls are evaluated from actual inputs, not expected ticker outcomes.

## K. Method consistency

| Ticker | EBITDA mid | Revenue mid | Family mid | Spread % | Confidence |
| --- | --- | --- | --- | --- | --- |
| GOOG | None | None | None | None | UNAVAILABLE |
| MSFT | None | None | None | None | UNAVAILABLE |
| ORCL | None | None | None | None | UNAVAILABLE |
| NVDA | None | None | None | None | UNAVAILABLE |
| AMZN | None | None | None | None | UNAVAILABLE |

## L. Earnings-family conflict

Reuse captured V4.5.2 earnings-family weighted representative. Difference = (enterprise family mid/earnings family mid−1)×100. Absolute bands <=10% CONSISTENT,<=25% MODERATE_DIFFERENCE,<=50% MATERIAL_DIFFERENCE,>50% SEVERE_DIFFERENCE; direction UP/DOWN, exact zero FLAT. Evidence statuses map to CONSISTENT_WITH_EARNINGS, MODERATE_CONFLICT, MATERIAL_CONFLICT or SEVERE_CONFLICT, with SINGLE_METHOD/UNAVAILABLE taking priority.
Optional equal-family diagnostic fair =50% earnings+50% enterprise. Difference versus production uses this experimental midpoint, not a production adjustment. Observed diagnostic families union existing successful numeric families with ENTERPRISE_MULTIPLE, without changing production active counts. Existing ENTERPRISE_MULTIPLE is not counted twice. Observed cashflow family and nearest-family distances are reported when both comparison families exist; no benchmark selects a preferred model.

## M. Production readiness

STRONG_CANDIDATE requires two valid positive-midpoint methods,spread<=20%,absolute earnings difference>=25%,and captured V4.7 burden HIGH/VERY_HIGH. Missing earnings comparison,one method,spread>40%,unavailable spread or nonpositive midpoint → NOT_READY. Remaining two-method cases → REVIEW_CANDIDATE. These labels cannot activate production weighting or reliability.
| Ticker | Evidence status | Experimental family count | Readiness |
| --- | --- | --- | --- |
| GOOG | UNAVAILABLE | 2 | NOT_READY |
| MSFT | UNAVAILABLE | 2 | NOT_READY |
| ORCL | UNAVAILABLE | 1 | NOT_READY |
| NVDA | UNAVAILABLE | 1 | NOT_READY |
| AMZN | UNAVAILABLE | 1 | NOT_READY |

Material earnings differences emit CLASS_MULTIPLE_FIT_REQUIRES_REVIEW, without tuning class ranges. Business-mix warnings are copied only from existing captured fields; absent warnings remain null, with a reason. No AWS/retail or semiconductor rule is inferred from ticker names.
Cloud validation: ADMIN_EMAIL opens the existing V4.5/V4.6 five-stock batch and inspects Enterprise-Aware Valuation Experiment. Existing v45_cloud_production_analysis.json includes full namespace; CSV includes namespace-prefixed enterprise summary. Normal snapshot writing and Last Reliable are not called by this audit. To regenerate from exact exported inputs: python scripts/audit_enterprise_aware_experiment.py --input-json <export>. No credentials in exports.

## N. V4.9 recommendation

Wait for actual eligible Cloud method spreads, earnings conflicts, burden and class-fit warnings. Consider formal enterprise-family registration only where internal methods are coherent and capital-heavy evidence supports it. Review class-specific applicability before multiple calibration; never use benchmark closeness. Reliability or production blend admission requires a separate version and before/after validation. Where enterprise methods disagree or capex distortion dominates, investigate CapEx-normalized owner earnings instead. No V4.9 work is implemented.
Validation:654 tests PASS,0 FAIL/ERROR; administrator widget capture/download/access-revocation validation PASS. Synthetic formulas,net cash,negative equity,method-specific missing inputs,family aggregation,confidence/readiness,production invariants,no-write snapshot isolation and external-data independence are tested. Actual Cloud validation pending deployment. No push.
