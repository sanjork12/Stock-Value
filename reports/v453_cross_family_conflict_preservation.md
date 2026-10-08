# V4.5.3 Cross-Family Conflict Preservation

## A. Executive summary

Default input replays approximate supplied Cloud observations, not a new Cloud execution. Missing EPS/capital inputs remain unknown.
Production fair, reliability, confidence, zones, weights, outliers, Peer and Last Reliable are unchanged. All signals are diagnostic namespace outputs.

## B. Active vs observed family framework

Reuse V4.5.1 mapping/dependencies and successful numeric family records. Active = observed model members included in production blend. Observed = applicable, successfully executed numeric valuation signals, including outlier-only exclusions. Invalid input, non-applicable, failed execution and null/nonfinite mids are not evidence. Independent family count equals observed family count; this is a structural family count, not proof of statistical independence.

## C. Suppression governance

Only exact outlier_vs_other_models exclusions of successful numeric models count. A fully absent active family is independent-family suppression; >=2 absent families is MULTIPLE_FAMILIES_SUPPRESSED. A removed member of a still-active family is SAME_FAMILY_MODEL_SUPPRESSED. No production exclusion is reversed.

## D. Independent evidence framework

Reuse active effective independent count from V4.5.1. Also report observed effective count separately using its dependency increments; suppressed signals cannot upgrade active confidence. Priority: zero observed → INSUFFICIENT; >=2 observed and exactly one active → DIVERSIFIED_BUT_SUPPRESSED; >=2 observed and active effective >=2 → DIVERSIFIED_EVIDENCE; one observed and effective >=1.5 → CONCENTRATED_MULTI_MODEL; one observed below1.5 → WEAKLY_INDEPENDENT_EVIDENCE; remaining incomplete configurations → INSUFFICIENT. Dominance requires one active family, >=2 included numeric members and a HIGH_DEPENDENCY pair.

## E. GOOG

Evidence origin: user_supplied_approximate_Cloud_model_observations. Production fair: 253.81.

```json
{
  "status": "DIAGNOSTIC_ONLY",
  "active_families": [
    "CASH_FLOW_INTRINSIC",
    "EARNINGS_MULTIPLE"
  ],
  "observed_families": [
    "CASH_FLOW_INTRINSIC",
    "EARNINGS_MULTIPLE"
  ],
  "active_family_count": 2,
  "observed_family_count": 2,
  "independent_family_count": 2,
  "effective_independent_model_count": 2.25,
  "observed_effective_independent_model_count": 2.25,
  "family_suppression_status": "NONE",
  "suppressed_families": [],
  "suppressed_models": [],
  "suppression_materiality": "NOT_APPLICABLE",
  "suppressed_family_materiality": "NOT_APPLICABLE",
  "production_vs_conflict_preserving_difference_pct": null,
  "difference_definition": "(production fair / Strategy C - 1) * 100; Strategy C is the reference denominator; materiality uses absolute value",
  "independent_evidence_status": "DIVERSIFIED_EVIDENCE",
  "correlated_family_dominance": false,
  "production_fair_dependency": "DIVERSIFIED",
  "structural_gaps": [],
  "cross_family_status": "CROSS_FAMILY_DISAGREEMENT",
  "growth_overlap_risk": "MODERATE",
  "capital_structure_flags": [],
  "numeric_stability": "CROSS_FAMILY_CONFLICT",
  "cross_family_conflict_preservation_required": false,
  "hypothetical_guard_action": "REVIEW_ONLY",
  "structural_valuation_readiness": "ACCEPTABLE_WITH_CONFLICT",
  "strategy_c_as_sensitivity_probe": true,
  "strategy_c_description": "conflict-preserving diagnostic reference; not recommended production valuation",
  "scope": "DIAGNOSTIC_GOVERNANCE_ONLY_NO_PRODUCTION_EFFECT"
}
```

## F. MSFT

Evidence origin: user_supplied_approximate_Cloud_model_observations. Production fair: 657.05.

