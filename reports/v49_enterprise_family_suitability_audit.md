# V4.9 Enterprise Family Applicability & Class-Specific Suitability Audit

## A. Summary and evidence boundary

V4.9 appends an independent `enterprise_family_suitability` diagnostic sidecar after the existing V4.8 experiment. It assesses method applicability, not fair-value accuracy. No production integration is implemented. Baseline: `842c7d2e7bcd6f772553cd7c71a79aac196ba6f6`.

No complete same-batch ELIGIBLE Cloud financial JSON was supplied. The five historical observations below are post-hoc context only. Actual scores, exact economic disagreement causes and production candidates remain pending a fresh eligible Cloud export. Synthetic test results are never presented as Cloud observations.

## B. Frozen boundary and exact wiring

`production_snapshot_admin._run_batch_impl` captures the existing production analysis, runs existing V4.5/V4.6/V4.7/V4.8 diagnostics and the existing batch eligibility guard, then calls `attach_report`. Rendering of a saved batch repairs existing V4.8 wiring first and attaches V4.9 without network requests. The new module only reads captured normalized inputs, profile assumptions and V4.8 results. It deep-copies the report and appends the new namespace plus a diagnostic version marker.

Production valuation modules, acquisition, cache, normalization, profile ranges, blend, outlier decisions, reliability, confidence, precise exit, MOS, zones, Peer and Last Reliable remain unchanged. V4.8 raw model values, confidence, method spread and 50/50 aggregation remain unchanged.

## C. Class policy proposal

The JSON companion contains the full fourteen-class policy matrix and rationale. These are proposal metadata, never production configuration:

- mega_cap_tech: STRONG EBITDA / MODERATE sales / MODERATE company.
- mature_growth: STRONG / WEAK / MODERATE.
- semiconductor_growth: MODERATE / MODERATE / MODERATE; growth/cycle review required.
- cyclical_semiconductor: WEAK / WEAK / WEAK; spot operating data cannot establish normalized cycle quality.
- bank: BLOCKED / BLOCKED / BLOCKED; financial balance-sheet semantics.
- fintech_exchange: MODERATE / WEAK / WEAK; operating versus financial exposure must be evidenced.
- crypto_treasury: BLOCKED throughout; NAV/asset exposure.
- high_growth_software: WEAK / STRONG / MODERATE; transitional EBITDA/SBC and growth review.
- pre_profit_growth: WEAK / MODERATE / WEAK; revenue conditional, nonpositive EBITDA blocked.
- space_optionality and auto_optionality: BLOCKED throughout absent a separately governed policy.
- consumer_platform: MODERATE / WEAK / WEAK; class alone does not prove heterogeneous mix.
- generic_profitable: STRONG / WEAK / MODERATE.
- unsupported_specialized: BLOCKED throughout.

No ticker-specific policy or business-mix inference exists. Unknown classes lack affirmative policy evidence.

## D. Evidence and scoring framework

Each method exposes score, component maxima, direct-input proof, quality, hard blocks, positive/negative evidence, missing evidence and ceilings. Maxima total 100: class 25, inputs 20, economics 20, business mix 15, growth 10, consistency 10. Consistency receives zero method-accuracy points: method agreement belongs to company aggregation only. Consequently the current conservative method score has a reachable maximum of 90.

Score bands are >=85 PREFERRED, >=70 ACCEPTABLE, >=50 CONDITIONAL, >=30 NOT_PREFERRED, otherwise NOT_ELIGIBLE. Hard guards and evidence ceilings override score. Explicit missing evidence is never silently assumed; unknown economics/mix/growth prevent affirmative candidate decisions.

EBITDA economics consider positive EBITDA, explicit economic meaningfulness, stability, historical profitability and margin. Revenue considers positive interpretable operating scale, operating/gross margins and explicit scalability. Revenue receives ceilings for high capital intensity, low margins, material financing burden, pre-profit and cycle concerns. EBITDA receives accounting/SBC/DA, cycle and transitional-margin ceilings.

Explicit structural fields record value and source path. Numeric evidence records margins, CapEx/revenue, CapEx/OCF, net debt/EBITDA and actual growth observations. Unknown stability/accounting/mix remain UNKNOWN. Current EBITDA or revenue is not evidence that the corresponding economic anchor is meaningful.

## E. Hard blocks and data-state guard

Missing/nonpositive operating metric or canonical shares; missing/negative cash/debt; unknown or mismatched currency; missing class range; blocked class; explicit financial balance-sheet semantics; non-operating value anchor; incompatible accounting basis; explicitly meaningless EBITDA/non-operating revenue; and captured nonpositive equity signals block the affected method.

Only both batch and stock ELIGIBLE plus live source and captured V4.8 permit final audit eligibility. Otherwise `audit_status=INELIGIBLE_INPUT_STATE`, no YES, and no final affirmative suitability conclusion. Last Reliable cannot supply inputs, unlock eligibility or boost score. Missing valid captured method results prevent affirmative method candidates.

## F. Aggregation and preferred method

Spread <=20% is CONSISTENT; >20% through 40% MODERATE_DISAGREEMENT; >40% MATERIAL_DISAGREEMENT. Both supported methods and consistent spread can support equal-weight reasonableness. One stronger method yields a conditional single-method recommendation. Moderate spread caps company suitability at CONDITIONAL; material spread prevents equal-weight recommendation and caps at NOT_PREFERRED. Explicit heterogeneity limits company suitability; explicit company-level multiple risk blocks it. Unknown spread/mix does not establish agreement.

