# V4.8.2 Quality-Aware Yahoo Acquisition & Cache Resilience

## A. Executive summary

Production acquisition now validates field health, permits one fresh Ticker
recovery, uses quality-aware public raw cache TTL and request-local coalescing.
No valuation formula, model parameter, normalization algorithm, guard threshold,
reliability/confidence policy, experiment, Peer or Last Reliable logic changed.
No database writes were introduced. No push/deployment performed.

The user supplied Cloud V4.8.1 findings: fresh Yahoo paths could obtain direct EPS,
currencies and statement data while earlier production batches stayed degraded.
This implementation addresses a demonstrated source-code/fixture mechanism; it
does not claim that Yahoo throttling or a specific Cloud HTTP incident is proven.
Actual deployed V4.8.2 validation remains pending.

## B. Original failure mechanism

Old `_merge_ticker_info`: a nonempty get_info result skipped the info alternative,
even if EPS and currencies were absent. Streamlit fundamentals_cached admitted
the resulting object for 900 seconds. Saved admin batches did not expire. These
could preserve an initially degraded response. Installed yfinance inspection
confirms info calls get_info, which reads `_quote.info`; they are not independent
providers. A fresh Ticker is an independent logical attempt, not a guarantee of
independent HTTP cache/transport or a cure for throttling.

## C. Field health model

FundamentalFieldHealth exposes HEALTHY / PARTIAL / DEGRADED / UNAVAILABLE with
groups CORE_MARKET_IDENTITY, EARNINGS_VALUATION, CURRENCY_CONTEXT, SHARE_CONTEXT,
ENTERPRISE_INPUTS. Required models are read from the existing class profile;
profile rules are not changed. Irrelevant EBITDA/forward EPS fields do not degrade
bank or specialized profiles merely because those fields are absent.

## D. Critical-field policy

Price, market cap and quote currency are market identity requirements. Forward
EPS is critical when forward/growth earnings models are preferred. Financial
currency is critical for preferred statement/enterprise/bank models. Share
candidates are required for those per-share models. Split verification becomes
critical when direct outstanding vs implied share counts show uncertain basis
(>20% difference); it may also be explicitly required by a supplied policy.
The 20% value is acquisition-health triage only, not a canonical-share resolver or
valuation/guard threshold. Optional relevant missing fields yield PARTIAL.
Health describes raw acquisition, so an existing statement/estimate fallback does
not falsely promote missing raw direct fields to HEALTHY.

## E. One-shot fresh recovery

For a nonempty DEGRADED primary, attempt at most one new Ticker.get_info. Accept
the whole fresh response only when its critical-missing set is a strict subset
of the previous set. Do not splice two info responses. A partly improved response
still remains DEGRADED if critical fields remain missing. Wrong ticker identity
is rejected. Empty responses retain the bounded legacy same-object info attempt;
no retry loop or additional retry/backoff is added. Metadata records reason,
attempt/result, source and recovered fields.

## F. Quality-aware cache

Central HEALTH_TTLS: HEALTHY 900s, PARTIAL 300s, DEGRADED/UNAVAILABLE 60s. Cache
contains raw selected info plus recorded statement/estimate payloads, never
valuation results or a live client. Every hit is copied and passes the existing
normalizer again. Entry expiry and the state's TTL are both checked.

Expired degraded entries require acquisition. A recovered healthy entry can
promote quality. A forced fresh degraded attempt cannot replace an unexpired
healthy cache; the current caller receives explicitly degraded fresh input, while
the retained cache stays reusable until expiry. Expired healthy entries are not
used to hide degraded input. Metadata includes health/missing fields, acquired
time, expiry, source, policy version, acquisition ID, hit/age/TTL and promotion.

Input freshness is `live`, `fresh_recovered`, `cached_healthy`, `degraded_live` or
`degraded_cached` in fundamentals_source_status. Existing top-level analysis
source_status/Calibration/Last Reliable semantics are unchanged; cached input is
not described as newly acquired live input by the new metadata.

## G. Batch request coalescing

Context-local request_scope_cache uses batch/ticker/acquisition kind (plus flags
and estimate mode). Consumers get deep copies. Each five-stock production export
button creates a new input_batch_id and forces a fresh acquisition cycle, bypassing
old raw cache entries. Downstream normalize, valuation, V4.6/V4.7/V4.8 consume that
single captured input; they do not fetch again. fundamentals_acquisition_id and
batch_input_health are exported. Saved old batches may still display with original
timestamps; degraded batches explicitly prompt a new button run. No automatic
background retries or data substitution are introduced.

## H. Quote currency fallback

Only when primary currency is missing: examine Yahoo history metadata, fast_info,
then Finnhub profile2 using the existing client. Choose the first validated direct
source in that precedence only when observed direct values agree. Finnhub requires
exact ticker and matching normalized listing/exchange evidence. Missing listing
evidence does not validate Finnhub. Identity/listing conflict or currency conflict
leaves currency unresolved and records the reason. Primary known currency is never
unconditionally overwritten. source/fallback/validation and evidence are retained.

## I. Financial currency protection

Only explicit current/fresh Yahoo financialCurrency/financialCurrencyCode is used.
Quote currency and Finnhub profile currency never fill reporting currency. Unknown
stays unknown; existing Calibration Guard judges it normally.

## J. Split fallback

Missing split date/factor may use nonempty valid Yahoo splits, whose installed
yfinance path defaults to period=max. Select latest positive valid event from the
full returned series, validate listing and reject future events. Empty history is
not proof of known split context. Record yahoo.splits/fallback provenance. Primary
split values remain untouched when complete. Diagnostic disagreement canonicalizes
`20:1` and `20.0` to the same ratio and compares calendar event dates, not raw seconds.
Snapshot/Last Reliable comparison rules themselves are unchanged.

