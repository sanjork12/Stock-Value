# Stock-Value V5.0 — Enterprise Method Evidence Completion & Structural Evidence Layer

## A. Executive Summary

Implemented a diagnostic-only structural evidence layer on the existing production snapshot. It observes already-loaded annual statement numbers, binds them to the current financial acquisition, computes transparent structural evidence and a completeness score, then uses a private V4.9 adapter to expose before/after suitability metadata. It never reruns valuation or introduces Enterprise Multiple into the production blend.

Baseline implementation commit: `ee3f4d9a0d761ae6f8c4d1fccedce804a5f21cd4`. User reports healthy Cloud batch `d5286861-5bc1-4f0f-a019-a5aa17690093`, five stocks ELIGIBLE. The full same-run financial JSON/historical series was not supplied. Actual five-stock V5 coverage and deltas remain pending a fresh Cloud run; no synthetic fixture is presented as a real result.

## B. Scope / Non-goals / Files

New files:
- enterprise_evidence.py: opt-in numeric observation, historical snapshot, statistics, structural evidence, V4.9 adapter, export helpers.
- enterprise_evidence_policy.py: centralized versioned evidence thresholds and coverage weights.
- tests/test_enterprise_evidence.py: evidence, governance, identity, integration and invariance tests.
- scripts/audit_enterprise_evidence.py: offline completion from a captured JSON; no provider access.
- reports/v50_enterprise_evidence_completion.md and .json: this source audit and validation record.

Modified:
- financial_forensics_observer.py: thin opt-in hook to observe the already-loaded frame.
- production_snapshot_admin.py: captures evidence_snapshot during the existing loader invocation; exposes the V5 button, summary, expanders and downloads.
- enterprise_family_suitability.py: minimal adapter plumbing for evidenced growth/capital intensity and V5 explicit instability precedence. No weight/threshold/class policy changes.
- scripts/verify_v45_snapshot_ui.py: same-batch V5 widget, no-fetch, seven downloads and access-revocation checks.

No production valuation, class assignment, PE/DCF, model weight/outlier, reliability/MOS/zones, Proxy/Calibration guard, Peer/Last Reliable, provider acquisition, raw-cache or fallback policy changes. No database migration or write. V4.8 raw enterprise values and 50/50 aggregation remain intact.

## C. Evidence Architecture / Sources / Identity

Existing canonical acquisition -> existing `_load_statement` -> opt-in ContextVar numeric observer -> `evidence_snapshot` -> `build_structural_evidence` -> `build_v49_evidence_adapter` -> private `suitability_audit` -> saved admin session/export.

The observer whitelists actual reported EBITDA, revenue, Operating Income, EBIT, EPS, D&A/unusual lines from annual income statements, and OCF/CapEx/FCF/SBC/D&A from annual cashflows. It never reads unrelated rows, raw provider dictionaries, credentials or exception messages. Observation failure records a safe category without interrupting financial loading. No constructed EBITDA from net income or arbitrary adjustments is supported.

Existing normalized historical margins/EPS/annual cashflows are fallback evidence only. Current normalized financials are never replaced or mutated. Every observation has period, value, source, basis and derivation. Current input references preserve normalized paths, source/type, basis and reporting period where actually available; market price, market cap and fair values are excluded from evidence inputs.

Every stock's evidence carries input_batch_id, fundamentals_acquisition_id and a separate historical_evidence_acquisition_id. A historical ID identifies the observer capture of already-loaded data, not a claim of an extra HTTP request. Legacy normalized-only captures are explicitly labelled. Unknown/divergent identity, cached Last Reliable source or ineligible stock/batch prevents formal completion and candidate YES. New Cloud acceptance requires a fresh production snapshot so the newly observed EBITDA/SBC lines are actually retained.

## D. Evidence Coverage Model

Weights total100: EBITDA15, revenue15, margin history15, capital intensity15, business mix15, accounting10, metric basis10, growth/cycle5. SUPPORTED/UNSUPPORTED findings count as known evidence; PARTIALLY_SUPPORTED receives half credit; INSUFFICIENT/NOT_APPLICABLE zero. Multiple records within a dimension share its weight. Negative findings can improve completeness while lowering suitability.

Bands: >=85 HIGH, >=70 MEDIUM, >=50 LOW, otherwise INSUFFICIENT. Coverage is never a valuation weight, reliability score or fair-value input. COMPLETE/PARTIAL/INSUFFICIENT describe completeness, while separate V5 audit status records input eligibility. All policy values are exported and reproduced in the JSON companion.

## E. EBITDA Meaningfulness

