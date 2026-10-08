# V4.4 Post-Data Trace Audit

## Evidence scope

Cloud counts supplied by the administrator: NVDA 3/3, ORCL 5/5,
AMZN 4/4, MSFT 5/5 initial/data-valid peers; all unavailable.
No per-peer metrics, target normalized inputs or selection_attempts from
that run were supplied. GOOG Cloud stage counts were not supplied.
These counts establish response availability and freshness, not availability
of forwardPE, evEbitdaTTM, evRevenueTTM, revenueGrowthTTMYoy or
operatingMarginTTM inside AVAILABLE responses. Exact stock-level failures
and alternate-multiple outcomes cannot yet be inferred.

## Exact control flow

`calculate_peer_comparable` continues after unsafe target inputs, insufficient
comparable peers and insufficient peers after outlier removal. It breaks only
after generating positive finite peer valuation prices. It selects the first
successful multiple; it does not optimize across all multiples.
EARLY_EXIT_ON_FIRST_ELIGIBLE_MULTIPLE is absent. Existing production traces
end on success, so they omit later alternatives, not failed eligible attempts.

Enterprise software (ORCL/MSFT): Forward P/E, EV/EBITDA, EV/Revenue.
NVDA: Forward P/E, EV/EBITDA, and EV/Revenue only when target Finnhub
revenue growth is at least 20 percentage points. AMZN/GOOG: Forward P/E
then EV/EBITDA under their existing classes. No mapping or order changed.

## Independent trace implementation

The admin-only report now runs each policy-eligible multiple independently
using the existing engine function's code with a private globals dictionary
whose order callback contains that single multiple. Shared engine globals
and production rules are untouched. All runs reuse the recorder cache and
the same normalized target input; no additional Finnhub requests are needed.
Benchmarks are absent from the audit function.

Each attempt contains candidate/data/multiple/comparability/outlier/final
counts, exact engine reasons, per-peer metrics and comparison booleans, and
target-side inputs. Unexecuted target-blocked stages remain null, not zero.
Independent availability/comparison flags are evidence, not overrides of
the engine's ordered first-failure reason. Outlier is recorded only when the
engine actually ran its outlier filter. Its existing reason is
`peer_excluded_as_outlier` (the combined IQR and median-factor rule).

Diagnostic classification: VALID, TARGET_INPUT_UNSAFE,
INSUFFICIENT_MULTIPLE_DATA, INSUFFICIENT_COMPARABLE_PEERS,
OUTLIER_FILTER_TOO_AGGRESSIVE. These are report labels; the last label
describes a count falling below three after filtering, not evidence that
the production rule should be relaxed.

## Stock conclusions pending Cloud evidence

- NVDA: REVISE (provisional architecture review). Three candidates give no
  redundancy. Which of AVGO/AMD/MRVL is excluded, survivors and whether an
  allowed alternative retains three are not established by 3/3 data counts.
- ORCL: KEEP pending evidence. Five candidates and continued alternate
  attempts are implemented. Exact target/filter failures and the best
  covered multiple remain unknown; early exit is ruled out by source audit.
- MSFT: KEEP pending evidence. Same priority policy as ORCL; it is not yet
  established that their actual failure reasons are the same.
- AMZN: REVISE (provisional architecture review). The engine already flags
  commerce business heterogeneity and caps confidence LOW; that does not
  establish why this particular Cloud run failed.
- GOOG: KEEP pending evidence. META/TTD/PINS/SNAP are distinct candidates;
  Alphabet canonicalization does not delete any of these four. Actual
  growth/margin filtering effects need the Cloud trace.

No architecture rejection or threshold change is justified by the supplied
aggregate evidence. Run the updated Cloud admin page and download
cloud_peer_diagnostic.json to complete the exact NVDA/ORCL exclusions and
five-stock per-multiple outcome table. The page renders that table from
actual captured values; no local fixture values substitute for Cloud data.

## Validation

Added tests cover all attempts after an early success, absence of failed-first
early exit, successful alternate after missing forward multiples, exact peer
exclusions, unsafe target classification, no extra endpoint requests and
unchanged original Peer output. Existing internal blend isolation tests run
in the full suite. No production Peer, normalization, valuation or fallback
implementation was edited.