```json
{
  "status": "DIAGNOSTIC_ONLY",
  "active_families": [
    "EARNINGS_MULTIPLE"
  ],
  "observed_families": [
    "CASH_FLOW_INTRINSIC",
    "EARNINGS_MULTIPLE"
  ],
  "active_family_count": 1,
  "observed_family_count": 2,
  "independent_family_count": 2,
  "effective_independent_model_count": 1.25,
  "observed_effective_independent_model_count": 2.25,
  "family_suppression_status": "INDEPENDENT_FAMILY_SUPPRESSED",
  "suppressed_families": [
    "CASH_FLOW_INTRINSIC"
  ],
  "suppressed_models": [
    {
      "model": "normalized_fcf_dcf",
      "family": "CASH_FLOW_INTRINSIC",
      "reason": "outlier_vs_other_models"
    }
  ],
  "suppression_materiality": "HIGH",
  "suppressed_family_materiality": "HIGH",
  "production_vs_conflict_preserving_difference_pct": 32.40632406802349,
  "difference_definition": "(production fair / Strategy C - 1) * 100; Strategy C is the reference denominator; materiality uses absolute value",
  "independent_evidence_status": "DIVERSIFIED_BUT_SUPPRESSED",
  "correlated_family_dominance": true,
  "production_fair_dependency": "SUPPRESSED_CROSS_FAMILY_CONFLICT",
  "structural_gaps": [],
  "cross_family_status": "CROSS_FAMILY_DISAGREEMENT",
  "growth_overlap_risk": "MODERATE",
  "capital_structure_flags": [],
  "numeric_stability": "NUMERICALLY_STABLE_BUT_CONCENTRATED",
  "cross_family_conflict_preservation_required": true,
  "hypothetical_guard_action": "REQUIRE_CROSS_FAMILY_REVIEW",
  "structural_valuation_readiness": "CROSS_FAMILY_CONFLICT_SUPPRESSED",
  "strategy_c_as_sensitivity_probe": true,
  "strategy_c_description": "conflict-preserving diagnostic reference; not recommended production valuation",
  "scope": "DIAGNOSTIC_GOVERNANCE_ONLY_NO_PRODUCTION_EFFECT"
}
```

## G. ORCL

Evidence origin: user_supplied_approximate_Cloud_model_observations. Production fair: 237.75.

```json
{
  "status": "DIAGNOSTIC_ONLY",
  "active_families": [
    "EARNINGS_MULTIPLE"
  ],
  "observed_families": [
    "EARNINGS_MULTIPLE"
  ],
  "active_family_count": 1,
  "observed_family_count": 1,
  "independent_family_count": 1,
  "effective_independent_model_count": 1.25,
  "observed_effective_independent_model_count": 1.25,
  "family_suppression_status": "NONE",
  "suppressed_families": [],
  "suppressed_models": [],
  "suppression_materiality": "NOT_APPLICABLE",
  "suppressed_family_materiality": "NOT_APPLICABLE",
  "production_vs_conflict_preserving_difference_pct": null,
  "difference_definition": "(production fair / Strategy C - 1) * 100; Strategy C is the reference denominator; materiality uses absolute value",
  "independent_evidence_status": "WEAKLY_INDEPENDENT_EVIDENCE",
  "correlated_family_dominance": true,
  "production_fair_dependency": "HIGHLY_CONCENTRATED",
  "structural_gaps": [],
  "cross_family_status": "SINGLE_FAMILY_ONLY",
  "growth_overlap_risk": "MODERATE",
  "capital_structure_flags": [],
  "numeric_stability": "NUMERICALLY_STABLE_BUT_CONCENTRATED",
  "cross_family_conflict_preservation_required": false,
  "hypothetical_guard_action": "REQUIRE_INDEPENDENT_FAMILY_REVIEW",
  "structural_valuation_readiness": "CONCENTRATED",
  "strategy_c_as_sensitivity_probe": true,
  "strategy_c_description": "conflict-preserving diagnostic reference; not recommended production valuation",
  "scope": "DIAGNOSTIC_GOVERNANCE_ONLY_NO_PRODUCTION_EFFECT"
}
```

