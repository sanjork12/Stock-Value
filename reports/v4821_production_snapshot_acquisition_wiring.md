# V4.8.2.1 Production Snapshot Acquisition Wiring Audit & Fix

## Evidence boundary / exact root cause

The reported live Cloud field loss cannot be conclusively attributed to a root-cause category without a same-run trace. This change does not assert that a default-config legacy path, field mapping loss, stale cache, or dropped recovery payload caused the observed Cloud result.

Confirmed source findings:

1. `acquisition_simulation.run_simulation` acquires a baseline, then uses controlled replay of its captured direct fields. Its HEALTHY scenario does not establish that a subsequent live production acquisition was healthy. Classification for this comparison limitation: OTHER_CONFIRMED_CAUSE (controlled replay and subsequent live acquisition are different observations). This explains why the comparison alone is not proof of wiring failure; it is not an asserted explanation for actual production missing fields.
2. Previously the production admin route injected `streamlit_app.fundamentals_cached`. Default flags already select canonical quality-aware acquisition. When the explicit quality-cache flag is disabled, however, the same injected wrapper selects a 900-second legacy normalized cache. That conditional path is proven in source; its activation in the user's Cloud runtime is not proven. The new admin route removes that outer-cache dependency and explicitly requires canonical acquisition to be enabled. It does not silently override a disabled safety/rollback configuration.
3. The production export previously set top-level input_batch_id to the new batch ID without preserving/checking every stage identity. Raw acquisition did not export the three public raw field values. These confirmed observability omissions prevented end-to-end verification. Four actual boundary identities and raw/normalized/valuation/calibration values are now retained and divergences are marked.
4. Source and controlled tests show existing accepted fresh recovery is already propagated: `acquire` replaces the whole `info` with the improved fresh response, and `RawAcquisitionCache.get` passes that accepted response to normalization. No recovery algorithm fix or new fallback was warranted.

No live Cloud diagnosis is invented. The next Cloud run can confirm/refute LEGACY_ACQUISITION_PATH, STALE_DOWNSTREAM_CACHE, SESSION_BATCH_REUSE, FIELD_MAPPING_LOSS, RECOVERY_PAYLOAD_NOT_PROPAGATED or BATCH_ID_DIVERGENCE using recorded values rather than assumptions.

## A. Exact production call chain

- `streamlit_app.py` admin `_v45_export_open` route -> `render_snapshot_export(... fundamentals_loader=snapshot_fundamentals)`.
- `production_snapshot_admin.render_snapshot_export`: “运行五股生产分析快照” handler clears previous result then calls `run_batch`.
- `run_batch`: creates fresh `fundamental_acquisition.acquisition_batch(force_refresh=True)` ContextVar scope; per-ticker loader calls coalesce in request-scope cache.
- `_run_batch_impl`: authorizes Cloud/admin, acquires lock/cooldown, uses scope batch ID, calls `capture_analysis` serially.
- `capture_analysis`: clones the existing `analysis_service.analyze_ticker` code for read-only boundary observation; no second valuation implementation. Peer provider execution is disabled here.
- `analysis_service.analyze_ticker`: history loader, observed fundamentals loader, then existing `fill_fundamental_fallbacks` and existing valuation engine.
- `production_input_wiring.snapshot_fundamentals`: calls canonical `mag7_monitor.get_live_fundamentals(ticker, force_refresh=True)`; disabled canonical feature explicitly rejects instead of entering legacy normalized caching.
- `get_live_fundamentals` -> `fundamental_acquisition.RAW_CACHE.get` -> `acquire` -> Yahoo primary `get_info`, permitted one-shot fresh recovery and existing direct fallbacks.
- RAW_CACHE normalization callback -> `mag7_monitor._get_live_fundamentals_impl(... _raw_context=(info,t,meta))` -> unchanged raw field mapping -> `fill_fundamental_fallbacks` -> `financial_normalization.normalize_financials` -> existing `decorate_inputs` provenance. No raw Yahoo info re-fetch in normalization.
- Existing `analysis_service` normalization -> observed `valuation_engine.valuate` -> unchanged profile/gates/primitives/blend/reliability/zones.
- `project_snapshot` captures the same normalized valuation argument; `_run_batch_impl` captures this exact stock normalized object at the `calibration_eligibility(stock,reference)` call boundary.
- Existing V4.5/V4.6/V4.7/V4.8/V4.9 sidecars consume captured inputs; none initiates a fundamentals acquisition.
- Existing `_public`/`snapshot_json` serialization exports production_input_trace with Calibration Batch Status in the same V4.5 JSON.

## B. Old and canonical acquisition paths

Old admin injection: fundamentals_cached -> quality-aware default, or conditional _legacy_fundamentals_cached -> get_live_fundamentals -> legacy implementation when quality cache disabled.

New admin injection: snapshot_fundamentals -> canonical get_live_fundamentals(force_refresh=True) -> RAW_CACHE.get. The main Dashboard/single-stock loader and feature-flag policy are unchanged. No second fundamentals acquisition implementation is introduced.

## C. Cache and session audit

