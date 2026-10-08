# V4.5.2 Family-Level Weighting Experiment

## A. Executive summary

Pure experimental namespace; no production valuation, confidence, reliability, weights, outlier, applicability, fallback, Peer or zones changes. Default report reuses user-provided approximate Cloud mids and source-derived base weights from V4.5.1. It is not a new Cloud capture. Low/high intervals, EPS ratios and capital inputs absent from that evidence remain unknown.

## B. Family aggregation method

Reuse V4.5.1 family mapping and successful model records, including valid pre-outlier numeric models. No inapplicable/invalid-input model is restored. Family mid/low/high are sums of each captured model value times its positive captured base weight divided by the family base-weight sum. Missing intervals remain null. Missing captured base weights abort the experiment rather than invent equal weights. Correlation-adjusted family mid equals family mid; dependency changes evidence strength only.

## C. Strategy A — CURRENT_WEIGHT_AGGREGATED

Family raw weight = sum of base weights of experimentally retained members; normalize across executed families. This reproduces production only when the same candidate set participates. MSFT restores DCF, so A is a restored-candidate control, not a promise to reproduce the production outlier exclusion.

## D. Strategy B — EQUAL_FAMILY

Each retained family receives 1 / family_count, regardless of how many correlated members it has.

## E. Strategy C — EVIDENCE_ADJUSTED

Raw family weight = family base-weight sum × evidence strength × governance modifier. Reuse same-family increments from V4.5.1: first member 1; HIGH additional 0.25, MODERATE 0.50, LOW 0.75. Dependency penalty = 1 − effective/raw count. Strength: effective >=1.75 →1.0; [1.25,1.75) →0.85; <1.25 →0.70. Conflict modifier 0.85 applies uniformly to every family (otherwise 1.0); it cancels on normalized weights and never suppresses minority evidence. No benchmark enters any formula.

## F. GOOG

Evidence: user_supplied_approximate_Cloud_model_observations; weights: current source base weights normalized over user-reported included set; not a captured Cloud weight payload.

Production 253.81; A 253.811; B 234.79583333333335; C 262.4761392405063.

Differences (%): A 0.0003939955084630853, B -7.491496263609254, C 3.414419936372215.

Sensitivity: LOW_SENSITIVITY; governance: CROSS_FAMILY_CONFLICT_REQUIRES_REVIEW.

Families: 2; representatives: {'EARNINGS_MULTIPLE': 329.87166666666667, 'CASH_FLOW_INTRINSIC': 139.72}.

Effective counts: {'EARNINGS_MULTIPLE': 1.25, 'CASH_FLOW_INTRINSIC': 1.0}; evidence strengths: {'EARNINGS_MULTIPLE': 0.85, 'CASH_FLOW_INTRINSIC': 0.7}.

Suppressed family: []; experimentally restored: False. Production exclusion unchanged.

## G. MSFT

Evidence: user_supplied_approximate_Cloud_model_observations; weights: current source base weights normalized over user-reported included set; not a captured Cloud weight payload.

Production 657.05; A 475.5625; B 430.19208333333336; C 496.2376265822785.

Differences (%): A -27.62156609086066, B -34.52673566192323, C -24.47490653949037.

Sensitivity: HIGH_SENSITIVITY; governance: CROSS_FAMILY_CONFLICT_REQUIRES_REVIEW.

Families: 2; representatives: {'EARNINGS_MULTIPLE': 657.0441666666667, 'CASH_FLOW_INTRINSIC': 203.34}.

Effective counts: {'EARNINGS_MULTIPLE': 1.25, 'CASH_FLOW_INTRINSIC': 1.0}; evidence strengths: {'EARNINGS_MULTIPLE': 0.85, 'CASH_FLOW_INTRINSIC': 0.7}.

Suppressed family: ['CASH_FLOW_INTRINSIC']; experimentally restored: True. Production exclusion unchanged.

## H. ORCL

Evidence: user_supplied_approximate_Cloud_model_observations; weights: current source base weights normalized over user-reported included set; not a captured Cloud weight payload.

Production 237.75; A 237.74923076923076; B 237.74923076923076; C 237.74923076923076.

Differences (%): A -0.0003235460648731703, B -0.0003235460648731703, C -0.0003235460648731703.

Sensitivity: LOW_SENSITIVITY; governance: SINGLE_FAMILY_LIMITATION.

Families: 1; representatives: {'EARNINGS_MULTIPLE': 237.74923076923076}.

Effective counts: {'EARNINGS_MULTIPLE': 1.25}; evidence strengths: {'EARNINGS_MULTIPLE': 0.85}.

Suppressed family: []; experimentally restored: False. Production exclusion unchanged.

## I. NVDA

Evidence: user_supplied_approximate_Cloud_model_observations; weights: current source base weights normalized over user-reported included set; not a captured Cloud weight payload.

Production 358.45; A 358.44384615384615; B 358.44384615384615; C 358.44384615384615.

Differences (%): A -0.0017167934590167633, B -0.0017167934590167633, C -0.0017167934590167633.

Sensitivity: LOW_SENSITIVITY; governance: SINGLE_FAMILY_LIMITATION.

