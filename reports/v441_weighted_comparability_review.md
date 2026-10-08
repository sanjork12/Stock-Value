# V4.4.1 Peer Comparability Revision

## Scope and sources

Peer remains diagnostic by default and the Cloud admin page explicitly requests
diagnostic mode. No activation, internal formula, normalization, reliability,
MOS, zones, Last Reliable or Auth/RLS changes. Benchmark values are unchanged
and are only used after model calculation. This report uses the user's supplied
Cloud conclusions as before-state evidence. No full Cloud numeric snapshot or
local Finnhub key was available to calculate actual revised market results.

## Formula

For complete growth/margin and positive market caps:

- growth similarity = 1 / (1 + absolute growth difference / 200).
- margin similarity = 1 / (1 + absolute margin difference / 100).
- size similarity = 1 / (1 + absolute ln(target cap / peer cap) / 10).
- business score = 1 for the same business family; 0.85 for the existing
  explicitly allowed cross-family software comparison. Unrelated families
  still fail the existing hard gate.
- weight = product of all four scores. Growth and margin units are percentage
  points, cap units cancel in the ratio. Fixed smooth scales are implementation
  choices, not fitted to five-stock prices or benchmarks.

Missing growth/margin does not receive an imputed score. Weight below 0.25
is excluded. Existing positive multiple/profitability/class/currency-safe target
conversion and outlier gates remain. Raw final peers must still be at least 3.
Effective count is the sum of weights of retained peers after outlier removal.
Below 2: unavailable; [2,2.5): LOW; at least 2.5: MEDIUM unless dispersion
or heterogeneity warrants LOW. HIGH requires effective count at least 4 and
weighted dispersion below 0.25, with complete candidate data; incomplete
candidate data caps HIGH at MEDIUM.

Weighted quartiles use sorted multiple/weight pairs, cumulative weight midpoint
positions normalized to [0,1], and linear interpolation at 0.25/0.5/0.75.
This is an interpolated weighted quantile convention, not inverse-CDF selection.
Equal weights exactly reproduce the prior unweighted interpolated quartiles.
The weighted median drives diagnostic mid; weighted quartiles drive low/high
through the existing EPS or EV conversion. Unweighted quartiles remain visible.
Dispersion is (weighted Q3 - weighted Q1) / weighted median. No multi-multiple
blend is introduced. All eligible attempts and all successful alternate results
are retained by the diagnostic report, with the first successful multiple primary.

## Eligibility

Policy is explicit in `peer_eligibility_by_class`. Mature growth, enterprise
software and banks are eligible. Semiconductor growth is eligible with weighted
comparability. Digital advertising, high-growth software and cyclical
semiconductors are diagnostic only. Mega-cap tech requires business-model
review; established enterprise/ad groups resolve to their business policy,
consumer devices stay diagnostic only. Specialized and unmapped unsupported
classes are not eligible. Commerce/mixed commerce company-level comparisons,
including AMZN, are NOT_ELIGIBLE regardless of benchmark.

## Five-stock before/after and architecture review

- NVDA — before: only AVGO retained after AMD margin and MRVL growth gates.
  After: those differences reduce weights rather than immediately exclude.
  Effective count and real weighted prices remain unmeasured; REVISE pending
  Cloud validation. A three-company pool remains fragile; no candidates added.
- MSFT — before: ORCL/SAP retained, CRM/NOW/IBM margin exclusions.
  After: margin differences can participate at reduced weight, subject to all
  remaining gates. Effective count and real prices pending Cloud; REVISE.
- GOOG — before: META/TTD retained, PINS margin exclusion, SNAP missing
  multiple. After: PINS can participate at reduced weight; SNAP still fails a
  missing/nonpositive chosen multiple. Availability is not guaranteed; REVISE
  pending Cloud effective-count and alternate results.
- ORCL — before: user reports internal 237.71, Peer mid 225.58. KEEP
  provisionally. Equal-similarity synthetic case exactly retains prior 100
  peer mid and effective count 5. This is a regression check, not a new ORCL
  market estimate. Actual weighted drift/direction versus the old Cloud result
  must be checked with identical captured inputs; no stability claim is made
  without those inputs.
- AMZN — before: user reports Peer about 154 against internal about 290.
  After: NOT_ELIGIBLE, no peer fair value or peer requests. UI explicitly
  displays “Not applicable — heterogeneous business mix”. REJECT the
  company-level commerce comparable architecture; no conclusion about stock.

The Cloud page/JSON/CSV expose eligibility, raw/effective counts, all peer
scores, weighted/unweighted medians, prices, confidence and primary/alternate
multiples. Real revised counts and prices are intentionally not filled from
synthetic fixtures. Capture a new Cloud export to complete market validation.

## Files and validation

Changed peer_comparable.py, peer_diagnostic_admin.py, peer_post_data_audit.py,
scripts/report_peer_comparable.py, tests/test_peer_comparable.py; added
tests/test_peer_weighted_comparability.py and this report. Two old test
expectations intentionally change: AMZN is unavailable and extreme growth is
tested against the weight floor rather than the removed hard threshold.

Full suite: 438 tests, 0 FAIL, 0 ERROR. Streamlit widget verification passes
single/batch runs, downloads and revoked admin access. New tests cover margin
and growth soft weighting, monotonicity, floor exclusion, effective sums and
LOW/unavailable boundaries, weighted quantile math, AMZN no-request behavior,
ORCL equal-weight stability and internal blend isolation. Existing benchmark
isolation and complete internal valuation regression tests remain passing.

Local commit only; no push. Commit hash is returned in the completion message.
