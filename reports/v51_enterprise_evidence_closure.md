# Stock-Value V5.1 — Enterprise Evidence Closure

## A. Executive Summary
Implemented a separate diagnostic namespace for metric identity, stock/flow timing and governed business structure. No valuation implementation is added. Production and V5.0 results are retained unchanged. No push.

## B. Scope
Only evidence, metadata and provenance. New modules: enterprise_evidence_closure.py and enterprise_evidence_closure_policy.py. Existing financial_forensics_observer.py forwards already-loaded statement observations. production_snapshot_admin.py captures and renders V5.1. Tests and scripts/verify_v45_snapshot_ui.py verify pure closure and real Streamlit interactions.

## C. Frozen Baseline
Commit ac5206a23488b6f7a5025d6fbef42d4512c7ee18. User-reported healthy Cloud batch da36c6d6-8401-426b-abb4-dd1bf5b53040, five reported coverage scores 67.5. No raw JSON for that batch was provided; this report does not invent new company results. The companion JSON records baseline/current source hashes for 12 frozen files.

## D. Metric Basis Architecture
Five current normalized values retain their production_input_value. Closure adds source/type, metric_basis, reporting_period, reporting_as_of, retrieved_at, currency, confidence, derivation and reference fields. Current batch/acquisition IDs are preserved. Historical observation ID is separate. Observer is opt-in and cannot perform I/O. Existing annual income and balance sheets are observed only when the existing loader loads them. Cached fundamentals without statement observation remain explicitly incomplete.

## E. EBITDA Basis
Explicit TTM/FY metadata takes precedence. Exact statement source identity can establish statement basis/date. Numerical proximity within 5% to latest FY only produces CURRENT_PROVIDER_VALUE_NEAR_LATEST_FY, never FY. Otherwise PROVIDER_CURRENT_UNSPECIFIED remains. Retrieval time never supplies reporting dates. V5.0 historical series can supply a reference, not replace current EBITDA.

## F. Revenue Basis
Same discipline as EBITDA. totalRevenue field naming alone does not prove TTM. Different flow periods are NOT_COMPARABLE numerically, even when values match.

## G. Cash/Debt Basis
Observe latest balance sheet direct cash/debt aliases, retain reference value/date/semantics and current value. Current quote matching within 5% is explicitly crossvalidated; it does not acquire the statement date. Exact direct source identity is required to adopt LATEST_BALANCE_SHEET metadata. Mismatches never replace production values. Existing missing-assumed-zero remains zero in production_input_value and unknown for evidence.

## H. Share Basis
Source semantics distinguish market-implied current count, provider current shares, FY diluted average and unknown. No average/current equivalence. Reference semantics and share basis/as-of remain explicit.

## I. Enterprise Bridge Timing
Flow plus latest stock is MIXED_BUT_STANDARD when semantic evidence supports it. Currency mismatch is incompatible; leverage/growth do not determine basis. Central gap bands: <=120 GOOD, 121–270 ACCEPTABLE, 271–550 STALE_RISK, >550 INCOMPATIBLE. All five comparable dates are required for a numeric gap; missing dates remain UNKNOWN. Oldest reporting age is separately retained and stale dates flagged. Final compatibility also checks values, explicit bases and currency. Mixed/incomplete dates do not become supported compatibility in the V4.9 adapter. Near-FY flows plus crossvalidated latest balance-sheet references can receive MIXED_BASIS partial evidence and MOSTLY_COMPATIBLE semantic assessment with an explicit caveat; production reporting dates remain unknown and no formal compatibility boolean is emitted.

Crosscheck tolerances: <=5% CONSISTENT, <=15% MOSTLY_CONSISTENT, >15% MATERIAL_DIFFERENCE, only after semantic/currency/period comparability. Reference periods are displayed independently.

## J. Business Structure Evidence
Reads existing operating_segments, normalized operating_segments, structural_segments and governed_business_structure_metadata. No ticker, company-name, market-price, benchmark or fair-value inference. No populated curated company claims were added without source review.