## K. Forward EPS protection

Hierarchy: current Yahoo direct forwardEps, one-shot fresh direct forwardEps, then
existing Yahoo estimate/secondary direct source behavior. New production resilience
never derives EPS from price/forwardPE or Finnhub. The legacy price/forwardPE
construction is bypassed on the new path. No trailing/statement/reference/target
substitution is added.

Existing get_earnings_estimate is preserved without expanding semantics. Local
yfinance source reads `_analysis.earnings_estimate` from quoteSummary earningsTrend.
Its avg is a direct analyst estimate, not a realized statement EPS. Existing period
priority remains 0y, +1y, 0q, +1q, then first available avg. Export selected period,
source and acquisition path. Currency/share basis/provider-effective timestamp are
not independently guaranteed; Cloud stability remains an observation to validate,
not an asserted property. No new endpoint or analyst-target inversion introduced.

## L. Shares and statements protection

Canonical resolver, priority and mismatch rules unchanged. Existing fast_info
shares/market cap/price supplementation stays. GOOG 5.53B outstanding vs ~12.23B
implied case retains the original canonical result. No Finnhub share/market-cap
production substitution enabled.

Existing statement cash/debt fallback continues only when primary is missing.
Record statement period, row, currency, as-of date and basis. Unknown legacy
assumed-zero cash/debt is explicitly labelled inferred; the preexisting numerical
rule is not changed. Revenue/EBITDA FY values are not newly substituted for TTM.
Diluted average shares retain statement period/row provenance. Enterprise metric
basis is marked quote-summary/current or unknown; multiple semantics unchanged.

## M. Telemetry / feature flags

Process-local counters: degraded writes/hits, healthy hits, fresh recovery attempts/
successes and logical acquisition calls. No user identity in telemetry. Raw
statement/estimate method names/counts are recorded; HTTP_COUNT_UNAVAILABLE is
explicit because lazy properties may share or internally retry network calls.
Cache is bounded to 512 entries and counters reset on process restart.

Environment flags and defaults:

- ENABLE_QUALITY_AWARE_FUNDAMENTALS_CACHE=true (master rollback switch)
- ENABLE_ONE_SHOT_FRESH_RECOVERY=true
- ENABLE_YAHOO_SPLIT_FALLBACK=true
- ENABLE_QUOTE_CURRENCY_FALLBACK=true
- ENABLE_FINNHUB_PRICE_FALLBACK=true
- ENABLE_FINNHUB_TRAILING_EPS_FALLBACK=false
- ENABLE_DERIVED_FORWARD_EPS_PRODUCTION=false (cannot enable via configuration)

Finnhub price requires matching ticker/exchange/currency, positive price and quote
timestamp no older than 600s and not in the future. Market cap remains existing
Yahoo-only behavior. Trailing EPS stays a candidate even if its flag is requested:
independent period/share-basis validation is not implemented, so no automatic
Finnhub trailing-EPS substitution is performed. Disabling the master switch restores
legacy acquisition and its original 900s Streamlit cache, including original legacy
source behavior; no guard is changed by rollback.

## N. Production invariants / tests

45 added unit tests. Full suite: 734 PASS, 0 FAIL, 0 ERROR. Five healthy fixed inputs
compare old/new normalized values and complete production blends, reliability,
confidence, fair/range, weights, outliers and zones exactly. Recovery passes the
unchanged Calibration Guard naturally; failed recovery remains ineligible.
GOOG basis, negative safety cases, TTL transitions, coalescing, provenance, admin
permissions and simulation isolation tested. Existing tests remain passing; the
observer equality test now compares within one acquisition batch so changing cache
hit/freshness metadata is not mistaken for a mutation by the observer.

Real Streamlit widget checks pass for existing V4.5 export and the V4.8.1 audit with
V4.8.2 simulation, downloads and access revocation. No Supabase writes introduced.
Valuation engine/primitives, normalization, calibration/proxy guards, V4.6, V4.7,
V4.8 experiment, Peer and Last Reliable source files are unchanged.

## O. Cloud validation plan (pending deployment)

1. Run five-stock production export; inspect input batch/acquisition IDs, health,
   source timestamps, EPS/currencies and original Calibration results.
2. Run V4.8.2 Acquisition Simulation in Cloud Input Resilience Audit. Each ticker
   first obtains a current complete direct baseline. Incomplete baseline aborts.
3. Five scenarios replay that baseline: healthy, partial get_info, missing forward
   EPS, missing currency, missing split. Fresh recovery replays actual captured
   direct data, not hardcoded market values. No provider requests within scenarios.
4. Simulation never accesses/writes production fundamentals raw cache or counters.
   Finnhub is cache-readonly during baseline acquisition, with no new Finnhub calls;
   if needed evidence is unavailable baseline may stay incomplete. Yahoo direct
   alternates are captured at most once before scenario replay.
5. Download v482_acquisition_simulation.json. Empty remaining input gaps do not
   imply ELIGIBLE: real model/guard results must be verified in the new production
   export. Simulation never computes or overwrites eligibility.
6. Confirm healthy cache hit after normal dashboard rerun, degraded expiry <=60s,
   no currency inference, no derived production EPS and original split/share basis.

## P. Recommended next phase

If Cloud direct EPS/currency recovery is stable, freeze this resilience layer and
proceed with V4.9 Enterprise Family Suitability Audit. If direct forward EPS stays
unavailable, investigate V4.8.3 direct forward EPS providers. Do not promote derived
EPS or tune valuation formulas to conceal acquisition failure. Neither next phase
is implemented here.