Positive EBITDA alone cannot produce HIGH. HIGH requires >=3 direct annual EBITDA observations with positive recurring operating profitability, stable operating margins, stable EBITDA and low observed D&A materiality. Supported recurring but less conclusive operating economics produce MODERATE. Missing history/current operating economics remains insufficient or partially supported. Nonpositive EBITDA or an inappropriate financial/non-operating class produces NOT_MEANINGFUL. Material D&A lowers meaning/confidence; an unusual EBITDA/revenue relationship is labelled LOW rather than asserted HIGH.

Current EBITDA/revenue and operating margin references are recorded. No EBITDA valuation calculation or company-specific rule is added.

## F. EBITDA Stability

At least3 comparable annual observations are required for a formal stability classification. Statistics include count, mean, median, population standard deviation/CV using abs(mean), min/max, YoY changes, sign changes, trend, CAGR and period warnings.

CV <=.25 STABLE, <=.50 MODERATELY_STABLE, <=1 VOLATILE, >1 HIGHLY_VOLATILE. Nonpositive/sign-changing EBITDA is HIGHLY_VOLATILE. Zero/missing mean yields null CV plus reason, not a fabricated stability result. No equivalent EBITDA is invented when the reported line is absent.

## G. Revenue Interpretability

Requires positive operating revenue and comparable fiscal history. HIGH additionally needs stable margins, explicit homogeneous mix and compatible basis. Cyclical class, material discontinuities, heterogeneity or compressing/transitional margins weaken interpretation. Missing mix or basis is retained as a missing dependency, not silently assumed. Nonpositive/non-operating/financial-class revenue cannot become a sales anchor merely because a numeric multiple exists.

History exposes CAGR, YoY, growth CV, negative-growth frequency and discontinuities. Discontinuities remain in the series; they are not silently filtered. These statistics never replace production Growth/DCF inputs.

## H. Margin Regime

Uses3+ fiscal operating margins; records mean/median/std, slope, spread and latest-versus-median. <=5pp spread is a stable candidate: median>=25% HIGH, <10% LOW, otherwise MODERATE. Wider spread with a slope>=1.5pp/year is EXPANDING, <=-1.5pp/year COMPRESSING; sign transitions are TRANSITIONAL, otherwise VOLATILE. Variation band separately distinguishes <=5pp, 5–10pp, >10pp.

Thresholds are centralized under EVIDENCE_POLICY_VERSION=v5.0. Fiscal-end dates and existing FY labels are not silently combined. TTM/calendar assumptions are not substituted for annual periods.

## I. Capital Intensity / Reinvestment / Scalability

Reports CapEx/revenue, CapEx/OCF, CapEx/EBITDA and FCF/OCF. Aligned fiscal observations take precedence; current mixed-provider-period ratios are explicitly PARTIALLY_SUPPORTED/LOW confidence. Negative reported CapEx is converted to outflow magnitude for ratios only; the original historical value remains visible.

CapEx/revenue bands: <=5/15/30% -> LOW/MODERATE/HIGH, >30% VERY_HIGH. CapEx/OCF uses <=30/70/100%; the greater observed severity governs the label. Trend and coverage are explicit. Missing/invalid denominators yield null plus reason.

Scalability uses revenue growth, operating-margin trend and observed capital-intensity trend. Expansion without an observed stable/decreasing reinvestment trend cannot establish SUPPORTED. Operating-income/revenue CAGR ratio and EBITDA-margin slope are exported as additional measured evidence. No software/cloud/company-name assumption is used.

Net debt/positive EBITDA separately records capital-structure relevance at1/2/3.5x thresholds. This explains framework relevance only, never enterprise fair-value accuracy.

## J. Business Mix / Segment Complexity / Curated Governance

The current acquisition paths expose company totals and statement rows, not a stable structured operating-segment dataset. No new segment endpoint/provider or paid dependency is introduced. No company-specific curated entries are added without a credible source. Absent explicit evidence remains INSUFFICIENT_EVIDENCE/UNKNOWN, including AMZN-like companies.

Existing explicit internal business metadata can be used. Optional complete operating-segment data exposes count, material segments (>=10% revenue), margin/growth dispersion and revenue concentration. Geography alone is never interpreted as business-model heterogeneity. Conflicting simple metadata cannot override observed segment heterogeneity; the conflict is recorded and the more cautious interpretation retained.

Optional curated records must include source_type, source_note, effective_date, as_of, review_status, reviewed and confidence. The governance record is preserved. Unreviewed records may inform diagnostics but cannot unlock candidate YES. No ticker/name lookup determines mix or growth.

## K. SBC / D&A / Accounting Distortion

SBC uses direct observed statement lines and ratios to revenue/EBITDA/OCF. Missing SBC is UNKNOWN. Bands for revenue2/5/10%, EBITDA10/25/50%, OCF10/25/50% are centralized.

