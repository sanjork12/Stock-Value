# Stock-Value V5.2 — Reporting Basis Resolution Audit

## A. Executive Summary
Added a diagnostic reporting-basis namespace using only already-observed canonical payloads and statements. Values are never substituted. Unsupported periods remain unresolved; competing TTM/FY evidence remains ambiguous. No push performed.

## B. Scope / Non-goals
Reporting metadata, period reconstruction and method-specific basis compatibility only. No business structure research, valuation formula changes, provider calls, fallback/retry changes, persistence or production integration.

Changed files: reporting_basis_resolution.py; provider_metric_semantics.py; financial_forensics_observer.py; production_snapshot_admin.py; scripts/verify_v45_snapshot_ui.py; tests/test_reporting_basis_resolution.py; this Markdown report and companion JSON.

## C. Frozen Baseline
Commit 3ac5355ee4c862575c7dfe750025569bb1f10176. User-reported healthy Cloud batch 8413002d-fde6-444f-8837-9e42f17506fd has five V5.1 scores 67.5 → 67.5, metric basis 0 → 0, business mix 0 → 0. The batch's complete production JSON was not attached. Therefore actual V5.2 company results and scores are pending a new Cloud export, not inferred from the selected values in the request.

## D. Provider Reporting Metadata
Opt-in ContextVar observer captures a numeric/currency/quote-type whitelist from the already-loaded accepted get_info payload. It records raw fiscal/quarter/earnings epochs, parsed ISO dates, maxAge, currencies, quoteType and named financial aggregates. Earnings timestamps and next fiscal year are supporting metadata only, never substitutes for metric periods. mostRecentQuarter confidence is HIGH only when it matches the latest observed balance-sheet date; fiscal metadata alone does not establish a metric basis. Snapshot carries current ticker/batch/acquisition identity. Historical identity stays separate. No entire raw response or credentials are retained.

## E. Flow Metric Resolution
Observe only already-loaded frames, retaining source, frequency, accounting line, period and same-acquisition statement currency. Four latest consecutive, distinct quarterly observations are required for reconstruction. Missing quarters, duplicate periods, missing/mixed currencies, missing/mixed semantics, missing sources and nonconsecutive quarter ends reject reconstruction. Quarter-end gap policy is centralized at 75–105 days. TTM start is provided only when explicitly observed or derivable from an already-loaded fifth consecutive quarter; otherwise start remains unknown with reason.

Match tolerance: <=5% strong, >5–10% moderate, >10% no match. Numeric proximity does not by itself prove FY. A FY selection needs matching fiscal/most-recent-quarter dates or exact direct statement source identity. Explicit same-acquisition TTM/FY metadata with a reporting date is respected. If TTM and FY both match without unique source proof, AMBIGUOUS_TTM_VS_FY remains visible, confidence at most MEDIUM.

## F. EBITDA Basis
Compares unchanged normalized EBITDA to reconstructed TTM and latest FY. Emits full selection trace, reference values, differences, source paths, periods, confidence, reconstruction details and unresolved reasons. No EBITDA inference from fair values or enterprise multiples.

## G. Revenue Basis
Uses the same disciplined flow resolution for totalRevenue. Field naming and generic Yahoo conventions never establish TTM. Current above FY can remain unspecified when quarterly evidence is absent.

## H. Cash Basis
Compares unchanged production cash against latest observed balance-sheet value/date and preserves raw provider totalCash separately. Cash Cash Equivalents And Short Term Investments is broadly compatible with totalCash; Cash And Cash Equivalents alone is not assumed equivalent. <=5% plus compatible semantics and currency permits CURRENT_PROVIDER_CROSSVALIDATED_TO_LATEST_BS, MEDIUM confidence. It records a reference date without pretending that date is the provider current value's reporting date. Exact direct source identity can establish LATEST_BALANCE_SHEET. Conflicting references remain unresolved.

## I. Debt Basis
Same principle using Total Debt semantics. Differences >15% use the existing conservative stock crosscheck scale and remain MATERIAL_VALUE_DIFFERENCE. Lease/interim/business explanations are not invented. No value replacement and no date inference from large differences.

## J. Shares Basis
Explicit source semantics distinguish current market-implied, provider shares, balance-sheet shares and FY diluted average. Known acquisition timestamp for current shares is tagged ACQUISITION_TIME_MARKET_SNAPSHOT, never a reporting period. Current count vs annual diluted average is EXPECTED_DIFFERENT_BASIS; numerical reference comparison remains visible and does not establish equivalence.

## K. Enterprise Bridge Semantics
EV/EBITDA and EV/Revenue are independently assessed. A resolved flow, compatible dated cash/debt reference, known shares semantics, safe currencies and no fatal semantic conflict are minimum closure conditions. TTM plus latest balance-sheet stocks plus current shares can be MIXED_BUT_STANDARD. A resolved revenue flow does not automatically resolve EBITDA. Crossvalidated current stocks normally yield MOSTLY_COMPATIBLE rather than pretending all dates are proven.

