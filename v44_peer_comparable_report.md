# Stock-Value V4.4 — Peer Comparable Valuation Layer

## A. Files changed

- `peer_comparable.py`: independent result, business groups, data gates, robust multiples, provenance and configuration.
- `finnhub_service.py`: expose four additional free Basic Financials fields: forward PEG, EV/EBITDA, EV/Revenue and market capitalization.
- `valuation_engine.py`: opt-in additional model and conservative weight allocation; existing assumptions and reliability/MOS/zone formulas retained.
- `analysis_service.py`: prepare peers before the single valuation call, isolate external failures, and omit current peer data from historical analysis.
- `peer_comparable_ui.py`, `streamlit_app.py`: single-stock valuation diagnostics, inclusion/exclusion details, freshness and JSON download.
- `scripts/report_peer_comparable.py`: repeatable five-stock JSON/CSV comparison.
- `scripts/verify_v44_ui.py`, `tests/test_peer_comparable.py`: real Streamlit widget verification and model regression coverage.
- `reports/v44_reference_context.json`, `reports/v44_peer_comparison.json`, `reports/v44_peer_comparison.csv`: user-supplied report context and local validation output.

## B. Peer group architecture

Groups use curated business families plus peer-only class compatibility. These tags do not change the existing valuation classes. ORCL/MSFT use enterprise software; GOOG/META use digital advertising; AMZN/BABA use commerce; AAPL uses devices. Banks, growth semiconductors, high-growth software and memory-cycle businesses have separate groups.

The semiconductor candidate pool adds MRVL alongside NVDA/AVGO/AMD. This supplies a possible third independent peer after excluding the target, but MRVL must still pass the same profitability, growth and margin gates. ANET is not a main semiconductor peer. WDC/STX are tagged storage hardware and excluded from MU's memory comparison; MU can remain unavailable. Alphabet aliases collapse to GOOG, and the target is always excluded.

## C. Multiple selection rules

- Mega-cap: Forward P/E, then EV/EBITDA. Enterprise software also permits EV/Revenue.
- Growth semiconductor: Forward P/E, EV/EBITDA; EV/Revenue only when target revenue growth is at least 20%.
- High-growth software: EV/Revenue first. Forward P/E requires three positive target historical EPS observations and nonnegative peer EPS growth with positive margins; otherwise it is skipped. EV/EBITDA is the final alternative.
- Bank: P/B with a target/peer median ROE adjustment bounded to 0.75–1.25, then trailing P/E; no EV multiple.
- Cyclical semiconductor: EV/EBITDA only in this version, avoiding spot Forward P/E.

Forward P/E requires an existing recognized forward EPS source; statement-derived EPS and price/forwardPE inference cannot drive this model. EV conversion is `(metric × peer multiple + cash − debt) / canonical shares`. Missing cash/debt/shares never become zero. Existing currency gates apply to statement-based metrics. A corrected canonical share count remains usable when a class-specific raw share count was rejected.

## D. Inclusion and exclusion

Each peer must have positive market cap and selected multiple, compatible business and class tags, and known comparable revenue growth and operating margin. Differences over 50 and 25 percentage points respectively are excluded. P/E and EV/EBITDA require positive target/peer TTM P/E. EV/Revenue separates positive-margin and loss-making cohorts. P/B requires positive ROE. Every excluded candidate has a reason; fallback attempts retain their own inclusion/exclusion history in provenance.

Only `stock/profile2` and `stock/metric` are requested by this layer. Requests remain serial through the existing cached provider. A rate limit stops further requests in that peer calculation and marks remaining candidates. Network failures are isolated and do not remove the internal valuation.

## E. Outliers and confidence

Use linear-interpolated Q1/Q3 and the median, never the mean. Remove values outside 1.5×IQR fences or outside one-third to three times the median; recompute quantiles after removal. Fewer than three survivors means unavailable. Three or four survivors are at most MEDIUM. HIGH requires at least five and IQR/median below 25%; dispersion above 60% is LOW. Device and commerce groups are capped at LOW because of business-mix differences.

Profile/metric retrieval timestamps, per-peer age and source are recorded. Data older than 72 hours or with unknown/invalid timestamps are rejected with warnings. Retrieval time does not establish the underlying financial reporting period; the UI explicitly discloses that limitation.

## F. Diagnostic and active behavior

Default `PEER_MODEL_MODE=diagnostic` computes and displays the result without adding it to the existing blend. Environment configuration takes precedence over Streamlit Secrets; unknown values resolve to diagnostic. Default mode preserves fair value, reliability, MOS and buy/exit zones. Existing classification, PE ranges, growth caps, DCF assumptions, financial normalization, Auth/RLS and watchlist ownership are unchanged.

Explicit `PEER_MODEL_MODE=active` gives valid peer results 15% for mega-cap/banks, 20% for growth semiconductors/mature growth, and 15% for other supported classes. Surviving existing weights retain their relative proportions and occupy the remaining weight. An invalid peer, mismatched ticker/class or absent valid existing model does not supply a standalone official valuation. The existing reliability and zone functions process the resulting model set.

## G–I. Five-stock results and benchmark comparison

Local validation on 2026-10-07 found no configured Finnhub credential. The key is configured in Streamlit Cloud, which has not been deployed or exercised during this local-only task. Therefore NVDA, ORCL, MSFT, GOOG and AMZN all have **unavailable current peer ranges**, no included live peers and no claimed benchmark direction. The JSON contains each candidate's explicit `NOT_CONFIGURED` exclusion and full unavailable result; CSV contains the five comparison rows. The report also leaves current internal recalculation empty, avoiding unrelated live financial requests without Finnhub configuration.

User-supplied context is retained separately: NVDA internal approximately 372 / benchmark 300; ORCL 238 / 180; MSFT 656 / 544; GOOG 253 / 345; AMZN 285–290 / 285. These are report context, not current observations or model inputs. No benchmark-fitting conclusion is justified until a configured run produces valid peer values. At that point the reporting utility compares absolute deviations and reports CLOSER/FURTHER/UNCHANGED.

To regenerate in a trusted environment with configured secrets:

```powershell
python scripts/report_peer_comparable.py --reference-file reports/v44_reference_context.json
```

The command imports core functions directly and never prints credentials. A local CLI does not inherit Streamlit Cloud secrets. On Cloud, authenticated users can inspect and download the single-stock peer diagnostics once this version is deployed; deployment is outside this no-push task.

## J. Validation

The full unittest suite and the real Streamlit peer-widget verification are run locally. Coverage includes business groups, alias de-duplication, minimum survivors, exact quantiles, outliers, forward EPS provenance, EV equity conversion/canonical shares/currency gates, bank rules, diagnostic identity, active weights, history isolation, request endpoint restrictions, rate-limit stop behavior, provenance, report unavailability and isolated transport failure. Synthetic fixtures verify arithmetic and behavior; they are not live market results. The final test count and commit hash are supplied in the completion message.

## K. Version control

Local commit only. No push is authorized for this V4.4 task. The completion message identifies the resulting commit; generated validation files above are included explicitly, while unrelated existing output files remain untracked.
