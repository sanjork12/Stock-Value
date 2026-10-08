# V4.5.1 Correlation & Cross-Family Governance Audit

## A. Executive summary

Governance only: no production valuation, weights, outlier, confidence, eligibility or reliability changes. Default report replays user-supplied approximate Cloud model observations, not a new Cloud API run. Exact normalized weights are reconstructed from current source and the supplied included set when a full Cloud export is absent. EPS ratios and debt metrics remain unknown without original inputs.

## B. Model family map

- forward_pe: EARNINGS_MULTIPLE
- growth_adjusted_pe: EARNINGS_MULTIPLE
- normalized_pe: CYCLE_NORMALIZED
- normalized_cycle_earnings: CYCLE_NORMALIZED
- normalized_fcf_dcf: CASH_FLOW_INTRINSIC
- ev_ebitda: ENTERPRISE_MULTIPLE
- revenue_multiple: REVENUE_MULTIPLE
- price_to_book_roe: BOOK_VALUE
- residual_income: BOOK_VALUE
- unsupported: SPECIALIZED

## C. Dependency methodology

Weighted core-driver Jaccard = sum(min(driver weights)) / sum(max(driver weights)). Drivers and weights are explicit in model_family_governance.py and the JSON. Currency/class context is counted in shared declared inputs, not as a core driver. PE pair shares EPS_BASIS(4) and EARNINGS_MULTIPLE_POLICY(2); Growth PE adds SUSTAINABLE_GROWTH(1): score 6/7 = 0.857143, HIGH_DEPENDENCY. Forward PE versus DCF has no shared core driver (score 0, LOW). DCF versus EV/EBITDA shares capital bridge/shares (6/14 = 0.428571, MODERATE). This is a structural descriptor, not Pearson correlation or measured market-price covariance.

Thresholds: >=0.70 HIGH; >=0.40 and <0.70 MODERATE; <0.40 LOW. Recorded model inputs accompany declared dependency sets so missing observations remain visible.

## D. Effective independent evidence methodology

Each active family first model contributes 1.0. Additional same-family models contribute 0.25/0.50/0.75 for HIGH/MODERATE/LOW dependency against the most-overlapping prior family member, in deterministic model-id order. This is a heuristic evidence count, not sample size. Different first families contribute 1.0 each; any cross-family overlaps remain explicit in pair diagnostics. Production model count and weights stay unchanged.

Family concentration sums actual normalized production weights, never reweights them. >=0.75 HIGH; [0.60,0.75) MODERATE; <0.60 DIVERSIFIED. Cross-family representatives are unweighted medians of successful numeric models per family, including later outlier exclusions. Spread = (max−min)/median ×100. Pairwise uses pair mean denominator. <=20% CONSISTENT; (20%,40%] MODERATE; >40% CROSS_FAMILY_DISAGREEMENT.

## E. GOOG result

Classification: CROSS_FAMILY_CONFLICT; review: CROSS_FAMILY_REVIEW_REQUIRED.

Included count 3; effective independent count 2.25; active families ['CASH_FLOW_INTRINSIC', 'EARNINGS_MULTIPLE']; executed families ['CASH_FLOW_INTRINSIC', 'EARNINGS_MULTIPLE'].

Family weights: {'EARNINGS_MULTIPLE': 0.6, 'CASH_FLOW_INTRINSIC': 0.4}. Cross-family status: CROSS_FAMILY_DISAGREEMENT; spread: 80.01717475311293%.

Family representatives: {'EARNINGS_MULTIPLE': {'family_model_count': 2, 'models': ['forward_pe', 'growth_adjusted_pe'], 'family_mid_median': 326.08, 'family_mid_min': 303.33, 'family_mid_max': 348.83}, 'CASH_FLOW_INTRINSIC': {'family_model_count': 1, 'models': ['normalized_fcf_dcf'], 'family_mid_median': 139.72, 'family_mid_min': 139.72, 'family_mid_max': 139.72}}.

Growth overlap: MODERATE; EPS ratio: None; reasons: ['included_earnings_models_share_eps_basis_and_growth_multiple_overlay', 'forward_trailing_eps_ratio_unavailable', 'active_cash_flow_family_provides_separate_structural_evidence'].

Capital structure: {'cash': None, 'debt': None, 'net_debt': None, 'net_debt_to_market_cap': None}; flags: [].

Outlier review: []. Production exclusion remains unchanged.