## L. Timing Compatibility
Imports V5.1 timing policy unchanged: <=120 GOOD, 121–270 ACCEPTABLE, 271–550 STALE_RISK, >550 INCOMPATIBLE. Method gaps include resolved flow date, stock reference dates and shares basis timestamp. Share snapshot gaps are exported separately with market-vs-reporting semantics. Missing dates produce UNKNOWN. Crossvalidated reference-date usage is explicitly caveated. Currency and cash-line semantic conflicts prevent compatibility.

## M. GOOG
User-reported baseline 67.5 → 67.5. Current-vs-FY revenue/EBITDA and large cash/debt differences in the request are investigative leads only. Missing actual provider fiscal metadata and same-batch observations prevent a new exact conclusion. No presumed interim date or TTM classification.

## N. MSFT
Baseline 67.5 → 67.5. Close FY revenue can resolve only when contemporaneous fiscal metadata or direct statement identity supports it. New Cloud result pending.

## O. ORCL
Baseline 67.5 → 67.5. Near-FY EBITDA/revenue alone remains insufficient; no forced TTM. New Cloud result pending.

## P. NVDA
Baseline 67.5 → 67.5. Above-FY flow values cannot prove TTM without quarterly reconstruction or explicit metric metadata. New Cloud result pending.

## Q. AMZN
Baseline 67.5 → 67.5. Same conservative treatment; no ticker-based reporting classification. New Cloud result pending.

## R. Coverage Before/After
Starts with actual saved V5.1 coverage. Only the 10-point Metric Basis component can change. Central policy: 10 for both methods compatible/mostly compatible, 5 for partial closure, 0 for insufficient evidence. Existing supported component is not erased. No hardcoded final 67.5/77.5 score in runtime. Business Mix component stays unchanged. Coverage can increase while suitability/candidate stays unchanged.

## S. V4.9 Before/After
Before is the saved V5.1 v49_after. After reuses existing suitability_audit/method_audit code through private FunctionType globals, injecting the corresponding method-specific basis at its existing accounting-basis gate. Generic aggregate basis is omitted from that private evaluation so one unresolved method cannot block the other. No edits to V4.9 source, weights or thresholds. Adapter exports ebitda_metric_basis, revenue_metric_basis, ev_ebitda_basis_compatible, ev_revenue_basis_compatible and enterprise_bridge_timing. Mixed/unresolved compatibility is not converted into True. Existing candidate NO ceilings are retained, and readiness remains DIAGNOSTIC_ONLY. Component-level deltas are exported.

## T. Unresolved Basis Gaps
Existing production loading currently observes annual statements; it does not pre-load quarterly statements. Availability for all four requested quarterly paths is explicitly audited as observed/not already available. No property access is introduced to fetch them. A future independently authorized ingestion task may address this gap. Unknown period, semantic mismatch, duplicated reference, missing currency/date and TTM/FY ambiguity are visible.

## U. Production Invariants
Only new snapshots and diagnostic namespaces are appended. Same batch/acquisition IDs and unchanged normalized inputs, production blend, V5.0 objects and V5.1 closure are tested. New batch removes prior diagnostic state; admin revocation removes all downloads. No Supabase writes, provider calls, current-fundamental refetch, valuation rerun, provider resilience edits or Last Reliable mutations. Companion JSON verifies frozen source hashes, including V4.8.2.2 and V5.1. Telemetry counts added_provider_calls=0, added_logical_calls=0, in-memory statement rows and metadata reads.

Tests: 60 new unit tests; 1048 total PASS, 0 FAIL, 0 ERROR; real Streamlit widget checks include same-batch V5.2, unchanged previous results, 11 downloads and access revocation. Exact final totals are recorded in companion JSON.

Cloud acceptance: deploy separately; run one new five-stock production snapshot; confirm ELIGIBLE; run V5.0, V5.1 then V5.2; download v52_reporting_basis_resolution.json/CSV; verify identities, zero added calls, metadata dates, quarterly availability, method-specific compatibility, coverage/V4.9 deltas and production invariants. Local fixture outputs are not Cloud evidence. Ineligible inputs may show diagnostic structure but cannot generate formal calibration conclusions.

## V. V5.3 Recommendation
Governed Segment / Business Structure Evidence, diagnostic-only. Research operating segments, revenues, margin dispersion, economic models and reviewed metadata separately. Do not implement or integrate that work here.

Implementation commit: `git log -1 -- reports/v52_reporting_basis_resolution.md`. The report is committed with the code; embedding its own eventual commit hash would change that hash.