D&A prefers direct annual lines. A same-period reported EBITDA minus Operating Income approximation is explicitly DERIVED_APPROXIMATION with LOW confidence and a reconciliation caveat. It is not represented as direct D&A. D&A/revenue <=5% LOW, <=15% MODERATE, >15% HIGH. A negative gap is a basis-review warning. Unaligned current FY/TTM observations are not subtracted unless compatible basis is explicit.

Accounting evidence only uses measured SBC/D&A, unusual items, aligned negative FCF with positive EBITDA, and known basis concerns. Unusual-item magnitude is measured against revenue: >5% is material; smaller observed amounts are moderate concerns. Absence of accounting distortion is not asserted without direct supporting coverage. Unknown is not clean/false.

## L. Enterprise Metric Basis Compatibility

Reports EBITDA/revenue/cash/debt/shares basis, currency, actual reporting as-of, retrieval time and source. Allowed explicit basis labels distinguish TTM, FY, balance-sheet position and current/annual shares. Mixed EBITDA/revenue FY/TTM is MIXED_BASIS. Currency conflict is INCOMPATIBLE; missing currency/basis is UNKNOWN. Reporting gaps >550 days flag MIXED_BASIS. Missing as-of can only support MOSTLY_COMPATIBLE, never full COMPATIBLE.

Existing QUOTE_SUMMARY_TTM_OR_PROVIDER_CURRENT and FY_OR_PROVIDER_STATEMENT_PERIOD labels are deliberately ambiguous and remain UNKNOWN. Retrieval timestamp is never repurposed as financial reporting date. V5 cannot manufacture period certainty from these legacy labels.

## M. Growth / Cyclicality / Operating Value Driver

Growth evidence includes revenue CAGR/recent YoY/current growth, historical EPS CAGR, forward/trailing EPS horizon comparison, margin trajectory and class. NORMAL/ELEVATED/HIGH/TRANSITIONAL/CYCLICAL_REBOUND/DISTORTED/INSUFFICIENT are evidence states. V4.9 adapter retains25% POSSIBLE and50% MATERIAL threshold semantics plus existing high-growth-class/transition review. EPS horizon comparison is explicitly not a forecast CAGR.

Cyclicality adds observed revenue-growth swings, aligned EBITDA-margin swings and EPS/EBITDA sign information. Missing numeric history remains UNKNOWN. Existing class/cyclicality/optionality metadata is consumed but never changed. High optionality prevents automatic operating-driver YES without declaring the operating business worthless. Positive measured operating economics and class/optionality jointly support YES/MOSTLY/PARTIAL/NO/UNKNOWN.

## N. GOOG Evidence Result

User-reported baseline V4.9 company-level CONDITIONAL, candidate NO, readiness DIAGNOSTIC_ONLY. V5 should examine captured EBITDA and 3–5 fiscal margins, CapEx/OCF and revenue history. Business mix remains insufficient unless explicit operating metadata exists. Actual coverage, evidence labels and score deltas are pending the complete Cloud snapshot/new export.

## O. MSFT Evidence Result

User-reported baseline NOT_PREFERRED/NO/DIAGNOSTIC_ONLY. V5 measures historical margin/EBITDA stability and reinvestment intensity. It does not tell an AI/cloud narrative or infer segment economics from brand recognition. Actual coverage and deltas are pending; no claims of confirmed stable margins or current CapEx severity are invented.

## P. ORCL Evidence Result

User-reported baseline NOT_PREFERRED/NO/DIAGNOSTIC_ONLY. V5 measures direct EBITDA stability/meaningfulness, CapEx trend, aligned FCF conversion and normalized net-debt/EBITDA. Historical high leverage does not establish a stable EBITDA anchor. Actual evidence/deltas remain pending.

## Q. NVDA Evidence Result

User-reported baseline NOT_PREFERRED/NO/DIAGNOSTIC_ONLY. V5 measures revenue CAGR/YoY, margin expansion, EBITDA-margin swings and cycle evidence. Low method spread is not structural suitability evidence. Growth classification cannot be set from the ticker. Actual measured regime/coverage/deltas remain pending.

## R. AMZN Evidence Result

User-reported baseline NOT_PREFERRED/NO/DIAGNOSTIC_ONLY. V5 measures CapEx, cash conversion and EBITDA/operating-income relationship. Without explicit operating-segment evidence, mix remains insufficient; AWS/commerce/ads is not inferred from common knowledge. Actual measured evidence/deltas remain pending.

## S. V4.9 Before / After / Delta / UI

