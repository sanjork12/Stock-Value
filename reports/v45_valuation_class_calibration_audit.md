# V4.5 Valuation-Class Calibration Audit

## A. Executive summary

Read-only source audit and captured-input replay tool. No production formula, parameter, class, applicability, weight, MOS, zone, fallback or Peer activation changes.

Evidence limitation: supplied Cloud final fair values alone do not identify model contributions or exact root causes. Missing values below are unknown, not zero. No synthetic fixture results stand in for Cloud.

Direction labels UNDERVALUATION_BIAS_RISK / BALANCED / OVERVALUATION_BIAS_RISK are intentionally not assigned without validated internal evidence. Benchmark proximity is insufficient.

## B. GOOG root cause

Mega-cap override with ticker PE range 20–26 (mid 23); same class as MSFT, different ticker overlay. No segment-level Cloud/YouTube/advertising valuation.

Need actual EPS/source, Growth PE floor/cap, DCF FCF/share bridge and exclusions to identify the downward driver. Lower than benchmark is not proof of undervaluation bias.

Snapshot status: CLOUD_MODEL_INPUT_SNAPSHOT_REQUIRED. Exact Cloud root cause: pending captured evidence.

Structural candidates (not confirmed causes): MULTIPLE_ASSUMPTION, MODEL_CORRELATION, BUSINESS_MIX.

## C. MSFT root cause

Ticker PE 26–32 (mid 29); Forward PE and Growth PE share EPS, with implied forward/trailing growth also entering Growth PE. DCF fixed growth is 11%, not observed earnings_growth.

Cannot identify largest positive contribution or validate EPS forecast without captured models. Shared signals are a risk, not evidence of a numeric forecast error.

Snapshot status: CLOUD_MODEL_INPUT_SNAPSHOT_REQUIRED. Exact Cloud root cause: pending captured evidence.

Structural candidates (not confirmed causes): EPS_FORECAST, MODEL_CORRELATION, GROWTH_DOUBLE_COUNT.

## D. ORCL root cause

Mature-growth override, PE 18–26 (mid 22), fixed DCF growth 10%. Preferred models are Forward PE/DCF/Growth PE; no EV/EBITDA primitive in the internal preferred set. DCF explicitly computes enterprise + cash − debt, then divides by canonical enterprise shares.

Correct bridge syntax does not validate the actual cash/debt values or FCFF basis. EPS P/E has no extra debt subtraction; whether leverage is reflected economically requires input/source validation.

Snapshot status: CLOUD_MODEL_INPUT_SNAPSHOT_REQUIRED. Exact Cloud root cause: pending captured evidence.

Structural candidates (not confirmed causes): CAPITAL_STRUCTURE, MODEL_CORRELATION, DCF_ASSUMPTION.

## E. NVDA control

Semiconductor-growth override, PE 20–28 (mid 24), normalized growth base 16%/cap 18%, fixed DCF growth 12%. Forecast EPS and implied EPS growth are shared between PE primitives.

No automatic forward-PE multiple expansion from live growth. DCF fixed growth is a separate assumption; triple counting of one live signal is not established.

Snapshot status: CLOUD_MODEL_INPUT_SNAPSHOT_REQUIRED. Exact Cloud root cause: pending captured evidence.

Structural candidates (not confirmed causes): EPS_FORECAST, GROWTH_DOUBLE_COUNT, MODEL_CORRELATION.

## F. AMZN healthy anchor — not yet established

Mega-cap override, PE 26–32 (mid 29), normalized growth base 14%/cap 16%, fixed DCF growth 12%. Company-level Peer is ineligible and cannot enter diagnostic internal blend.

An internal fair near benchmark does not establish healthy model independence. Need captured applicability/outlier/weights/dispersion; do not assume DCF is included or healthy.

Snapshot status: CLOUD_MODEL_INPUT_SNAPSHOT_REQUIRED. Exact Cloud root cause: pending captured evidence.

