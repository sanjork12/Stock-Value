# V4.7.1 Capital Structure Consistency Rule Fix

## A. Original rule

V4.7 required both methods to fall more than25% below production. When the earnings representative equals production fair, the burden discount capped at15% cannot satisfy that condition. This made combined conflict unreachable for an earnings-only case such as the supplied ORCL observation. The old condition was not universally unreachable when the representative differs from a multi-family production blend, but still used incompatible method scales.

## B. New materiality bands

Burden absolute difference: <=5% LOW, <=10% MODERATE, >10% HIGH. EV bridge: <=10% LOW, <=25% MODERATE, >25% HIGH. Direction: absolute difference<=2% FLAT, otherwise UP/DOWN. Missing/nonfinite difference: UNAVAILABLE materiality and null direction. Version: v4.7.1. A1e-9 percentage-point tolerance handles floating-point boundary representation without rounding fair values.

## C. Combination rules

Priority: both unavailable → UNAVAILABLE; one unavailable → MATERIAL_CONCERN; both LOW → CONSISTENT; opposite UP/DOWN → MIXED_SIGNAL; HIGH+LOW → MATERIAL_CONCERN; same-direction HIGH+MODERATE/HIGH → CAPITAL_STRUCTURE_CONFLICT; both MODERATE or remaining unconfirmed combinations → MATERIAL_CONCERN.

consistency_status remains; capital_structure_consistency_status aliases it. Stable reasons and method materiality/direction/version are exported in JSON, administrator summary and namespace-prefixed CSV. Ordinary-user UI is unchanged. Governance retains its burden hierarchy; conflict always maps to MATERIAL_CAPITAL_STRUCTURE_CONFLICT. New concern/mixed statuses retain the former moderate-concern MONITOR category where no stronger burden condition applies. No result enters production reliability.

## D. ORCL expected classification

Supplied Cloud observations, not a new Cloud execution: production237.75, burden202.09, EV104.09. Differences approximately−15.00% and−56.22%; HIGH/HIGH, DOWN/DOWN → CAPITAL_STRUCTURE_CONFLICT. Governance remains MATERIAL_CAPITAL_STRUCTURE_CONFLICT. No ticker-specific rule or value is used in the implementation.

## E. Invariants

No production fair/range/reliability, V4.6 governance, burden score/band, discount, burden-overlay fair, EV-bridge fair, class range, applicability, Peer, Last Reliable or snapshot valuation changes.

Six synthetic calculation baselines are frozen from V4.7 commit bb83a593913e8e3bbca2033c7ea193ba5eaa18bf. Every output except the explicitly permitted consistency/materiality/direction/governance fields matches. Cases cover heavy debt, net cash, negative bridge equity, missing class range, unsafe currency and missing interest. Historical V4.7 report artifacts remain unchanged; future offline report generation documents the corrected rules.

## F. Tests

python -m unittest discover -s tests -v:621 tests PASS;0 FAIL,0 ERROR.

New coverage includes materiality boundaries, same/opposite directions, LOW agreement, unavailable methods, FLAT boundary, floating-point precision, supplied ORCL classification, six frozen calculation baselines and production-state immutability. Existing V4.6/V4.6.1, Peer and fallback suites remain passing. Administrator Streamlit five-stock capture, overlay display, downloads and access revocation validation PASS. Actual Cloud validation remains pending deployment.

## G. Commit hash

This report is committed with the fix. The exact local hash is provided in the completion response and resolves with git log -1 --format=%H -- reports/v471_capital_structure_consistency_fix.md. No push performed.