Preferred method uses structural suitability and availability, never proximity to production fair. Recommendations do not change actual V4.8 weights.

## G. Growth, mix and disagreement

Observed growth >=25% flags POSSIBLE, >=50% MATERIAL; high-growth classes/transition also require review. Forward/trailing EPS change is recorded as a horizon comparison, not claimed to be a forecast growth rate. Growth mismatch does not automatically block an otherwise calculable method. Stable method agreement cannot remove the growth ceiling.

Mix uses only explicit structural/normalized/profile metadata; no ticker mapping. Driver labels are supported diagnostic hypotheses, not proof of exact causation. Explicit mix/accounting incompatibility, measured capital intensity, growth, margin/range-pair interpretation and leverage are considered. Unexplained disagreement is UNKNOWN. Class range-pair implied margin is a dimensional interpretation, not a second valuation engine.

## H. GOOG

Supplied observation: production 253.81; enterprise 246.75; spread 14.64%. This is internal consistency only. Method economics, growth and explicit mix still require captured evidence. No actual suitability score or candidate is asserted.

## I. MSFT

Supplied observation: production 657.05; enterprise 362.49; spread 55.92%. Material disagreement prevents equal-weight reasonableness. Margin/range-pair, capital intensity and business-mix evidence must explain the discrepancy; exact cause remains pending inputs.

## J. ORCL

Supplied observation: production 237.75; enterprise 83.54; spread 49.22%; historical V4.7 burden VERY_HIGH. Mature-growth policy favours EBITDA structurally over sales, but EBITDA quality and transition/capital intensity must still be established. High leverage alone cannot justify PREFERRED. V4.7 burden score is not a V4.9 scoring input.

## K. NVDA

Supplied observation: production 358.45; enterprise 153.34; spread 18.71%. Low internal spread does not establish suitability. Semiconductor growth policy forces growth/cycle review. Historical approximately -57% earnings-family difference is context only and never a method-score penalty.

## L. AMZN

Supplied observation: production 290.44; enterprise 344.75; spread 43.39%. Company-level equal-weight suitability is unsupported by spread. Heterogeneity must come from explicit metadata, not the ticker or assumptions about segments. If explicit mix evidence is missing it remains UNKNOWN. SOTP/owner earnings are research recommendations only.

## M. Matrices and production candidate semantics

`reports/v49_enterprise_family_suitability_audit.json` contains the fourteen-class matrix, candidate policy and five-stock evidence-pending matrix. Method YES requires supported suitability, valid direct inputs, share provenance and no unresolved required evidence/structural concern. REVIEW requires evidenced conditional suitability. NO includes hard blocks, not-preferred results and missing required evidence. Company YES additionally requires two valid supported methods, consistent spread, explicit simple mix and no growth mismatch. All labels are future recommendations, never inclusion permissions.

## N. Admin UI and exports

Existing ADMIN_EMAIL/cloud/owner controls protect the new section beneath Enterprise-Aware Valuation Experiment. Summary is compact; expanders contain class policy, scores, evidence, hard blocks, driver, eligibility and compact V4.8 raw reference values. No raw-provider dump is added.

Downloads share the same sidecar:
- v49_enterprise_family_suitability_audit.json
- v49_enterprise_family_suitability_audit.csv

An offline read-only helper accepts `--input-json` and `--output-dir`. It never fetches data or writes database snapshots. CSV export guards spreadsheet formula injection. Admin JSON uses existing public financial serialization/redaction. No credentials are read by V4.9.

## O. Risks and production invariants

Explicit semantic metadata is sparse in current production inputs. Conservative UNKNOWN/NO or CONDITIONAL results are expected rather than fabricated certainty. Class proposals and heuristic evidence thresholds require further empirical validation. Internal consistency does not prove accuracy, independence does not prove suitability and leverage does not prove enterprise valuation accuracy.

Invariance tests compare the entire original report after removing only V4.9 additions, captured production/V4.8 payloads and method decisions under changed fair/price/benchmark/Peer/Last Reliable/governance context. Existing production regression tests remain intact. No Supabase write path or new provider acquisition exists.

## P. Validation

65 new tests; complete `python -m unittest discover -s tests -v`: 799 tests, 0 FAIL, 0 ERROR. Real Streamlit widget check: five-stock batch, five downloads, V4.9 sidecar/section, saved-batch rerender without fetch and access revocation PASS. Cloud validation is pending deployment and an ELIGIBLE real batch; no Cloud values were manufactured.

## Q. Recommended V5.0 direction and revision

Keep enterprise methods diagnostic-only until eligible captured evidence supports class-specific method selection. Research single-method/class priorities before weighted-family integration; study growth-normalized operating multiples for rapid growth, segment-aware/SOTP for explicit mixed businesses and owner earnings/CapEx normalization for capital-intensive businesses. Implement none in V4.9.

This report is committed with the implementation. Its exact immutable revision is obtained by `git log -1 --format=%H -- reports/v49_enterprise_family_suitability_audit.md`; the completion response supplies that hash. No push is authorized or performed.
