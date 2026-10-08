# V4.5.0 Calibration Snapshot Eligibility / Data-State Guard

Read-only governance only. No production formula, proxy/applicability policy,
Peer, weights, normalization, fallback, Auth/RLS or Supabase writes changed.

## Rules

Eligibility consumes the recorded production live blend and its included models,
the same execution's normalized inputs, capture/source/alignment flags, and an
optional projected historical reference. It never reruns applicability or values
a stock. All reasons are recorded even when multiple conditions apply.

Main-status precedence:

1. No current live fair, no displayed production fair, or fewer than two included
   production models: INELIGIBLE_UNAVAILABLE_VALUATION.
2. Verified healthy recent reference plus missing current core fields:
   INELIGIBLE_TRANSIENT_INPUT_DEGRADATION.
3. Missing forward EPS and included EPS primitives actually using proxy inputs:
   INELIGIBLE_PROXY_ONLY_VALUATION.
4. Unknown quote/financial currency, or recorded/explicit currency mismatch:
   INELIGIBLE_CURRENCY_CONTEXT_UNKNOWN. `currency_mismatch=false` never proves
   currency is known.
5. Cached/non-live, incomplete or mismatched input execution, or Peer in the
   internal blend: ineligible data-state with explicit reason. This does not
   by itself assert transient loss; transient_input_degradation remains false
   unless a healthy reference actually establishes missing current fields.
6. Otherwise ELIGIBLE. Existing production included/applicable results are
   authoritative; no second class-specific valuation gate is introduced.

Proxy-only refers to the EPS regime of included EPS primitives, not a claim
that no cashflow model participated. Missing EPS without any included EPS
primitive is not automatically proxy-only; production model applicability governs.

## Reference handling

Read existing same-day raw.last_reliable via the existing authenticated snapshot
reader; look at the prior day's row if needed. Projection is whitelist-only.
Preserve calculated_at and source, fair/confidence, forward EPS/source, currencies,
canonical shares/source, split knowledge/date/factor. Existing Last Reliable
inputs do not always store forward_eps_source: when available, recover it from
the saved production Forward PE primitive's forward_eps/eps_source, not from
current live data. Otherwise export null.

A reference establishes transience only when it is live, valuation and forward
EPS are positive, currencies and share/split context are known, and its timestamp
is not future and strictly less than 24 hours old. Expired/incomplete references
may be shown as references but cannot prove transient loss. Foreign ticker rows
are rejected. Reference data is never substituted into current financials or
blend; reference_snapshot_used_for_calibration is always false. No timestamp is
refreshed and no snapshot is saved. Existing production display fallback is
unchanged, and cached display/current live mismatch remains explicitly marked.

## Expected replay of user-reported Cloud batch

Without a verifiable healthy reference:

- GOOG: INELIGIBLE_PROXY_ONLY_VALUATION; quote-currency-unknown also recorded.
- MSFT: INELIGIBLE_PROXY_ONLY_VALUATION; quote-currency-unknown also recorded.
- ORCL: INELIGIBLE_PROXY_ONLY_VALUATION; quote-currency-unknown also recorded.
- NVDA: INELIGIBLE_UNAVAILABLE_VALUATION; all other detected reasons retained.
- AMZN: INELIGIBLE_PROXY_ONLY_VALUATION; quote-currency-unknown also recorded.

With a healthy reference, the first four available proxy valuations instead use
the higher-priority transient-degradation status; NVDA remains unavailable and
may also have transient_input_degradation=true. This is expected governance
replay from supplied evidence, not a new Cloud fetch.

Batch is ELIGIBLE only when exactly the five required distinct tickers are
present and each is ELIGIBLE. Otherwise INELIGIBLE with ineligible_tickers and
batch_reasons. The supplied degraded batch is INELIGIBLE.

## UI / export / downstream audit

Cloud V4.5 export page shows Calibration Batch Status before the result summary,
then all ticker reasons and the warning:
“本批次仅用于输入降级诊断，不应用于估值校准。”
JSON adds all stock/batch governance and reference fields. The offline V4.5 audit
also refuses degraded captures before sensitivity/replay; it cannot silently
treat a proxy/currency-degraded live fair as a healthy calibration baseline.

## Files and verification

Added calibration_snapshot_guard.py, tests/test_calibration_snapshot_guard.py and
this report. Updated production_snapshot_admin.py, streamlit_app.py,
valuation_calibration_audit.py, scripts/verify_v45_snapshot_ui.py.

Tests cover proxy, unavailable, currency unknown despite mismatch=false, healthy
live, transient reference, expiry/context checks, cached mismatch, batch failure,
the reported five-stock state replay, downstream refusal and reference read-only
integration. Existing production same-input/fair, no-write, credential-redaction,
Peer isolation and prior regression tests remain in the full suite.

Full-suite totals and the local commit hash are supplied in the completion
message. No push; no Cloud execution or new market values are claimed.
