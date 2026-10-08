# V4.6 Production Reliability Governance

## A. Executive summary

Default report reuses approximate prior Cloud model observations, not a new Cloud execution. No missing capital/EPS/reliability values are invented.
Production analysis_service applies the policy after unchanged valuation, MOS and buy-zone construction, before result assembly and snapshot persistence. valuation_engine model execution/blend math stays unchanged. Reuse V4.5.3 independent_evidence_audit; no second family mapping or benchmark-based rule.

## B. Governance severity rules

Highest matching severity wins: suppressed conflict + HIGH materiality → CRITICAL; suppressed conflict + MODERATE → HIGH; other suppressed conflicts, unsuppressed cross-family disagreement, structural gaps or single-active-family HIGH growth overlap → MODERATE; single active family → LOW; otherwise NONE. Ticker names and external references are never policy inputs.

## C. Reliability penalty rules

NONE/LOW/MODERATE/HIGH/CRITICAL primary deltas = 0/−5/−10/−15/−20, defined centrally. At most one secondary −5: single-family HIGH growth overlap first, otherwise structural gap when below CRITICAL. If the primary already charges that same driver, suppress the secondary. Total structural cap −25. Existing penalty list is retained unchanged; structural_reliability_penalties is separate. Apply after existing score; clamp 0–100. Missing original score remains null.

## D. Confidence ceiling rules

NONE/LOW/MODERATE/HIGH/CRITICAL severity ceilings = NONE/HIGH/MEDIUM/MEDIUM/LOW. Recheck unchanged score thresholds 85 and65, and take the minimum of existing confidence, governed-score confidence and structural ceiling. Never upgrade LOW or UNAVAILABLE. Original model version is preserved; reliability_governance_version is independently v4.6.

## E. Precise-exit blocking rules

HIGH/CRITICAL always block. MODERATE blocks for single active family, significant cross-family disagreement or nonempty gaps. LOW/NONE add no block. Re-evaluate existing exit reliability with governed score/confidence and retain original eligibility as an AND gate. The existing exit display guard nulls precise prices when blocked; it never unlocks a previously blocked profile. MOS and buy-zone formulas/ranges remain unchanged.

## F. Double-count protection

One primary + at most one distinct secondary. A structural gap used as primary cannot charge again as secondary. A forecast-only gap cannot be secondary to the same high-growth primary. HIGH/VERY HIGH dispersion plus cross-family disagreement sets overlap_detected and documents suppression of a repeated conflict secondary. A primary structural conflict penalty remains intentional and separate. All rejected secondary codes/reasons are exported in penalty_overlap_guard.

## G. GOOG expected result

Evidence: user_supplied_approximate_Cloud_model_observations. Fair before/after: 253.81 / 253.81.

Severity MODERATE; primary -10; secondary 0; total -10; confidence ceiling MEDIUM; structural exit block True.

Confirmed gaps: []; warnings: ['CROSS_FAMILY_DISAGREEMENT'].

## H. MSFT expected result

Evidence: user_supplied_approximate_Cloud_model_observations. Fair before/after: 657.05 / 657.05.

Severity CRITICAL; primary -20; secondary 0; total -20; confidence ceiling LOW; structural exit block True.

Confirmed gaps: []; warnings: ['STRUCTURAL_EVIDENCE_CONCENTRATION', 'CROSS_FAMILY_DISAGREEMENT', 'INDEPENDENT_FAMILY_SUPPRESSED', 'HIGH_MATERIALITY_FAMILY_CONFLICT'].

## I. ORCL expected result

Evidence: user_supplied_approximate_Cloud_model_observations. Fair before/after: 237.75 / 237.75.

Severity LOW; primary -5; secondary 0; total -5; confidence ceiling HIGH; structural exit block False.

Confirmed gaps: []; warnings: ['STRUCTURAL_EVIDENCE_CONCENTRATION'].

## J. NVDA expected result

Evidence: user_supplied_approximate_Cloud_model_observations. Fair before/after: 358.45 / 358.45.

Severity LOW; primary -5; secondary 0; total -5; confidence ceiling HIGH; structural exit block False.

Confirmed gaps: []; warnings: ['STRUCTURAL_EVIDENCE_CONCENTRATION'].

## K. AMZN expected result

Evidence: user_supplied_approximate_Cloud_model_observations. Fair before/after: 290.44 / 290.44.

Severity MODERATE; primary -10; secondary 0; total -10; confidence ceiling MEDIUM; structural exit block True.

Confirmed gaps: ['CAPEX_DISTORTION_REMOVES_INDEPENDENT_CASH_FLOW_CONFIRMATION']; warnings: ['STRUCTURAL_EVIDENCE_CONCENTRATION', 'INDEPENDENT_CASH_FLOW_CONFIRMATION_MISSING'].

ORCL MODERATE requires verified capital-structure gap. NVDA MODERATE plus growth secondary requires actual HIGH growth overlap and a confirmed gap. Default observations lack those inputs, so LOW concentration may be all that can be established. Cloud input evidence decides; none is hardcoded.

## L. Production invariants

Automated before/after tests cover all14 fixed financial fixtures: fair, range, production model outputs, weights, included/excluded models, outlier decisions, MOS and buy zones unchanged. Peer diagnostic isolation remains tested. Pre-V4.6 regression hashes run with the post-valuation policy disabled only in that historical test; new governance tests independently prove every immutable valuation field remains identical with the policy enabled. Admin audit exports explicit invariants and before/after reliability/confidence/precise-exit state.

## M. Snapshot compatibility

raw JSON and reliability_json save structural governance/version; existing snapshots get null governance. Last Reliable stores the governed blend and restores it verbatim, including historical exit state and calculated_at. No fallback eligibility,24h freshness, currency/split/share safety rules change. Input fingerprints remain based solely on existing financial inputs/context; governance metadata does not enter the fingerprint. Cached/live structures remain separate. Diagnostic capture uses the existing no-write resolver and does not update Last Reliable.

## N. Cloud validation instructions

As ADMIN_EMAIL in Cloud, open V4.5 估值结构导出 and click V4.6 Reliability Governance Audit. It captures GOOG/MSFT/ORCL/NVDA/AMZN serially in the existing read-only batch. Download v46_cloud_reliability_governance.json. Verify fair_unchanged and all invariants are true; inspect real before/after scores, ceilings and exit blocks. Cached entries are labeled source_status; their saved historical policy is shown rather than recomputed from current missing inputs. No credentials in exports. Local Streamlit widget tests verify access revocation and downloads; actual Cloud validation remains pending deployment.

## O. V4.7 recommendation

After eligible real Cloud audits: prioritize independent-family minimum for HIGH confidence and confirmed capital-structure gaps; investigate capital-structure-aware earnings overlays and CapEx-normalized owner earnings where those gaps are evidenced. Family-level or correlation-aware production weighting requires a separate validation phase because it changes fair. Do not prioritize by benchmark closeness. None of these V4.7 changes is implemented.