`v49_before` preserves current captured suitability metadata. Adapter values enter a private copy of enterprise_structural_metadata; V4.9 runs only its diagnostic suitability computation, not valuation. `v49_after` includes method score/state/components/candidate, company suitability/preferred method/aggregation, readiness and audit status. `v49_evidence_delta` records exact component changes, signed deltas, evidence drivers/provenance, ceiling changes and original production fair equality as reference only.

Weights25/20/20/15/10/10 and thresholds85/70/50/30 are unchanged. Missing evidence is omitted, not mapped to false. MODERATE/LOW evidence is not indiscriminately promoted to true or hard-block false. Explicit V5 instability overrides only the V5 private margin proxy; existing non-V5 V4.9 behavior is preserved. Growth and capital-intensity adapter fields consume richer measurements without changing their threshold semantics.

Administrator-only Enterprise Evidence Completion appears under the existing snapshot workflow. Click “运行 V5.0 Evidence Completion” after a production batch. Summary defaults compact; expanders hold bounded numeric history, derivations/provenance, missing inputs and before/after delta. Downloads:
- v50_enterprise_evidence_completion.json (complete provenance)
- v50_enterprise_evidence_completion.csv (summary)

Existing V4.5 JSON also retains the added session namespaces. No persisted Supabase snapshot is written. The offline script accepts --input-json and --output-dir and never fetches providers.

## T. Remaining Unknown Evidence / Data Discipline

Likely remaining gaps: absent reported annual EBITDA/SBC/unusual-item rows, segment evidence, exact metric as-of/basis and historical reporting semantics not actually present in captured data. These remain explicit missing inputs. Current incomplete data cannot be completed from Last Reliable, benchmarks, market price, analyst target or Peer fair.

Invalid/missing data is never filled with zero. An explicitly upstream-assumed missing cash/debt zero is excluded in an evidence-only view; its original normalized value and exclusion reason remain visible, and production normalization is untouched. Raw and filtered series, excluded observations and reasons are exported. Exclusions are limited to missing/nonfinite/invalid-period, duplicate, inconsistent currency or incompatible annual frequency; numerical outliers are retained and labelled. Non-consecutive fiscal years have no invented one-year growth rate. Formal stability requires >=3 comparable periods.

## U. Production Invariants / Performance / Tests

The JSON companion records hashes and unchanged checks for13 frozen source files against the baseline, including valuation engine/primitives, normalization, Calibration guard, V4.6/V4.7/V4.8, V4.8.2 acquisition, V4.8.2.1 wiring, provider normalization, Streamlit route, Peer and Last Reliable. Production blend, fair/range, inputs, zones and original diagnostic results are unchanged by completion.

88 new tests; full `python -m unittest discover -s tests -v`: 915 tests, 0 FAIL, 0 ERROR. Tests cover evidence correctness, provenance, null discipline, period/currency/basis checks, source conflicts, curated review, benchmark/ticker isolation, positive/negative score changes, unchanged weights/thresholds, same-batch identity, no network/storage writes and immutable production payloads.

Real canonical five-stock test: five factories for the original batch, three reported EBITDA/SBC periods captured per ticker, no additional acquisition on V5 completion. Telemetry distinguishes zero incremental V5 logical/historical calls from existing source acquisition counts/cache hits. Observer reads are not claimed to equal HTTP counts.

Real Streamlit widget test PASS: V5 reuses batch identity and unchanged normalized inputs/production blend, seven downloads after completion, another production run creates a fresh batch, legacy rerender does not fetch, admin revocation removes all downloads. Synthetic fixtures are explicitly test-only.

Cloud acceptance after separately authorized deployment:
1. Run a new five-stock production snapshot; confirm Calibration Batch Status ELIGIBLE and wiring trace consistent.
2. Click V5.0 Evidence Completion without rerunning production fetch.
3. Download V5 JSON; match input_batch_id and fundamentals_acquisition_id to V4.9/current normalized inputs and inspect the historical capture ID.
4. Inspect actual coverage, source periods/rows, missing evidence, before/after score components and signed deltas. A lower score with stronger negative evidence is a valid outcome.
5. Verify original production fair/range/models/zones, raw V4.8 and trace unchanged; inspect zero added provider calls and production_integration_performed=false.
6. Share the same-run JSON to close the five-stock evidence audit. Local tests cannot substitute for these Cloud observations.

## V. V5.1 Recommendation / Commit

Interim recommendation D: keep Enterprise Multiple diagnostic-only. Do not choose class governance, SOTP or growth-normalized production work before actual V5 Cloud evidence is reviewed. Segment research is appropriate only if explicit segment gaps persist; no such next-stage implementation is included.

This report is committed with the implementation. Resolve its immutable revision with `git log -1 --format=%H -- reports/v50_enterprise_evidence_completion.md`; the completion response supplies the exact local hash. Do not push.
