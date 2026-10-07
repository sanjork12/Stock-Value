# V4.4 Cloud Financial Input Forensics — implementation and local findings

## Scope and execution status

Read-only instrumentation and a temporary administrator UI are implemented locally. No valuation assumptions, applicability rules, normalization logic or fallback decisions were changed. No commit or push performed.

Actual public Yahoo inputs were successfully captured locally for AVGO, NVDA, MU, PLTR, COIN, CRCL, AMZN and MSFT. Files are under `output/financial_input_forensics/`, excluded from Git. The aggregate A–I report is `output/financial_input_forensics/forensics_report.json`. These are real local captures, not the previous synthetic isolation fixtures.

**No actual Cloud financial snapshot has been captured in this task.** New code has not been deployed because commit/push are prohibited. Cloud Secrets remain on Cloud. Do not interpret local replay, simulated Cloud tests or missing Cloud files as evidence of a confirmed Cloud data bug.

## What is captured

`analysis_service.analyze_ticker` has an optional diagnostic sink. Immediately before its single `valuation_engine.valuate` call, it builds an independent snapshot and invokes the sink. This is enabled only for the diagnostic runner. The snapshot is never attached to ordinary user results. Observer and sink failures cannot change the original financial dictionary or internal valuation.

The request-local observer captures only allowlisted public numeric fields and currency codes from the existing Yahoo `get_info`, `info`, `fast_info` and earnings-estimate paths. It records attempted statement paths, known row availability and periods. It does not request new Yahoo paths or alter the existing path-selection behavior. The metadata is reset after each capture.

The final snapshot contains the requested Market, EPS, Shares, Cash flow, Balance sheet, Growth, Currency and Profile sections. Each field includes value, source category, raw source name and status. Raw Yahoo EPS remains distinguishable from normalized statement-derived trailing EPS. Raw CapEx and normalized outflow are separate. Missing cash/debt converted to zero by the existing loader is explicitly tagged `fallback_missing_assumed_zero`; this instrumentation does not correct that behavior. Unknown currencies are explicitly marked UNKNOWN rather than treated as proven alignment.

Pre-valuation model applicability is evaluated using the existing gate functions on another copy. Execution is initially false. After the engine finishes, the snapshot adds the actual executed/valid/included flags, model reasons, model count and exact final failure reason. Missing-input lists describe checked alternatives; they do not falsely claim every listed field is independently mandatory.

`normalized_growth` observes the existing growth-cap helper without modifying it. `normalized_fcf` is the existing loader's selected normalized FCF. `free_cash_flow` is the latest statement FCF, or the existing info TTM value when annual data is absent. These are not interchangeable periods.

## Local findings

All eight local captures have genuine positive forward EPS from Yahoo and an implied-shares-based canonical denominator. All eight have four existing-engine FCF observations (annual/TTM deduplication follows the original engine). Local Finnhub is NOT_CONFIGURED; no Cloud API key was copied to this machine.

- AVGO / NVDA: STANDARD, two valid models. DCF excluded for `fcf_conversion_too_low`.
- MU: LOW_CONFIDENCE, two valid models. Normalized P/E excluded as an outlier, DCF for `normalized_fcf_not_stable_enough`, Growth by valuation class.
- PLTR: LOW_CONFIDENCE, three valid models. DCF excluded for `fcf_conversion_too_low`.
- COIN: LOW_CONFIDENCE, two valid models. Yahoo trailing EPS is missing in this capture; the normalized trailing value is explicitly `statement_derived`. A real Yahoo forward EPS is available, so the statement-only official-valuation guard does not block the final result. Revenue multiple is an outlier; DCF is excluded by class.
- CRCL: LOW_CONFIDENCE, two valid models. Revenue multiple is an outlier; DCF is excluded by class.
- AMZN: STANDARD, two valid models. DCF excluded for `capex_or_fcf_distortion`.
- MSFT: STANDARD, two valid models. DCF excluded as an outlier.

Exact price, EPS values/sources, canonical shares/sources, normalized FCF, counts, excluded models and availability are recorded per ticker in the aggregate JSON and individual local snapshots. Their timestamps are capture timestamps; the market price is the last daily history close, not necessarily a live intraday quote.

## A–G investigation

