# V4.8.1 Cloud Financial Input Resilience & Provider Fallback Audit

## A. Executive summary

Implemented a Cloud-only ADMIN_EMAIL provider audit. No production fallback is
implemented. The user-reported pattern is missing forward EPS, quote currency,
financial currency and (NVDA) split context, with proxy-only/unavailable live
valuation. These are symptoms, not proof of a particular Yahoo network failure.

**Cloud runtime evidence is pending.** Local tests use explicitly synthetic
fixtures. This report does not claim they are live GOOG/MSFT/ORCL/NVDA/AMZN data.
Run `Cloud Input Resilience Audit` → `运行五股 Provider Audit` after deployment
and download `v481_cloud_input_resilience.json` to establish actual path results.
No push was performed for this implementation.

## B. Yahoo path audit

Production `mag7_monitor._merge_ticker_info` calls get_info first; info is attempted
only when the accumulated dict is empty. A nonempty response missing forward EPS
and currencies skips that alternative. fast_info currently supplements shares,
market cap and price. This behavior is unchanged. Production may separately use
get_earnings_estimate when forward EPS is absent; the audit does not call estimate
endpoints or rerun valuation.

The isolated audit calls info, get_info, fast_info, get_history_metadata,
financials, income_stmt, cashflow, balance_sheet, splits and bounded 10-year history
actions once per ticker. Same Ticker object deliberately exposes shared lazy cache
effects; these paths are not assumed independent. Public field projections,
exception category only, latency, acquisition timestamps, statement periods and
path state are exported. No provider exception messages or complete raw objects
are exported. Lazy fast_info field failures preserve other available fields.

## C. Finnhub field availability

Reuse existing FinnhubProvider `_symbol` and its endpoint allowlist/cache/rate
limiter for profile2, metric/all and quote only. Observe currency, market cap,
shares, industry, exchange, epsTTM, peTTM, forwardPE, beta, 52-week values and
epsForward if actually returned. Missing values remain null. A reported epsForward
still requires forecast-horizon/semantics validation and is diagnostic-only.
Profile market capitalization/share counts are converted from millions to base
units before comparison. Actual Cloud availability remains pending.

## D. Currency resilience

Finnhub profile currency, if present, is a DIRECT / SAFE_WITH_VALIDATION candidate
for quote currency. Validate listing identity, freshness and all direct currency
disagreements first. Statement financial currency is never filled from quote
currency. Explicit Yahoo financialCurrency from an alternative path may be
considered with validation; otherwise financial currency remains unknown and
quote-to-reporting-currency inference is UNSAFE.

## E. Forward EPS resilience

price / forwardPE is DERIVED / DIAGNOSTIC_ONLY, never direct EPS. Record price,
multiple, provider, calculation time, positive and plausibility checks, trailing
EPS ratio and healthy-reference percentage difference. Quote timestamp and metric
retrieval timestamp are exported, but metric effective time is not provided:
retrieval alignment does **not** establish fundamental-period alignment. These
unverified candidates never enter production or unlock real eligibility. Reference
EPS is comparison-only, never a calculation operand. No target/benchmark inversion.

## F. Split resilience

Nonempty splits/history-actions may directly provide last split date/factor even
when info fails. Mark these as SAFE_DIRECT candidates subject to complete history
and listing/share-basis validation. Empty history is not proof of a known no-split
context. Both date and factor are required to address split-context reasons.

## G. Shares resilience

Export info/fast_info/profile/statement share observations and info marketCap / price
as a derived comparison, with pairwise agreement. Diluted weighted-average shares
are not automatically interchangeable with current shares. Canonical priority and
algorithm are unchanged. Period, units, listing and split basis need validation.

## H. Statement-data resilience

Compare cash/debt/EBITDA/revenue from info and statement paths against an existing
admin production batch's normalized values, if available. Production comparison
batch ID/time are explicit; those old values are not mixed into current provider
calculations. Statement values carry periods. Annual statement values are not
automatically promoted to current/TTM production fields. No zero-value assumption
is introduced by this audit.

## I. Cache behavior

Source-confirmed Streamlit TTL: history and fundamentals 900 seconds. Successful
return of partial fundamentals is eligible for that cache; whether a specific
Cloud response hit it is unobservable and remains unknown. Diagnostic Yahoo uses
a fresh Ticker, bypassing those wrappers. Existing admin session batches have no
TTL; their saved timestamp is displayed in the report.

Finnhub TTL: quote 600 seconds, profile 86400 seconds, metric 28800 seconds;
NO_DATA uses endpoint TTL and errors 60 seconds. Existing cache hit/age/key/TTL
are observed under its lock. Cached degraded/unavailable responses with TTL >60
are flagged DEGRADED_CACHE_AMPLIFICATION when actually observed. No TTL changes.

## J. Request-count behavior

Export per-path method invocation counts, not invented HTTP counts. yfinance
properties may share responses or trigger additional HTTP calls/internal retries.
Production request repetition and actual network counts are not established by
this audit. No aggressive retry added. Existing Finnhub retry policy is reused;
RATE_LIMIT skips all remaining Finnhub endpoints and tickers in this batch.

## K. Provider disagreement

Numeric disagreement = abs(a-b) / max(abs(a),abs(b),epsilon) × 100.
<=2% CONSISTENT; >2–5% MINOR_DIFFERENCE; >5% MATERIAL_DIFFERENCE.
Categorical fields use exact match/mismatch. Values from different timestamps,
annual/TTM periods or share bases require interpretation; disagreement alone is
not permission to replace a production field.

## L. Safe fallback candidates

Conditional only: alternative direct Yahoo split history; profile quote currency;
direct shares/market cap/price/trailing EPS and statement financial fields with
the required period, currency, timestamp, identity and share-basis validation.
Each exported proposal records source type, tier, safety and required validations.
IMPLEMENT is a proposal for the next release, not an executed fallback.

## M. Unsafe fallback candidates

Reject inferred financial currency. Do not substitute trailing/statement EPS,
Last Reliable EPS, analyst targets or external benchmarks for current forward EPS.
Derived EPS remains diagnostic-only. Missing providers do not crash the batch;
missing fields stay explicit.

## N. Calibration recovery simulation

Read-only reason-addressability scenarios: quote-currency only, split only,
SAFE_DIRECT set, validated direct fields pending validation, and derived EPS
diagnostic-only. No calibration function, valuation engine or model is rerun.
Original production batch reasons remain intact. Unavailable valuation/fewer
models/currency mismatch cannot be erased by an EPS candidate. Even zero remaining
reasons means only possible recovery requiring a new complete live production run,
not ELIGIBLE. No existing production batch means UNKNOWN_NO_CURRENT_BATCH.

## O. Recommendation for V4.8.2

First collect the actual Cloud export. Prioritize confirmed alternate split
evidence, then validated direct quote-currency candidates. Review share basis,
statement periods and provider disagreement before any multi-provider fallback.
Keep derived EPS diagnostic-only. Consider degraded-cache policy/request
coalescing only after runtime evidence, not solely the current failure pattern.
No resilience wrapper, TTL or production precedence changes in V4.8.1.

## Verification and invariants

25 new unit tests; 689 total tests PASS (0 FAIL / 0 ERROR). Streamlit real-widget
check passes for batch, summary, five expanders, export and access revocation.
No Supabase calls/writes, production analysis/valuation/governance invocation or
Last Reliable mutation in the audit. All previous regression tests pass.
Changed existing application code is limited to administrator navigation and
diagnostic session cleanup. Model/normalization/guard/Peer/Last Reliable files
are unchanged. Credentials are removed at the existing export boundary.