Summary: CROSS_FAMILY_CONFLICT. Input/weight scope: current source base weights normalized over user-reported included set; not a captured Cloud weight payload.

## F. MSFT result

Classification: CROSS_FAMILY_CONFLICT; review: CROSS_FAMILY_REVIEW_REQUIRED.

Included count 2; effective independent count 1.25; active families ['EARNINGS_MULTIPLE']; executed families ['CASH_FLOW_INTRINSIC', 'EARNINGS_MULTIPLE'].

Family weights: {'EARNINGS_MULTIPLE': 1.0}. Cross-family status: CROSS_FAMILY_DISAGREEMENT; spread: 104.8106124885162%.

Family representatives: {'EARNINGS_MULTIPLE': {'family_model_count': 2, 'models': ['forward_pe', 'growth_adjusted_pe'], 'family_mid_median': 651.125, 'family_mid_min': 615.61, 'family_mid_max': 686.64}, 'CASH_FLOW_INTRINSIC': {'family_model_count': 1, 'models': ['normalized_fcf_dcf'], 'family_mid_median': 203.34, 'family_mid_min': 203.34, 'family_mid_max': 203.34}}.

Growth overlap: MODERATE; EPS ratio: None; reasons: ['included_earnings_models_share_eps_basis_and_growth_multiple_overlay', 'forward_trailing_eps_ratio_unavailable'].

Capital structure: {'cash': None, 'debt': None, 'net_debt': None, 'net_debt_to_market_cap': None}; flags: [].

Outlier review: [{'model': 'normalized_fcf_dcf', 'family': 'CASH_FLOW_INTRINSIC', 'flag': 'CROSS_FAMILY_SIGNAL_SUPPRESSED', 'production_exclusion_remains_unchanged': True, 'exact_production_reason': 'outlier_vs_other_models'}]. Production exclusion remains unchanged.

Summary: NUMERICALLY_STABLE_BUT_CONCENTRATED. Input/weight scope: current source base weights normalized over user-reported included set; not a captured Cloud weight payload.

## G. ORCL result

Classification: SINGLE_FAMILY_ONLY; review: STRUCTURALLY_CONCENTRATED.

Included count 2; effective independent count 1.25; active families ['EARNINGS_MULTIPLE']; executed families ['EARNINGS_MULTIPLE'].

Family weights: {'EARNINGS_MULTIPLE': 1.0}. Cross-family status: SINGLE_FAMILY_ONLY; spread: None%.

Family representatives: {'EARNINGS_MULTIPLE': {'family_model_count': 2, 'models': ['forward_pe', 'growth_adjusted_pe'], 'family_mid_median': 236.48, 'family_mid_min': 230.98, 'family_mid_max': 241.98}}.

Growth overlap: MODERATE; EPS ratio: None; reasons: ['included_earnings_models_share_eps_basis_and_growth_multiple_overlay', 'forward_trailing_eps_ratio_unavailable'].

Capital structure: {'cash': None, 'debt': None, 'net_debt': None, 'net_debt_to_market_cap': None}; flags: [].

Outlier review: []. Production exclusion remains unchanged.

Summary: NUMERICALLY_STABLE_BUT_CONCENTRATED. Input/weight scope: current source base weights normalized over user-reported included set; not a captured Cloud weight payload.

## H. NVDA result

Classification: SINGLE_FAMILY_ONLY; review: STRUCTURALLY_CONCENTRATED.

Included count 2; effective independent count 1.25; active families ['EARNINGS_MULTIPLE']; executed families ['EARNINGS_MULTIPLE'].

Family weights: {'EARNINGS_MULTIPLE': 1.0}. Cross-family status: SINGLE_FAMILY_ONLY; spread: None%.

Family representatives: {'EARNINGS_MULTIPLE': {'family_model_count': 2, 'models': ['forward_pe', 'growth_adjusted_pe'], 'family_mid_median': 356.485, 'family_mid_min': 331.02, 'family_mid_max': 381.95}}.

Growth overlap: MODERATE; EPS ratio: None; reasons: ['included_earnings_models_share_eps_basis_and_growth_multiple_overlay', 'forward_trailing_eps_ratio_unavailable'].

Capital structure: {'cash': None, 'debt': None, 'net_debt': None, 'net_debt_to_market_cap': None}; flags: [].

Outlier review: []. Production exclusion remains unchanged.