## K. Segment Evidence
OPERATING_SEGMENT is distinguished from GEOGRAPHIC_SEGMENT, PRODUCT_CATEGORY, REPORTING_UNIT and UNKNOWN_SEGMENT_TYPE. Nonoperating types are excluded with reason. >=10% remains the V5.0 materiality rule. Complete shares, explicit source/period, economic models, and multi-segment margin/growth evidence are required for direct supported classification. Concentration, margin/growth dispersion and economic-model diversity are exported; count alone does not determine complexity. Existing V5.0 dispersion thresholds are reused unchanged. Same-period and total-share consistency are validated.

## L. Curated Metadata Governance
REVIEWED requires ticker, effective date, source type/note, reviewer, confidence, business models, complexity and explicit boolean mix/risk conclusions. Missing governance is PENDING_REVIEW; wrong ticker or conflicting direct evidence is CONFLICTING; old reviewed evidence is STALE. Only REVIEWED + SUPPORTED enters build_v49_business_structure_adapter. Direct complete operating evidence has precedence over reviewed notes, then pending metadata, then unknown. Pending metadata is visible but cannot supply new scoring values.

## M. GOOG
Reported V5.0 coverage 67.5. Actual V5.1 metric basis, timing, mix, coverage and V4.9 result await the new Cloud export. No assumption about Ads/Cloud.

## N. MSFT
Reported coverage 67.5. Actual closure pending Cloud. Office/Azure/Gaming names are not evidence.

## O. ORCL
Reported coverage 67.5. Actual closure pending Cloud. High leverage is independent from stock/flow compatibility.

## P. NVDA
Reported coverage 67.5. Actual closure pending Cloud. High growth does not affect basis classification; operating segment labels need explicit evidence.

## Q. AMZN
Reported coverage 67.5. Actual closure pending Cloud. No commerce/cloud ticker rule. Reviewed heterogeneous evidence may increase coverage while reducing suitability.

## R. Coverage Before/After
Uses actual V5.0 score/components. Only business_mix (15 max) and metric_basis (10 max) can increase. Complete supported compatibility, including a supported negative finding, counts full; explicit mixed basis counts half; insufficient evidence counts zero. Other components stay unchanged. No hardcoded 67.5 or 92.5. Full reviewed business evidence increases completeness, not valuation quality.

## S. V4.9 Before/After
Before is the saved V5.0 v49_after. After is a private copy passed to existing suitability_audit with V5.0 adapter plus supported V5.1 adapters. Weights and thresholds unchanged. Export contains component-level changes and new evidence drivers. Missing identity or unreviewed business evidence blocks YES. Readiness remains DIAGNOSTIC_ONLY and production_integration_performed=false.

## T. Remaining Unknowns
Unspecified provider-current flow periods, missing share as-of, absent statement observations on cached acquisition and missing reviewed operating segments can remain unresolved. No new provider calls or filing ingestion were added. Runtime cannot reliably close absent evidence merely by adding metadata fields.

## U. Production Invariants
Closure deep-copies the batch and appends enterprise_evidence_closure only. No Supabase writes, valuation rerun, cache changes or Last Reliable update. Same normalized inputs, fair/ranges, model outputs/weights/outliers, V4.6/V4.7/V4.8, Peer and Last Reliable are preserved. Companion JSON hashes verify frozen source files. Added calls: zero; statement_reads are in-memory evidence rows, metadata_reads is one local-object inspection per stock, cache_hits is zero added cache access.

## V. V5.2 Recommendation
Keep Enterprise diagnostic-only. After Cloud export, prioritize Segment/SOTP Evidence Research if AMZN/GOOG/MSFT business structure remains unresolved. Class-Specific Governance is conditional on actual coverage >=85 and closing major unknowns. No V5.2 implementation is included.

## Validation and Cloud Acceptance
Local: 41 new unit tests; 956 total PASS, 0 FAIL, 0 ERROR; real Streamlit widget test checks same batch, unchanged production/V5.0 objects, nine downloads and admin revocation. Exact final totals are recorded after final verification in companion JSON.

Cloud procedure: deploy separately, run new five-stock production snapshot, confirm ELIGIBLE, run V5.0, run V5.1, download v51_enterprise_evidence_closure.json/CSV. Check IDs, zero added_provider_calls, explanations for component deltas, unknown/pending status, V4.9 component changes and production invariants. Local tests are not Cloud acceptance evidence.

Implementation commit: retrieve with `git log -1 -- reports/v51_enterprise_evidence_closure.md`. The report is included in that commit; its own hash cannot be embedded without changing that hash.
