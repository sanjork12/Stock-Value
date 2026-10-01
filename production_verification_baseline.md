# V4.1 Production Verification Baseline

Recorded **before** any verification-only code changes.

Date (local): 2026-10-01

## Identity

| Item | Value |
|---|---|
| git commit hash (HEAD) | `136246ca1a7c80b7607314237d6f21a4524b8297` |
| branch | `main` |
| HEAD subject | Add sector-aware V4 valuation engine and watchlist single-stock navigation. |
| working tree | dirty: uncommitted V4.1 reliability layer (`mag7_monitor.py`, `streamlit_app.py`, `supabase_schema.sql`, `tests/test_valuation.py`, `valuation_engine.py`) |
| Python | 3.14.2 |
| Streamlit | not installed in the default interpreter used for this baseline (`ModuleNotFoundError: supabase`; `pip show` not executed against a project venv at baseline time). Declared in `requirements.txt`: `streamlit>=1.50` |
| supabase-py | not installed in the default interpreter. Declared: `supabase>=2.18` |
| yfinance | importable via project modules used in prior V4.1 work; declared: `yfinance>=0.2.66`. Exact installed version at baseline: **NOT CAPTURED** (default interpreter missing supabase stack) |
| deployment environment | local Windows 10 (`win32 10.0.22621`), PowerShell. Production target is Streamlit Community Cloud + Supabase (per README). **Cloud runtime version: NOT EXECUTED** |
| model_version (code) | `v4.1-reliability` (`valuation_engine.MODEL_VERSION`) |
| database schema version | no dedicated schema-version table in repo. Schema is defined by `supabase_schema.sql` (profiles / watchlist / valuation_snapshots + V4/V4.1 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`) |
| `supabase_schema.sql` SHA-256 | `298be6a82d98aacaeff6e17158a55bb9c92e2ddd56cfdf6c111dc06316bfadc8` |
| local `.streamlit/secrets.toml` | **absent** |
| local `.env` | **absent** |

## Post-baseline verification-only edits

After this baseline was recorded, allowed verification fixes were applied (snapshot reconstruction, legacy caption, LOW range primary metric, timestamps, analysis error wrapping, login log hygiene). Valuation class architecture, PE/DCF/MOS/SMA formulas were **not** retuned.

Do not treat those later edits as part of HEAD `136246c`.

## Baseline notes

- This file is an append-only verification artifact. Do not overwrite later; add a new section or a dated file instead.
- Cloud migration status, live User A/B IDs, and Streamlit Cloud package versions are **not** part of this baseline because they were not queried against production at record time.
- Uncommitted V4.1 work is the candidate under verification; HEAD `136246c` is V4 without the reliability layer.

## Package pins (`requirements.txt`)

```
streamlit>=1.50
supabase>=2.18
extra-streamlit-components>=0.1.81
yfinance>=0.2.66
pandas>=2.2
numpy>=2.0
```