Summary: NUMERICALLY_STABLE_BUT_CONCENTRATED. Input/weight scope: current source base weights normalized over user-reported included set; not a captured Cloud weight payload.

## I. AMZN result

Classification: SINGLE_FAMILY_ONLY; review: STRUCTURALLY_CONCENTRATED.

Included count 2; effective independent count 1.25; active families ['EARNINGS_MULTIPLE']; executed families ['EARNINGS_MULTIPLE'].

Family weights: {'EARNINGS_MULTIPLE': 1.0}. Cross-family status: SINGLE_FAMILY_ONLY; spread: None%.

Family representatives: {'EARNINGS_MULTIPLE': {'family_model_count': 2, 'models': ['forward_pe', 'growth_adjusted_pe'], 'family_mid_median': 287.83, 'family_mid_min': 272.13, 'family_mid_max': 303.53}}.

Growth overlap: MODERATE; EPS ratio: None; reasons: ['included_earnings_models_share_eps_basis_and_growth_multiple_overlay', 'forward_trailing_eps_ratio_unavailable'].

Capital structure: {'cash': None, 'debt': None, 'net_debt': None, 'net_debt_to_market_cap': None}; flags: [].

Outlier review: []. Production exclusion remains unchanged.

Summary: NUMERICALLY_STABLE_BUT_CONCENTRATED. Input/weight scope: current source base weights normalized over user-reported included set; not a captured Cloud weight payload.

## J. Cross-family disagreement matrix

| Ticker | Active families | Effective count | Cross-family status | Spread % |
| --- | --- | ---: | --- | ---: |
| GOOG | CASH_FLOW_INTRINSIC, EARNINGS_MULTIPLE | 2.25 | CROSS_FAMILY_DISAGREEMENT | 80.01717475311293 |
| MSFT | EARNINGS_MULTIPLE | 1.25 | CROSS_FAMILY_DISAGREEMENT | 104.8106124885162 |
| ORCL | EARNINGS_MULTIPLE | 1.25 | SINGLE_FAMILY_ONLY | None |
| NVDA | EARNINGS_MULTIPLE | 1.25 | SINGLE_FAMILY_ONLY | None |
| AMZN | EARNINGS_MULTIPLE | 1.25 | SINGLE_FAMILY_ONLY | None |

## K. Growth overlap matrix

Shared active PE pair alone => MODERATE. Forward/trailing ratio >1.5 plus active HIGH_DEPENDENCY PE pair with the same actual forward_eps recorded and no proxy use => HIGH. A high EPS ratio alone => MODERATE; otherwise LOW. A growth-adjusted model alone never causes HIGH. Active cashflow evidence is separately recorded and does not cancel a confirmed shared-EPS step-up. In default observation replay all EPS ratios are unknown, so NVDA HIGH cannot be numerically confirmed until Cloud inputs are exported.

## L. Capital-structure flags

Positive net debt and only EARNINGS_MULTIPLE active => CAPITAL_STRUCTURE_NOT_REPRESENTED_IN_ACTIVE_MODELS. This means no explicit EV/equity bridge in active primitives, not that economic leverage has no effect on EPS. ORCL cash/debt values were not supplied; its actual flag remains pending. Unknown metrics produce no fabricated net-debt flag.

## M. Outlier governance findings

MSFT DCF remains in cross-family representatives despite its unchanged production exclusion. CROSS_FAMILY_SIGNAL_SUPPRESSED requires an executed numeric model, outlier_vs_other_models as the exclusion reason, and a family distinct from the active dominant family. Other invalid/applicability failures do not qualify. AMZN is numerically stable within the supplied PE family but concentrated; it is not a healthy independent multi-model anchor.

## N. Recommended V4.5.2 experiments

- Offline family-level versus model-level weighting experiment, with the original blend frozen as control.
- Test correlation-adjusted evidence weighting separately from production reliability.
- Review family-disagreement reliability penalties in a sandbox; preserve the current outlier decision as baseline.
- Validate capital-structure-aware earnings diagnostics using actual debt/cash/share inputs.
- Evaluate capex-cycle-normalized cashflow scenarios without relaxing existing applicability guards.

No experiments were implemented. Benchmarks are absent from all governance calculations. Use `python scripts/audit_cross_family_governance.py --input-json v45_cloud_production_analysis.json` for exact captured inputs/weights. The Cloud V4.5 page also exports this governance automatically.

Full test results and local commit hash are in the completion message. No push.