Families: 1; representatives: {'EARNINGS_MULTIPLE': 358.44384615384615}.

Effective counts: {'EARNINGS_MULTIPLE': 1.25}; evidence strengths: {'EARNINGS_MULTIPLE': 0.85}.

Suppressed family: []; experimentally restored: False. Production exclusion unchanged.

## J. AMZN

Evidence: user_supplied_approximate_Cloud_model_observations; weights: current source base weights normalized over user-reported included set; not a captured Cloud weight payload.

Production 290.44; A 290.44666666666666; B 290.44666666666666; C 290.44666666666666.

Differences (%): A 0.0022953679474690958, B 0.0022953679474690958, C 0.0022953679474690958.

Sensitivity: LOW_SENSITIVITY; governance: SINGLE_FAMILY_LIMITATION.

Families: 1; representatives: {'EARNINGS_MULTIPLE': 290.44666666666666}.

Effective counts: {'EARNINGS_MULTIPLE': 1.25}; evidence strengths: {'EARNINGS_MULTIPLE': 0.85}.

Suppressed family: []; experimentally restored: False. Production exclusion unchanged.

## K. Sensitivity comparison

| Ticker | Production | A | B | C | Maximum sensitivity |
| --- | ---: | ---: | ---: | ---: | --- |
| GOOG | 253.81 | 253.811 | 234.79583333333335 | 262.4761392405063 | LOW_SENSITIVITY |
| MSFT | 657.05 | 475.5625 | 430.19208333333336 | 496.2376265822785 | HIGH_SENSITIVITY |
| ORCL | 237.75 | 237.74923076923076 | 237.74923076923076 | 237.74923076923076 | LOW_SENSITIVITY |
| NVDA | 358.45 | 358.44384615384615 | 358.44384615384615 | 358.44384615384615 | LOW_SENSITIVITY |
| AMZN | 290.44 | 290.44666666666666 | 290.44666666666666 | 290.44666666666666 | LOW_SENSITIVITY |

Bands use absolute strategy difference versus production: <=10% LOW; (10%,25%] MODERATE; >25% HIGH. Aggregate sensitivity is the maximum absolute difference over A/B/C. GOOG need not be HIGH: observed numbers and formulas decide, not the initial hypothesis. Small single-family differences against rounded supplied fair are rounding, not diversification.

## L. Suppressed-family findings

MSFT cashflow DCF is restored in all three experiments because it was an executable cross-family outlier signal. No production exclusion is reversed. Family conflict flag and conflict_preserving_blend remain explicit. No fake family is created for ORCL/NVDA/AMZN.

## M. Structural recommendations

Conflict => CROSS_FAMILY_CONFLICT_REQUIRES_REVIEW. Single family => SINGLE_FAMILY_LIMITATION. Moderate disagreement or high strategy sensitivity => FAMILY_LEVEL_BLEND_NEEDS_REVIEW. Multiple-family moderate sensitivity without conflict => FAMILY_LEVEL_BLEND_PROMISING; otherwise NO_ACTION. These are diagnostic recommendations, never production eligibility changes.

Family weighting cannot repair missing capital-structure representation or cashflow applicability. AMZN is numerically stable but concentrated. A HIGH growth-overlap signal on actual NVDA inputs recommends a family confidence cap only; the experiment mid is unchanged. The supplied observations lack the EPS ratio, so that recommendation cannot be asserted from the default report.

## N. V4.5.3 proposal

- Offline family-level versus correlation-adjusted weighting on complete eligible captures; retain production as a frozen control.
- Test a separate family-disagreement reliability penalty in a sandbox, never by silently dropping minority cashflow evidence.
- Evaluate class-specific independent-family minimums without relaxing existing applicability.
- Validate capital-structure-aware earnings overlays for debt-heavy single-family cases.
- Study capex-normalized owner earnings as a distinct model with documented cashflow basis.

No V4.5.3 change was implemented. To recompute from exact Cloud inputs: `python scripts/experiment_family_weighting.py --input-json v45_cloud_production_analysis.json`. Degraded/cached calibration inputs are refused. Full test results and local commit hash are supplied in the completion message. No push.

## POST-HOC ONLY — signed error versus external reference

- GOOG: benchmark 345; errors (%) {'production': -26.43188405797101, 'strategy_A': -26.431594202898545, 'strategy_B': -31.943236714975843, 'strategy_C': -23.919959640432953}.
- MSFT: benchmark 544; errors (%) {'production': 20.781249999999996, 'strategy_A': -12.580422794117652, 'strategy_B': -20.920572916666657, 'strategy_C': -8.779848054728223}.
- ORCL: benchmark 180; errors (%) {'production': 32.08333333333333, 'strategy_A': 32.08290598290597, 'strategy_B': 32.08290598290597, 'strategy_C': 32.08290598290597}.
- NVDA: benchmark 300; errors (%) {'production': 19.48333333333332, 'strategy_A': 19.481282051282058, 'strategy_B': 19.481282051282058, 'strategy_C': 19.481282051282058}.
- AMZN: benchmark 285; errors (%) {'production': 1.908771929824571, 'strategy_A': 1.9111111111111079, 'strategy_B': 1.9111111111111079, 'strategy_C': 1.9111111111111079}.