- A: snapshot retains observed raw `forwardEps` and `trailingEps` separately from normalized inputs. It records actual yfinance paths; it does not assert an unobserved underlying Yahoo HTTP endpoint.
- B: a separate diagnostic-only Finnhub `stock/metric` projection records `epsTTM`, `forwardPE`, `peTTM` and market cap. It never feeds valuation. Local credentials are absent; Cloud availability must be measured by the administrator run.
- C: raw `impliedSharesOutstanding`, normalized canonical shares and the chosen denominator source are all captured.
- D: actual FCF periods/values and existing-engine observation count support local/Cloud comparison. Cloud count remains unknown until captured.
- E: each attempted cashflow/income/balance-sheet path records allowed row presence/missingness and date columns. This distinguishes empty data, different periods and different response paths.
- F: raw currency fields and the chosen path are recorded. `currency_mismatch=false` with either currency absent is marked UNKNOWN, not proof of matched currencies.
- G: final `forward_and_trailing_eps_unavailable` is reported as a correct guard decision **for the captured inputs**, independently of whether a provider/path bug caused those inputs to be missing. No forced valuation recovery occurs.

A controlled partial-info test reproduces an important path limitation: when `get_info()` returns a nonempty partial dictionary lacking EPS/currencies, the existing loader does not attempt `.info`; empty earnings estimates then leave statement EPS as the fallback, and the original guard can correctly block affected classes. This is test evidence of the existing path behavior, not proof that it happened on Cloud. No path fallback was changed this round.

## Administrator workflow

After this local code is deployed through a separately authorized process, the existing account menu shows **财务输入诊断** only on Streamlit Community Cloud for the verified server-side authenticated `ADMIN_EMAIL`. Execution, rendering and downloads each recheck authorization. Session reports are owner-bound and cleared for non-admin sessions. There is no role-metadata bypass.

Select a ticker and click **Run diagnostic**. The page shows Field / Value / Source / Status, actual model applicability and `UNAVAILABLE because` with valid/included model counts and model reasons. Download filename is `cloud_financial_diagnostic_<ticker>.json`. No file is written on the Cloud server or uploaded to GitHub. Downloaded Cloud filenames are also Git-ignored if placed in the checkout.

An optional local-snapshot uploader compares the public financial fields using schema projection. It does not echo arbitrary uploaded keys or free-form strings. Full trusted exported-snapshot comparison also includes statement path/row/period metadata and final model counts/reasons:

```powershell
python scripts/capture_financial_inputs.py --local output/financial_input_forensics/local_financial_diagnostic_NVDA.json --cloud path/to/cloud_financial_diagnostic_NVDA.json
```

Output includes field, local/cloud values and sources, difference and severity: CRITICAL / MATERIAL / MINOR / SAME. Captures should be taken close in time; normal market changes and differing reporting periods must not be mistaken for missing-data regressions.

## Fallback boundaries

No Finnhub fallback is enabled. A future `epsTTM` fallback would require verified issuer, share class, currency, units, reporting window, split adjustment and accounting basis. `forwardPE` is a reference multiple, not an independently observed forward EPS. Finnhub share counts/market caps require their unit contract to be verified before any use.

Do not silently substitute statement annual EPS for forward EPS, infer trusted forward EPS from a multiple, use class-specific shares as canonical shares, assume unknown currency is USD, assume absent cash/debt/FCF is zero, or mix FY and TTM measurements. Existing loader zero fallbacks are exposed as evidence only, not expanded or repaired here.

Confirmed Cloud data bugs: **not yet determined**. Correct Cloud guard blocks: **not yet determined**. Real local inputs are available for all eight tickers; each actual Cloud root cause awaits the matching downloaded snapshot.

## Local verification

Full suite: `python -m unittest discover -s tests -v` — **367 tests, 0 FAIL, 0 ERROR**. Twenty new forensic tests cover capture order, absence from ordinary result payloads, observer/sink isolation, actual Yahoo paths and statement periods, partial-info behavior, earnings-estimate provenance, unchanged loader output, non-use of Finnhub fallbacks, explicit zero-fallback provenance, comparison severities, administrator authorization, session ownership, upload projection and credential redaction.

`python scripts/verify_cloud_forensics_ui.py` passes with real Streamlit widgets and explicit mocked Cloud authorization/data. It verifies the eight-ticker selector, Run diagnostic, failure trace, field/model tables, local upload widget and JSON download. This is local UI verification, not a real Cloud capture.