## H. NVDA

Evidence origin: user_supplied_approximate_Cloud_model_observations. Production fair: 358.45.

```json
{
  "status": "DIAGNOSTIC_ONLY",
  "active_families": [
    "EARNINGS_MULTIPLE"
  ],
  "observed_families": [
    "EARNINGS_MULTIPLE"
  ],
  "active_family_count": 1,
  "observed_family_count": 1,
  "independent_family_count": 1,
  "effective_independent_model_count": 1.25,
  "observed_effective_independent_model_count": 1.25,
  "family_suppression_status": "NONE",
  "suppressed_families": [],
  "suppressed_models": [],
  "suppression_materiality": "NOT_APPLICABLE",
  "suppressed_family_materiality": "NOT_APPLICABLE",
  "production_vs_conflict_preserving_difference_pct": null,
  "difference_definition": "(production fair / Strategy C - 1) * 100; Strategy C is the reference denominator; materiality uses absolute value",
  "independent_evidence_status": "WEAKLY_INDEPENDENT_EVIDENCE",
  "correlated_family_dominance": true,
  "production_fair_dependency": "HIGHLY_CONCENTRATED",
  "structural_gaps": [],
  "cross_family_status": "SINGLE_FAMILY_ONLY",
  "growth_overlap_risk": "MODERATE",
  "capital_structure_flags": [],
  "numeric_stability": "NUMERICALLY_STABLE_BUT_CONCENTRATED",
  "cross_family_conflict_preservation_required": false,
  "hypothetical_guard_action": "REQUIRE_INDEPENDENT_FAMILY_REVIEW",
  "structural_valuation_readiness": "CONCENTRATED",
  "strategy_c_as_sensitivity_probe": true,
  "strategy_c_description": "conflict-preserving diagnostic reference; not recommended production valuation",
  "scope": "DIAGNOSTIC_GOVERNANCE_ONLY_NO_PRODUCTION_EFFECT"
}
```

## I. AMZN

Evidence origin: user_supplied_approximate_Cloud_model_observations. Production fair: 290.44.

```json
{
  "status": "DIAGNOSTIC_ONLY",
  "active_families": [
    "EARNINGS_MULTIPLE"
  ],
  "observed_families": [
    "EARNINGS_MULTIPLE"
  ],
  "active_family_count": 1,
  "observed_family_count": 1,
  "independent_family_count": 1,
  "effective_independent_model_count": 1.25,
  "observed_effective_independent_model_count": 1.25,
  "family_suppression_status": "NONE",
  "suppressed_families": [],
  "suppressed_models": [],
  "suppression_materiality": "NOT_APPLICABLE",
  "suppressed_family_materiality": "NOT_APPLICABLE",
  "production_vs_conflict_preserving_difference_pct": null,
  "difference_definition": "(production fair / Strategy C - 1) * 100; Strategy C is the reference denominator; materiality uses absolute value",
  "independent_evidence_status": "WEAKLY_INDEPENDENT_EVIDENCE",
  "correlated_family_dominance": true,
  "production_fair_dependency": "HIGHLY_CONCENTRATED",
  "structural_gaps": [
    "CAPEX_DISTORTION_REMOVES_INDEPENDENT_CASH_FLOW_CONFIRMATION"
  ],
  "cross_family_status": "SINGLE_FAMILY_ONLY",
  "growth_overlap_risk": "MODERATE",
  "capital_structure_flags": [],
  "numeric_stability": "NUMERICALLY_STABLE_BUT_CONCENTRATED",
  "cross_family_conflict_preservation_required": false,
  "hypothetical_guard_action": "REQUIRE_INDEPENDENT_FAMILY_REVIEW",
  "structural_valuation_readiness": "CONCENTRATED_WITH_STRUCTURAL_GAP",
  "strategy_c_as_sensitivity_probe": true,
  "strategy_c_description": "conflict-preserving diagnostic reference; not recommended production valuation",
  "scope": "DIAGNOSTIC_GOVERNANCE_ONLY_NO_PRODUCTION_EFFECT"
}
```

