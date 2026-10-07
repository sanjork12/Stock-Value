# V4.4 diagnostic isolation investigation and repair

## Evidence and limits

Compared pre-V4.4 commit `e44131863ae02184832f2f36ca64ac09dd57372f`, V4.4 commit `4621369b196fe3321c396d582a98ff3e1bf7e564`, and the local repair. The audit loads each revision's analysis service and valuation engine directly from Git, without changing the checkout. Every revision receives identical financial and price inputs.

The reported Cloud Dashboard CSV and the financial inputs used to produce it were not provided. Git commits contain code, not those historical market responses. Consequently the numeric results in `v44_isolation_regression.json` are **synthetic replay results, not recovered historical Dashboard values**. The actual Cloud regression root cause remains unconfirmed; no live recovery is claimed.

With complete synthetic EPS inputs, all 14 tickers produce identical internal results in pre-V4.4, current V4.4 and the repair: AMZN, AAPL, AVGO, GOOG, JPM, META, MSFT, MU, NVDA, ORCL, PLTR, COIN, CRCL and UBER. The JSON records each version's low/mid/high, fair value, confidence, valuation mode, included models, reliability/model counts, dispersion, trading zones, status and peer result.

For the six reported tickers, replay midpoints and modes are identical across all three versions:

- NVDA: 94.31226717592534, MEDIUM, STANDARD.
- AVGO: 114.43357515599052, MEDIUM, STANDARD.
- MU: 99.73599999999999, MEDIUM, STANDARD.
- PLTR: 25.019878914956077, LOW, LOW_CONFIDENCE.
- COIN: 156.50249665018373, LOW, LOW_CONFIDENCE.
- CRCL: 86.21, LOW, LOW_CONFIDENCE.

These numbers only identify the fixed-input replay. They must not be substituted for real current or historical valuations.

A second replay removes quote-currency forward and trailing EPS while retaining statement EPS. All six tickers return UNAVAILABLE with `forward_and_trailing_eps_unavailable` **already in pre-V4.4**, as well as in V4.4 and the repair. This establishes an existing input-dependent explanation matching the affected class pattern; it does not establish that Cloud actually received those inputs. No EPS guard, normalization rule or model assumption has been relaxed.

## Isolation defect and repair

Although ordinary fixed-input replay did not reproduce the reported Cloud difference, V4.4 had an avoidable isolation hazard: diagnostic calculation ran before internal valuation and received the same mutable normalized financial dictionary. Its exception handler could not undo a prior mutation to that dictionary. A deliberately injected peer callback that clears its input and then throws makes the old V4.4 pipeline unavailable. The repaired pipeline preserves the pre-V4.4 internal output under the same injected fault. This is a fault-injection demonstration, not a claim that the shipped peer calculator performed that mutation in Cloud.

Diagnostic calculation now runs **after** internal valuation, confidence/reliability, buy/exit zones, recommendation and valuation display policy are finalized. It receives a deep copy of financial inputs and never receives the result, blend or model dictionary. Only two fields are appended:

- `peer_comparable_result`: the separate serialized result, or null on diagnostic failure.
- `peer_diagnostics`: mode, availability and a sanitized failure warning.

Calculation, import and serialization errors only mark the peer sidecar unavailable. The UI displays `Peer Comparable: Unavailable`; internal `STANDARD`/`LOW_CONFIDENCE` and confidence remain untouched. Legacy `peer_comparable`/`peer_model_mode` result additions are replaced by the requested sidecar names, and their single-stock UI consumer is updated.

The active-only branch remains explicit. Diagnostic mode passes no peer result to the valuation engine. `valuation_engine.py` is unchanged by this repair.

## Model count, applicability and formula audit

- `included_models` and the model dictionary are finalized by the internal engine before diagnostics.
- `model_count_total`, `model_count_valid`, `model_count_included` and `model_count_excluded` are identical with diagnostic on/off.
- Diagnostic values cannot enter dispersion, outlier detection, reliability, MOS, or either zone eligibility function.
- Peer forward-EPS provenance checks and peer-data availability gates only operate on the independent copy.
- A peer rejection of a `price/forwardPE` EPS source leaves the original internal P/E applicability rule unchanged.
- Dashboard status is `recommendation`; the invariant audit maps it to the report's `status`. Existing `zones`/`exit_zone` are reported as `buy_zones`/`exit_zones` without changing their production keys.
- PE ranges, DCF assumptions, growth caps, valuation classes, financial normalization, MOS and reliability formulas were not modified.

## Verification

`python -m unittest discover -s tests -v`: **347 tests, 0 failures, 0 errors**, including 17 new dedicated diagnostic-isolation tests. Existing peer tests were updated to read the two requested sidecar fields. Real Streamlit peer-widget verification also passes.

The dedicated tests cover all ten requested cases, all 14 tickers, full model/reliability equality, valid-but-extreme peer ranges, unavailable peers, input and nested-input mutation, failures during import/calculation/serialization, preservation of EPS applicability, append-only field ownership and execution order after display policy.

Reproduce the three-version replay:

```powershell
python scripts/verify_peer_isolation.py
```

To replay actual financial inputs when available, provide a JSON file with a `tickers` mapping from ticker to the financial dictionary used by the original analysis, and a `description` stating provenance:

```powershell
python scripts/verify_peer_isolation.py --inputs path/to/captured_financials.json --output output/actual_peer_isolation.json
```

A Dashboard CSV alone can validate exported values and statuses, but does not recover missing provider inputs. The script's synthetic price history fixes volatility/technical inputs; an exact historical zone replay would additionally require the original price history. The report does not conflate those limits with a proven production root cause.

No push performed. Changes remain local for review and Cloud verification after a separately authorized deployment.