- history_cached: Streamlit cache_data, key ticker/as_of/function code, TTL 900s, historical price DataFrame; unchanged, not a financial EPS/currency cache.
- _legacy_fundamentals_cached: Streamlit cache_data, ticker/function-code key, TTL 900s, normalized fundamentals dict; removed from the snapshot route only. No cache_resource financial or analysis object exists in this route.
- RAW_CACHE.entries: key uppercase ticker/factory/Flags/allow_estimates/V4.8.2 version; TTL HEALTHY900/PARTIAL300/DEGRADED60/UNAVAILABLE60; raw public info, recorded statement/estimate payloads and metadata; bounded512. New explicit snapshot run forces fresh acquisition rather than accepting old entries. Recovery, promotion, expiry and healthy/degraded preservation policies are unchanged.
- RAW_CACHE ContextVar request scope: batch ID/ticker/fundamentals/options/allow_estimates, lifetime one batch; normalized result deep copies for intra-batch coalescing.
- Snapshot wrapper request scope: batch ID/ticker/production_fundamentals, lifetime one batch; same captured fundamentals result, no stale cross-batch normalized cache.
- `_v45_export_result`: session result, no TTL, owner checked; used for display only. Button already clears it before every accepted new run; retained behavior is tested with real widgets. Lock plus per-user `_LAST_RUN`30s cooldown can reject rapid clicks, never relabel an old batch as new.
- Finnhub provider cache: endpoint/params key, public data; quote600s/profile86400s/metrics28800s (other enabled endpoints retain existing TTL). Existing acquisition optional direct quote/profile candidates only. No derived EPS or financial-currency inference added.
- yfinance may internally cache provider responses; this patch does not assert network-level HTTP freshness. It invokes the existing acquisition's logical fresh path. Simulation replay is explicitly distinct from live requests.

## D. Field propagation and identity

RAW_CACHE now attaches only selected accepted raw `forwardEps`, `currency`, `financialCurrency` (existing financialCurrencyCode alias supported) and their existing source paths to metadata. It stamps current input_batch_id before the existing normalization callback. No entire raw Yahoo dictionary or credentials are exported.

Trace includes raw provider value/source and health, normalized value/source, normalization source label, valuation argument and exact calibration argument. It preserves actual input_batch_id and fundamentals_acquisition_id at raw/normalized/valuation/calibration stages. Differing observed IDs produce BATCH_ACQUISITION_DIVERGENCE / acceptance FAIL; absent identity is UNOBSERVED, never fabricated. The top-level UI batch label cannot conceal mismatched captured stage IDs.

If accepted fresh recovery values differ downstream, accepted_recovery_payload_is_downstream_payload=false. HEALTHY acquisition with lost/changed traced values marks acceptance FAIL. PASS means the observed wiring is consistent, not that the stock or calibration is otherwise eligible.

## E. Files changed and frozen invariants

- production_input_wiring.py: canonical snapshot loader and pure trace/summary helpers.
- streamlit_app.py: snapshot route injects uncached canonical loader.
- fundamental_acquisition.py: three public raw fields and early batch identity metadata only; resilience logic/flags/health/recovery/TTL/fallback rules unchanged.
- production_snapshot_admin.py: observations at loader, valuation and guard boundaries; compact admin table and JSON namespace.
- tests/test_production_input_wiring.py: 28 regression/integration tests.
- scripts/verify_v45_snapshot_ui.py: real-widget trace and new-button batch assertions.
- this report.

Valuation formulas/parameters, Calibration Guard, Proxy Guard, V4.6/V4.7/V4.8/V4.9 calculations, Peer, Last Reliable and storage behavior have no changes. No EPS substitutions, derived EPS, currency inference, snapshot writes, or Last Reliable mutation are added.

## F. Tests

Complete unittest suite: 827 tests, 0 FAIL, 0 ERROR (28 new tests). Existing calibration/proxy/reliability/overlay/enterprise/suitability/Peer/Last Reliable tests remain passing.

New tests cover canonical entrypoint, feature-disabled explicit rejection, fresh recovered payload propagation, 12 three-field/stage checks, batch/acquisition identity, stale identity/batch detection, lost healthy calibration value rejection, no raw credentials, single acquisition per batch, new batch bypassing old raw cache, production result equivalence, five-stock runs with no database access and compact summaries.

Real Streamlit widget verification PASS: batch/trace rendering, five existing/new downloads, another button run gets a different batch, saved legacy report rerender does not fetch, access revocation removes downloads. Synthetic widget values are not Cloud evidence.

## G. Cloud acceptance / commit

After an explicitly authorized deployment:
1. Keep canonical quality-cache feature enabled. Open administrator production snapshot page; click once after cooldown.
2. Check new Production Input Wiring Trace table and download existing v45_cloud_production_analysis.json. Both production_input_trace and Calibration Batch Status are present.
3. Each stock's four stage batch IDs must match the report input_batch_id and all four acquisition IDs must agree. Any BATCH_ACQUISITION_DIVERGENCE is a failed wiring run.
4. When raw acquisition is HEALTHY, all three direct raw values must survive normalization/valuation/calibration. HEALTHY raw but missing calibration EPS/currency is FAIL regardless of other eligibility reasons.
5. When fresh recovery is used, verify yahoo.fresh_get_info source, original recovered values and accepted_recovery_payload_is_downstream_payload=true.
6. Genuine degraded acquisition may still yield an ineligible batch. Do not relax guards or substitute other EPS/currency to force ELIGIBLE.
7. Send the same-run JSON for exact Cloud root-cause classification. This local patch cannot verify credentials/provider behavior in the remote runtime.

Implementation commit hash is provided in the completion response and can be resolved by `git log -1 --format=%H -- reports/v4821_production_snapshot_acquisition_wiring.md`. No push performed.