## J. Structural gaps

Capital structure gap requires the existing CAPITAL_STRUCTURE_NOT_REPRESENTED_IN_ACTIVE_MODELS flag (verified positive net debt and earnings-only active evidence). Forecast-growth gap requires actual HIGH growth_overlap_risk and no observed cashflow family. CapEx gap requires exact capex_or_fcf_distortion reason and no observed cashflow family. No ticker mapping. Default ORCL capital inputs and NVDA EPS ratio are missing: their expected additional gaps cannot be asserted. AMZN CapEx gap is directly supported by its observed applicability reason.

## K. Suppression materiality

Only independent-family suppression enables this metric: signed difference = (production fair / Strategy C − 1) ×100, using the diagnostic reference as denominator. This differs explicitly from V4.5.2 strategy sensitivity, which uses production as denominator. Absolute difference <=10% LOW, (10%,25%] MODERATE, >25% HIGH. Missing Strategy C → UNAVAILABLE; no suppression → NOT_APPLICABLE. Strategy C is a conflict-preserving diagnostic reference, not recommended production valuation. A/B/C remain intact. No benchmark is an input.

## L. Production readiness matrix

| Ticker | Active / observed | Suppression | Materiality | Dependency | Readiness | Hypothetical action |
| --- | --- | --- | --- | --- | --- | --- |
| GOOG | 2 / 2 | NONE | NOT_APPLICABLE | DIVERSIFIED | ACCEPTABLE_WITH_CONFLICT | REVIEW_ONLY |
| MSFT | 1 / 2 | INDEPENDENT_FAMILY_SUPPRESSED | HIGH | SUPPRESSED_CROSS_FAMILY_CONFLICT | CROSS_FAMILY_CONFLICT_SUPPRESSED | REQUIRE_CROSS_FAMILY_REVIEW |
| ORCL | 1 / 1 | NONE | NOT_APPLICABLE | HIGHLY_CONCENTRATED | CONCENTRATED | REQUIRE_INDEPENDENT_FAMILY_REVIEW |
| NVDA | 1 / 1 | NONE | NOT_APPLICABLE | HIGHLY_CONCENTRATED | CONCENTRATED | REQUIRE_INDEPENDENT_FAMILY_REVIEW |
| AMZN | 1 / 1 | NONE | NOT_APPLICABLE | HIGHLY_CONCENTRATED | CONCENTRATED_WITH_STRUCTURAL_GAP | REQUIRE_INDEPENDENT_FAMILY_REVIEW |

Readiness priority: suppressed observed cross-family disagreement → CROSS_FAMILY_CONFLICT_SUPPRESSED; >=2 active conflicting families → ACCEPTABLE_WITH_CONFLICT; diversified sufficient active evidence → ROBUST; otherwise gaps → CONCENTRATED_WITH_STRUCTURAL_GAP, else CONCENTRATED. Zero observed evidence has null readiness/dependency rather than a fabricated positive classification. Preservation required is independent suppression + >=2 observed + existing CROSS_FAMILY_DISAGREEMENT. Dependency SUPPRESSED_CROSS_FAMILY_CONFLICT additionally requires HIGH materiality.

## M. Recommendation for V4.6

- Consider reliability-only cross-family conflict governance after eligible Cloud validation; do not change fair.
- Evaluate an independent-family minimum for precise confidence and correlation-aware evidence counts in a sandbox.
- Investigate a capital-structure-aware earnings overlay using verified debt/cash inputs.
- Research a separate CapEx-normalized owner earnings model with documented normalization.

Worth investigating production governance only after exact eligible Cloud captures confirm these signals. None activated. Admin export includes these fields under independent_evidence_governance and retains V4.5.2 A/B/C. Existing access and read-only storage boundaries are reused.
