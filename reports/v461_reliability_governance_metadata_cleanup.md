# V4.6.1 Reliability Governance Metadata Cleanup

## A. Old semantic issue

V4.6 reused the V4.5 structural governance input status `DIAGNOSTIC_ONLY` even after applying reliability penalties, confidence ceilings and precise-exit restrictions. That label described the source audit but no longer described the applied production governance result.

## B. New status fields

Newly applied production `structural_governance` records contain:

- `status = APPLIED_TO_PRODUCTION_RELIABILITY`
- `governance_scope = RELIABILITY_CONFIDENCE_AND_EXIT`
- `fair_value_effect = NONE`
- `production_effect = RELIABILITY_CONFIDENCE_PRECISE_EXIT`
- `governance_input_source = V4.5_STRUCTURAL_GOVERNANCE`
- `reliability_governance_version = v4.6.1`

The valuation model version remains unchanged. Pure V4.5 diagnostic results retain their existing diagnostic semantics. Metadata is attached at the existing production application point, after governance evaluation; no family or reliability rules change.

The administrator V4.6 audit exports governance_status, governance_scope, fair_value_effect, production_effect and the saved per-stock reliability_governance_version. The batch version identifies the current exporter; cached rows retain their original per-stock version. The administrator UI explains the scope of new live results. Ordinary-user UI is unchanged.

## C. Backward compatibility

Existing snapshots with status DIAGNOSTIC_ONLY remain readable with their original status and policy effects intact. No database migration, rewrite or status-based rejection is introduced. Historical snapshot reconstruction and Last Reliable retain the saved reliability, confidence, exit state, version and calculated_at. Audit projection reads saved metadata and does not recalculate historical policy. Legacy metadata fields absent from a snapshot remain null in the added audit columns.

## D. Production invariants

No severity, primary/secondary penalty, confidence ceiling, exit block, warning, explanation, structural gap, family calculation or reliability/confidence/exit formula changes. Fair, low/mid/high, model outputs/weights, outlier decisions, MOS and buy zones remain unchanged. Peer and Last Reliable rules are untouched.

Fourteen ticker behavioral baselines were frozen from the original V4.6 implementation at commit `678e72c6959578815cb3f2438a1031145768bc62`. Comparison excludes only naming/version metadata and retains all behavioral fields in the internal valuation payload, including reliability, confidence and precise-exit state. Every baseline matches V4.6.1.

## E. Tests

`python -m unittest discover -s tests -v`: 575 tests PASS; 0 FAIL, 0 ERROR.

Coverage includes new status/effects/version, snapshot persistence and unchanged valuation model version, old DIAGNOSTIC_ONLY snapshot loading without mutation, all14 behavioral baselines, new administrator export fields, historical audit metadata/version preservation and Last Reliable historical metadata restoration. Existing Peer, reliability, fallback and valuation tests remain passing.

Streamlit widget validation passes five-stock V4.6 audit execution, downloads, invariant verification and administrator access revocation. Real Cloud validation is pending deployment; no Cloud data or credentials were used for this cleanup.

## F. Commit hash

This report is committed together with the metadata cleanup. The exact local commit hash is included in the completion message and can be resolved with `git log -1 --format=%H -- reports/v461_reliability_governance_metadata_cleanup.md`. No push was performed.
