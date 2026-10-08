# V4.4.2 Cross-Multiple Consistency Guard

## Implementation

The guard is an additive report-only function, `cross_multiple_consistency`.
It consumes independently successful recorded attempts (Status VALID with
positive finite mid), canonical method deduplication, the unchanged primary
confidence and primary effective count. It does not read benchmarks, internal
valuation or production configuration and does not activate Peer in the blend.
An ineligible business returns NOT_APPLICABLE without examining methods.

Collected method fields: multiple, low/mid/high, confidence, raw peer count,
effective peer count and weighted dispersion. The first successful primary
and its prices/confidence remain unchanged; alternate methods are not blended.

## Math and explicit constants

Cross-multiple spread percent = (max(mid) - min(mid)) / median(mid) * 100.
Maximum pairwise percent difference = max(|a-b| / ((a+b)/2) * 100).
The second formula is symmetric and uses each pair's mean as its denominator.

- No valid methods: UNAVAILABLE, null statistics.
- One valid method: SINGLE_METHOD_ONLY, zero spread/pairwise difference.
- Two or more: <=20% CONSISTENT; (20%,40%] MODERATE_DISAGREEMENT;
  >40% MULTIPLE_DISAGREEMENT.
- Explicit constants live in peer_consistency.py: CONSISTENT_SPREAD_PCT=20,
  MODERATE_SPREAD_PCT=40, REVIEW_MIN_EFFECTIVE_PEERS=2.5.

REVIEW_ELIGIBLE requires CONSISTENT, a valid primary with confidence MEDIUM
or HIGH, and primary effective count >=2.5. Otherwise DIAGNOSTIC_ONLY.
This is a future governance marker, never permission to enter a blend.
Admin transport/data failures cannot retain REVIEW_ELIGIBLE.

## Observed Cloud evidence replay

These calculations replay the approximate method mids supplied by the user;
they are not a fresh Cloud API run. Full intervals, effective counts and method
dispersions were not supplied and are not fabricated in this report.

- ORCL: PE 225.76, EV/EBITDA 198.13, EV/Revenue 92.29. Three valid methods;
  minimum 92.29, median 198.13, maximum 225.76. Spread 67.3649%; maximum
  pairwise difference 83.9302%. MULTIPLE_DISAGREEMENT / DIAGNOSTIC_ONLY.
  Primary PE remains 225.76. Governance review: KEEP_WITH_GUARD (keep the
  diagnostic architecture with mandatory disagreement disclosure, not approval
  for production use).
- MSFT: PE 406.43, EV/Revenue 257.01; unavailable EV/EBITDA is not counted.
  Two valid methods; minimum 257.01, median 331.72, maximum 406.43. Spread
  and maximum pairwise difference both 45.0440%. MULTIPLE_DISAGREEMENT /
  DIAGNOSTIC_ONLY. Primary PE remains 406.43. Governance: DIAGNOSTIC_ONLY.
- NVDA: user confirms all methods fail effective count <2. No valid method;
  UNAVAILABLE / DIAGNOSTIC_ONLY, no inferred prices. Governance: REVISE.
- GOOG: user confirms all methods fail effective count <2. UNAVAILABLE /
  DIAGNOSTIC_ONLY. Governance: REVISE.
- AMZN: NOT_ELIGIBLE, NOT_APPLICABLE / DIAGNOSTIC_ONLY. No method-consistency
  evaluation or peer value. Governance: REJECT company-level commerce Peer.

## UI and export

Cloud admin page displays primary method/mid/confidence, all valid method
results, count, min/median/max, spread, pairwise difference, consistency and
production eligibility. JSON includes all fields and method arrays; Cloud CSV
adds scalar governance fields and a JSON-encoded multiple_results column.
External benchmark references are marked POST-HOC ONLY and never enter the
guard, threshold, method choice, weight or result calculation.

## Files and validation

Added peer_consistency.py, tests/test_peer_consistency.py and this report.
Updated peer_post_data_audit.py (record existing dispersion),
scripts/report_peer_comparable.py (attach governance), peer_diagnostic_admin.py
(display/export). No Peer rules or engine/core valuation files were changed.

Full suite: 451 tests PASS, 0 FAIL, 0 ERROR; real Streamlit widget tests pass
single/batch execution, exports and admin access revocation. New tests cover
zero/one/close/moderate/large method sets, threshold equality, NOT_ELIGIBLE,
primary immutability, observed Cloud numeric examples, review confidence/count
gates, invalid/duplicate attempts, benchmark independence and blend isolation.

Local commit hash is supplied in the completion message. No push.
