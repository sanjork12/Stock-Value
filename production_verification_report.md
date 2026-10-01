# V4.1 Production Verification Report

Date: 2026-10-01  
Candidate: Stock Fair Value Monitor V4.1 Reliability Beta Candidate  
Runner: local Windows workspace, no production Supabase credentials in this environment

## A. Verdict

**NOT READY FOR BETA**

Required production proofs were not executed against a live Supabase project with two real users. Repo SQL and code review are not a substitute for that.

CLOUD MIGRATION = **NOT EXECUTED**

## B. Blocking issues

1. Production/cloud schema migration was not run against the live database. Column presence, unique constraints, and live RLS policies are unverified in production.
2. User A / User B login, watchlist CRUD, snapshot save/upsert, remember-login, logout, and direct RLS attack tests were **NOT EXECUTED** (no local `.streamlit/secrets.toml`, no `.env`, no test account credentials).
3. Until PV-01 and PV-16–PV-22 pass on the real project, isolation/session claims cannot be accepted.

## C. Schema status

Repo `supabase_schema.sql` (SHA-256 `298be6a82d98aacaeff6e17158a55bb9c92e2ddd56cfdf6c111dc06316bfadc8` at baseline) plus `supabase_v4_1_production_migration.sql`:

- Uses `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for all required V4.1 columns
- Does not drop or rebuild `valuation_snapshots`
- Unique keys in CREATE TABLE: `(user_id, ticker)` and `(user_id, ticker, snapshot_date)`
- Migration also adds unique indexes if an older cloud DB was created without them
- RLS enabled in SQL; policies `TO authenticated` with `auth.uid() = user_id` (profiles uses `user_id`, not `id`)
- Duplicate policy names are dropped then recreated (`Users can insert own watchlist` vs `watchlist_insert_own`)
- No `USING (true)` / `WITH CHECK (true)` in repo SQL
- `model_version` is unconstrained text: null / `legacy` / `v4-sector-aware` / `v4.1-reliability` are all representable

**Production column existence: NOT EXECUTED**

### Manual SQL Editor steps (required)

1. Open the production Supabase project → SQL Editor
2. Paste and run `supabase_v4_1_production_migration.sql` (idempotent)
3. Confirm columns:

```sql
select column_name
from information_schema.columns
where table_schema = 'public' and table_name = 'valuation_snapshots'
order by ordinal_position;
```

4. Confirm policies:

```sql
select schemaname, tablename, policyname, roles, cmd, qual, with_check
from pg_policies
where tablename in ('profiles', 'watchlist', 'valuation_snapshots');
```

5. Re-run PV-01 against the live result. Do not mark PASS until that query output exists.

## D. Auth / session status

Code review:

- Auth tokens live in `st.session_state` only
- `create_authenticated_client()` is **not** `@st.cache_resource`
- Each rerun builds a client and calls `set_session` + `postgrest.auth`
- Remember-me stores a **refresh token** cookie, not a password
- Logout: `sign_out`, delete cookie, `clear_auth_session()` (authenticated / user_id / access_token / refresh_token)
- Login/signup/password logs now record `error_type` only, not exception text that might include request bodies

Live remember-login / logout / email-confirmed User A+B: **NOT EXECUTED**

## E. RLS isolation status

Repo policies are owner-scoped `TO authenticated`. Duplicate historical policy names are handled with `DROP POLICY IF EXISTS` then `CREATE POLICY`.

Live User B cannot-read-A / cross-user INSERT-UPDATE-DELETE-SELECT: **NOT EXECUTED**  
Do not treat this as PASS.

## F. Snapshot / history status

`save_snapshot` upserts on `user_id,ticker,snapshot_date` and writes V4.1 fields (`model_version`, reliability, dispersion, blended range, `models_json`, `reliability_json`). If extra columns are missing in the cloud DB, code falls back to the legacy payload (so writes may succeed while V4.1 columns stay empty). That fallback is why cloud migration must land first.

Historical date mode:

- Price / SMA from `get_history(..., as_of)` (Yahoo bars truncated at the selected date)
- Valuation from the latest snapshot with `snapshot_date <= as_of`
- Reconstruction goes through `reconstruct_blend_from_snapshot` and **does not call `valuate()`**
- Unit test patches `valuate` and mutates `MODEL_VERSION`; saved fair / reliability / model_version stay unchanged
- Legacy rows (`model_version` null/`legacy`, missing reliability columns) show: “该历史快照创建于可靠性层之前，部分可靠性指标不可用。”
- Historical `model_version` is **not** backfilled with today’s `v4.1-reliability`

Live historical date on a saved production snapshot: **NOT EXECUTED**

## G. Dashboard / single-page consistency

Both Dashboard and 单股分析 call `analyze_one(...)`, which for live dates calls `valuate(...)` once. There is a single `blend = valuate(` in `streamlit_app.py`.

Live Yahoo engine smoke (2026-10-01, 11.17s, 14 Yahoo-family calls for 7 tickers):

| Ticker | confidence | view | DCF executed / reason |
|---|---|---|---|
| AMZN | MEDIUM | Fair value estimate | False / `capex_or_fcf_distortion` |
| NVDA | MEDIUM | Fair value estimate | False / `fcf_conversion_too_low` |
| MU | LOW | Indicative valuation range | False / `normalized_fcf_not_stable_enough` |
| JPM | MEDIUM | Fair value estimate | False / `excluded_by_valuation_class` |
| COIN | LOW | Indicative valuation range | False / `excluded_by_valuation_class` |
| PLTR | LOW | Indicative valuation range | False / `fcf_conversion_too_low` |
| TSLA | SPECIALIZED | No reliable traditional fair value | n/a (fair=None) |

UI copy after allowed fixes:

- MEDIUM: metric **Fair Value Estimate**, caption **Reasonable Range**
- LOW: metric **Indicative Valuation Range**; Reference midpoint is caption-only (not the primary bold Fair Value)
- SPECIALIZED: “传统估值模型不适用，需要专项场景估值。”

Browser walkthrough of Dashboard vs 单股分析 vs DB row: **NOT EXECUTED**

## H. Security status

- `.gitignore` includes `.env` and `.streamlit/secrets.toml`
- Tracked files do not contain `SUPABASE_SERVICE_ROLE_KEY`, real anon keys, passwords, or tokens
- `.streamlit/secrets.toml.example` is placeholders only
- `git ls-files` does not include `.env` / `.streamlit/secrets.toml`; those paths have no commit name history in this clone
- App uses anon key + user JWT, not service_role
- Automated full-history content scan for JWT/service_role blobs was **not** completed (tooling blocked a history grep that could surface credential material). Current tree scan is clean.

## I. Performance observations

Measured locally (engine only, not Streamlit Cloud Dashboard):

- 7 tickers (AMZN NVDA MU JPM COIN PLTR TSLA): **11.17s**
- Yahoo-family calls: **14** (history + fundamentals per ticker)
- Supabase query count: **0** in this smoke (no credentials)

Identified (not optimized this round):

- Dashboard autosave is **N upserts** after **1 watchlist SELECT** (N+1 pattern)
- Each live ticker does history + fundamentals; `@st.cache_data(ttl=900)` should reuse within 15 minutes
- 20-stock Dashboard load: **NOT EXECUTED**

## J. Test matrix

Local unit tests: `python -m unittest tests.test_production_verification tests.test_valuation -q` → **51 OK**

| ID | Scenario | Expected | Result | Evidence |
|---|---|---|---|---|
| PV-01 | migration | V4.1 columns exist in production; ALTER IF NOT EXISTS; no data loss | **NOT EXECUTED** | Repo SQL ready; cloud SQL Editor not run |
| PV-02 | user A login | auth user exists, confirmed, login works | **NOT EXECUTED** | no credentials |
| PV-03 | watchlist insert | AMZN NVDA MU JPM COIN PLTR insert, user_id=A, no 42501 | **NOT EXECUTED** | no credentials |
| PV-04 | watchlist persistence | refresh keeps list | **NOT EXECUTED** | no credentials |
| PV-05 | watchlist delete | delete/re-add/note update | **NOT EXECUTED** | no credentials |
| PV-06 | single nav | first/last disable, next NVDA, jump JPM, `?ticker=NVDA` | **NOT EXECUTED** | code present; no browser |
| PV-07 | manual ticker | AMD analyzes, not auto-added, nav disabled | **NOT EXECUTED** | no browser |
| PV-08 | add manual ticker | AMD joins watchlist, nav updates | **NOT EXECUTED** | no browser |
| PV-09 | snapshot save | fields including model_version=v4.1-reliability | **NOT EXECUTED** | serializer writes fields; no DB |
| PV-10 | snapshot upsert | same-day second save does not duplicate | **NOT EXECUTED** | upsert in code; cloud unique unverified |
| PV-11 | dashboard/single consistency | same `analyze_one` / `valuate` | **PARTIAL** | one valuate path; live UI+DB not compared |
| PV-12 | LOW display | Indicative Valuation Range primary | **PARTIAL** | COIN/PLTR/MU live engine LOW; UI metric fixed; no browser |
| PV-13 | SPECIALIZED display | fair=None, 传统估值模型不适用 | **PARTIAL** | TSLA live SPECIALIZED; no browser for SPCX/BMNR/TEM |
| PV-14 | historical snapshot | no look-ahead recompute | **PARTIAL** | reconstruct unit + `valuate` not called; live date mode not opened |
| PV-15 | legacy snapshot | no crash, old fair, reliability unavailable caption | **PARTIAL** | unit + UI caption; no production legacy row |
| PV-16 | user B isolation | B cannot see A data | **NOT EXECUTED** | no User B |
| PV-17 | cross-user insert blocked | B insert with A user_id rejected | **NOT EXECUTED** | no authenticated B session |
| PV-18 | cross-user update blocked | B cannot update A watchlist | **NOT EXECUTED** | |
| PV-19 | cross-user delete blocked | B cannot delete A watchlist | **NOT EXECUTED** | |
| PV-20 | cross-user select blocked | B select A snapshots empty/denied | **NOT EXECUTED** | |
| PV-21 | remember login | cookie restore, JWT on client, watchlist works | **NOT EXECUTED** | |
| PV-22 | logout clearing | tokens/cookie cleared, refresh cannot read data | **NOT EXECUTED** | |
| PV-23 | multi-session isolation | no cached authenticated client | **PASS** | static: no `@st.cache_resource`; per-session state |
| PV-24 | secret scan | no secrets in repo | **PASS** | gitignore + tracked files + example placeholders; history name scan empty |
| PV-25 | error handling | no user traceback, no secret logs | **PARTIAL** | helpers added; timeout/invalid ticker not live-simulated |
| PV-26 | 20-stock performance | load time + Yahoo/Supabase counts | **NOT EXECUTED** | 7-ticker engine smoke only |
| PV-27 | duplicate protection | unique + upsert | **PARTIAL** | present in SQL/app; cloud constraint unknown |
| PV-28 | model_version storage | v4.1-reliability persisted | **PARTIAL** | payload includes field; no DB readback |
| PV-29 | reliability storage | score/dispersion/json saved and read | **PARTIAL** | serializer + reconstruct; no DB |
| PV-30 | historical reliability immutability | saved score not replaced by today | **PARTIAL** | mock/unit PASS; live app NOT EXECUTED |

**PASS 2 / FAIL 0 / PARTIAL 10 / NOT EXECUTED 18**

## K. Files changed (this verification round)

- `valuation_engine.py` — snapshot reconstruct / legacy detection (no formula retune)
- `streamlit_app.py` — historical reconstruct, timestamps, LOW primary range, explanations, analysis errors, log hygiene
- `supabase_schema.sql` — already contained V4.1 ALTER IF NOT EXISTS (from V4.1 work)
- `supabase_v4_1_production_migration.sql` — **new**, for SQL Editor
- `tests/test_production_verification.py` — **new**
- `tests/test_valuation.py` — V4.1 unit tests from prior layer
- `mag7_monitor.py` — V4.1 wiring from prior layer (not retuned this round)
- `production_verification_baseline.md`
- `production_verification_report.md`
- `production_verification_findings.md`

## L. Manual actions still required

1. Run `supabase_v4_1_production_migration.sql` in production SQL Editor
2. Confirm V4.1 columns and unique indexes on the live DB
3. Create/confirm two independent users (record UUIDs only)
4. Execute User A watchlist + snapshot + nav + remember-login
5. Execute User B isolation and PV-17–PV-20 with **authenticated** (not service_role) session
6. Open 单股分析 in a browser for AMZN / COIN / PLTR / TSLA copy checks
7. Open a saved historical date and confirm values do not move after a local assumption mock
8. Re-run this matrix; only then consider READY FOR BETA

## M. Evidence limitations

- No Streamlit Cloud session was opened
- No Supabase URL/anon key was present locally (`secrets.toml` absent, `.env` absent)
- User A/B UUIDs were not collected
- Yahoo 7-ticker smoke is engine-layer, not Dashboard HTML
- Git history **content** scan for leaked JWTs was not fully executed
- `valuation_snapshots.json` in the repo is a local file snapshot store from the CLI tool, not cloud user data
