# V4.1 Production Verification Findings

Date: 2026-10-01  
These are observations only. Valuation formulas were not changed in this round.

## Blocking (beta)

- Cloud migration not executed. Production may still lack V4.1 columns; `save_snapshot` will silently fall back to the legacy payload if ALTER has not been applied.
- No dual-user RLS proof. Isolation is specified in SQL, not demonstrated with User A/B JWTs.
- Remember-login / logout / Streamlit Cloud multi-user runtime not exercised.

## Allowed fixes applied during verification

- Historical snapshots now reconstruct via `reconstruct_blend_from_snapshot` instead of live `valuate`.
- Historical `model_version` is no longer replaced with current `v4.1-reliability`.
- Legacy caption: “该历史快照创建于可靠性层之前，部分可靠性指标不可用。”
- LOW confidence primary metric is the indicative range, not the midpoint as a bold Fair Value.
- Price / Financials / Valuation run / Snapshot timestamps are labeled separately. Price is the daily bar date (Yahoo daily bars do not supply a reliable 15:42 ET tick timestamp).
- Model explanations show `executed`, `reason`, applicability, and outlier vs not-executed.
- Single-stock analysis errors are user-facing messages; login/signup/password logs no longer use `logger.exception`.
- Idempotent production migration file added. Duplicate policy names are dropped then recreated, not deleted ad hoc on a live project without `IF EXISTS`.

## Model / data notes (do not retune this round)

- NVDA DCF: `executed=False`, `reason=fcf_conversion_too_low` (expected V4.1 gate).
- AMZN DCF: `executed=False`, `reason=capex_or_fcf_distortion`.
- COIN midpoint can still be ~$46 in the payload; UI must keep it secondary. Engine still emits a mid because blending needs a number; presentation policy is the control.
- MU also came back LOW in the 2026-10-01 live smoke (wide cycle range). Spec called out COIN/PLTR; MU is consistent with LOW semantics.
- SPCX/BMNR/TEM were not live-fetched this run. TSLA is SPECIALIZED with fair=None via ticker override.
- Yahoo daily bars do not provide a precise Price clock timestamp. Do not fake 15:42 ET.

## Performance (non-blocking)

- Dashboard autosave: 1 watchlist SELECT + N valuation runs + N snapshot upserts.
- 7-ticker engine smoke: 11.17s, 14 Yahoo-family calls.
- 20-stock Dashboard not measured.

## Schema notes (non-blocking if migration is applied)

- Ticker uppercase is enforced in `normalize_ticker` on write, not by a database CHECK/trigger.
- Duplicate policies: repo SQL already replaces both naming schemes. Do not drop production policies by hand without the idempotent script.
- If an older cloud database was created before unique constraints, `CREATE TABLE IF NOT EXISTS` will **not** add them. The production migration’s `CREATE UNIQUE INDEX IF NOT EXISTS` is required for those databases.

## Security notes

- Remember-me cookie holds a refresh token by design. Treat XSS on the Streamlit origin as session theft risk.
- `valuation_snapshots.json` is tracked (CLI local store). It should not contain credentials; keep secrets out of it.
- Full git-history blob scan for leaked keys was not completed.

## Not bugs / out of scope

- Specialized names (TSLA, crypto treasury, space) still have no dedicated model. Allowed by acceptance criteria.
- Yahoo missing forward EPS remains a data-quality issue, not a formula bug.