Structural candidates (not confirmed causes): MODEL_APPLICABILITY, MODEL_CORRELATION, WEIGHTING.

## G. Model contribution waterfalls

For each captured model: raw pre-outlier mid, applicability/validity/inclusion, exclusions, exact inputs, low/mid/high, configured and normalized weights, weighted contribution, outlier reason. Contribution sum must equal blended mid to 1e-6 absolute tolerance.

### GOOG

Unavailable: no matching Cloud model/input snapshot.

### MSFT

Unavailable: no matching Cloud model/input snapshot.

### ORCL

Unavailable: no matching Cloud model/input snapshot.

### NVDA

Unavailable: no matching Cloud model/input snapshot.

### AMZN

Unavailable: no matching Cloud model/input snapshot.

## H. Growth double-count findings

- Forward PE and Growth PE share the same EPS basis.
- Growth PE combines fixed norm_growth with eligible live earnings_growth and implied forward/trailing EPS growth, then caps it.
- Forward PE multiple is fixed by ticker/class; no live-growth multiple expansion.
- DCF projects FCF using fixed class/ticker growth with a mature-growth fade and fixed terminal growth; no live earnings_growth or explicit revenue/margin model.
- Weighted blending shared-signal models can overrepresent one expectation; this is qualitative correlation, not proven arithmetic double/triple counting.

## I. Sensitivity results

GOOG/MSFT/ORCL: snapshot replay required before sensitivities. Forward EPS ±10%; observed earnings_growth ±20% with class/DCF assumptions fixed; Forward PE realized target multiple ±10% only. Full applicability/outlier/blend rerun. These scopes distinguish shared-signal sensitivity from changing fixed production assumptions.

Numerical sensitivities are in JSON for capture-replay matches. Without snapshots, no elasticities or most-sensitive-input ranking is fabricated. Cached final fair paired with current failed input is rejected.

## J. Model correlation

Forward PE ↔ Growth PE: HIGH_CORRELATION (shared EPS; Growth PE also uses implied forward/trailing growth). PE ↔ DCF: MEDIUM_CORRELATION qualitatively (same firm/cycle, separate fixed DCF growth and FCF basis). No time-series correlation was measured; no weights changed.

## K. Root-cause matrix

Each stock has at most three structural candidates above. No INPUT_QUALITY error, classification mismatch, systematic bias direction or exact Cloud primitive driver is proven from final fair values alone.

## L. Recommended next calibration experiments

- Capture same-run normalized inputs, source timestamps and full internal blend before any calibration.
- Separate EPS-level and EPS-growth sensitivity; compare linked Forward PE/Growth PE contributions without changing weights.
- In isolated experiments, assess correlated-model weight concentration; do not activate changes.
- Validate capex/FCF normalization, levered versus unlevered cashflow basis, debt bridge and canonical shares.
- Run segment/business-mix scenarios separately from company-level baseline, without fitting to benchmark.
- Inspect ticker overlays versus class assumptions and floor/cap saturation before proposing class-specific experiments.

## POST-HOC ONLY reference context

- GOOG: user Cloud fair 253.81, benchmark 345, gap -26.43% (not used in audit calculations).
- MSFT: user Cloud fair 657.04, benchmark 544, gap 20.78% (not used in audit calculations).
- ORCL: user Cloud fair 237.71, benchmark 180, gap 32.06% (not used in audit calculations).
- NVDA: user Cloud fair 358.45, benchmark 300, gap 19.48% (not used in audit calculations).
- AMZN: user Cloud fair 290.44, benchmark 285, gap 1.91% (not used in audit calculations).

## Reproduce with Cloud captures

Run `python scripts/audit_valuation_classes.py --input-json <file>` with an `analyses` object keyed by ticker, each containing normalized `financials` and the matching captured `blend`. The tool makes no network calls or snapshot writes. Report JSON contains detailed inputs, contributions and all sensitivity runs.

No production changes. Cloud export capture is pending deployment. No commit or push; full-suite validation is reported in the completion message.
