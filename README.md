# Stock Fair Value Monitor V3

A Streamlit + Supabase stock research dashboard designed for long-term watchlists.

## Features

- Email/password registration and login using **Supabase Auth**
- Optional **Remember login for 30 days** using a Supabase refresh-session token (the password itself is never stored)
- Private per-user watchlist stored in Supabase
- Add arbitrary US ticker symbols, not only the Magnificent Seven
- Current price, SMA30, SMA50, SMA200
- Approximate one-year volume-density zone
- Three valuation models: Forward P/E, DCF, Growth/PEG
- Blended fair value
- First-entry / core-buy / deep-value zones
- Colored status labels for stocks currently inside a preferred price zone
- Daily valuation snapshots saved to Supabase
- Historical chart of price vs saved fair value
- Historical-date analysis that avoids look-ahead bias

## Security design

Do **not** store plaintext passwords in your own table.

This project uses Supabase Auth. Passwords are processed by Supabase Auth and are not written to `profiles`, `watchlist`, or `valuation_snapshots`.

The app uses the public **anon key** plus Row Level Security (RLS). Never put the Supabase `service_role` key in this Streamlit app or in GitHub.

The Remember Me feature stores a Supabase refresh-session token in the browser for up to 30 days. It does **not** store the user's password.

## 1. Create a Supabase project

Go to Supabase and create a project.

In **Authentication → Providers → Email**, enable email/password authentication.

Choose whether you want email confirmation enabled:

- ON: users must confirm their email before first login.
- OFF: users can sign in immediately after registration.

## 2. Create database tables

Open **SQL Editor** in Supabase and run:

`supabase_schema.sql`

This creates:

- `profiles`
- `watchlist`
- `valuation_snapshots`

and RLS policies so each user can only access their own records.

## 3. Configure local secrets

Copy:

```text
.streamlit/secrets.toml.example
```

to:

```text
.streamlit/secrets.toml
```

Then fill in:

```toml
SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_ANON_KEY = "YOUR_SUPABASE_ANON_KEY"
```

These values are available in Supabase project settings / API keys.

The anon key can be used by a browser/server app when RLS is configured correctly. Do not use `service_role` here.

## 4. Install and run

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## 5. Deploy to Streamlit Community Cloud

Push the project to GitHub, but do **not** commit `.streamlit/secrets.toml`.

In Streamlit Cloud project settings, add these secrets:

```toml
SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_ANON_KEY = "YOUR_SUPABASE_ANON_KEY"
```

Then deploy `streamlit_app.py`.

## Watchlist colors

- 🟢 Dark/light green: deep-value or core-buy zone
- 🟡 Amber: first-entry zone
- 🔵 Blue: within ~5% of the first-entry zone
- ⚪ Gray: observe / wait for pullback
- 🔴 Red: data unavailable

## Valuation assumptions

The Magnificent Seven have ticker-specific assumptions in `mag7_monitor.py`.

Other tickers are supported using transparent generic assumptions so they can still be tracked. For serious use, add ticker-specific assumptions to `ASSUMPTIONS` in `mag7_monitor.py`.

Default blend:

- P/E model: 35%
- DCF model: 40%
- Growth/PEG model: 25%

## Historical valuation

Historical OHLCV data can be reconstructed later, but historical analyst expectations cannot. To avoid look-ahead bias, the app stores valuation snapshots in Supabase and uses the latest snapshot that existed on or before the selected date.

## Disclaimer

This is a research and monitoring tool, not personalized investment advice. Fair value depends heavily on future earnings, growth, capital expenditure, margins, discount rates and valuation multiples.

## V4.3 External Valuation Sanity Layer

The analysis service exposes `market_reference` (MarketReferenceResult), numeric
`valuation_low/mid/high`, `valuation_mode`, and a separate nullable confidence.
Internal valuation formulas and engine outputs are unchanged. Legacy snapshot
confidence encoding is retained for compatibility; presentation normalizes it.

Yahoo Finance / yfinance ticker.info supplies targetMeanPrice, targetLowPrice,
targetHighPrice, numberOfAnalystOpinions and forwardPE. Consensus never enters
internal model weighting. Provider update dates, historical PE medians and sector
PE are unavailable from this feed and remain null; retrieval time is not an
estimate update time. Historical analysis does not fetch current consensus.

Deviation = (internal midpoint / consensus target - 1) * 100 percentage points.
Absolute deviation <20 is NORMAL, 20 through 35 is REVIEW, >35 is
HIGH_DIVERGENCE. Missing reference or internal midpoint is
NO_EXTERNAL_REFERENCE and does not penalize valuation. A high divergence is a
review warning, not proof that either estimate is correct.

Dashboard: internal valuation, consensus target, signed deviation, valuation mode
and confidence replace the standalone fair-value presentation. Advanced columns
include current/implied forward PE and optional historical/sector references.
LOW + HIGH_DIVERGENCE hides dashboard trading zones; numeric internal zones are
preserved. Single-stock diagnostics explain source, missing update dates, PE and
rule-derived zones. Display prices use two decimals; LOW ranges use integers.

Validation: python -m unittest discover -s tests -v (220 tests passed).
No live provider or interactive browser validation was performed.


### Finnhub live market reference provider

Current live analyses use the independent Finnhub adapter in
`market_reference_provider.py`, via GET
`https://finnhub.io/api/v1/stock/price-target?symbol=TICKER`.
The app reads `FINNHUB_API_KEY` from the environment, then Streamlit secrets.
Copy the placeholder in `.streamlit/secrets.toml.example` into deployment secrets;
never commit the actual key. The configured account must have endpoint access.

Provider results contain ticker, target_mean/high/low, analyst_count,
last_updated, source, source_status and a sanitized error. Finnhub's targetMean,
targetHigh, targetLow and lastUpdated map directly; numberAnalysts is used only
when supplied. Missing analyst counts/dates remain null.

The process-wide provider caches public results by normalized ticker for 12 hours
(success/no-data), and transient errors for 60 seconds. Requests are serialized
and spaced 1.1 seconds apart; HTTP 429 activates a shared cooldown of at least
60 seconds (respecting numeric Retry-After up to one hour). Existing valid cache
entries remain usable during cooldown. Cache is in-memory per application worker;
worker restarts clear it. Credentials are neither cache keys nor cached values.

States distinguish NOT_CONFIGURED, NO_DATA, RATE_LIMIT, NETWORK_ERROR,
INVALID_SYMBOL, AUTH_ERROR, ACCESS_DENIED and PROVIDER_ERROR. Dashboard shows
explicit state labels rather than a generic dash. Historical analyses do not
fetch current targets. Single-stock summaries show consensus, range, deviation,
source/update date and high-divergence warnings even for specialized valuations.

Provider data is joined after internal valuation and zone calculations, without
changing financial normalization or feeding analyst targets into model inputs.
Validation includes injected HTTP responses, cache expiry/cooldown, safe errors,
and end-to-end analysis comparisons with and without external references.

### Temporary administrator Finnhub audit

The account menu shows `Finnhub 能力诊断` only for a server-verified Supabase
user whose email matches `ADMIN_EMAIL` in Streamlit Secrets. Configure the
administrator's actual login email in Cloud Secrets; an empty value disables
access. User metadata and session email labels are not used for authorization.

The diagnostic fails closed outside Community Cloud's `/mount/src` application
checkout. It reads the Finnhub key directly from `st.secrets`, calls the audit
core in-process, and never invokes a shell or writes report files. Reports live
only in the administrator's session, bound to the verified user ID. JSON/CSV
exports are generated in memory after defensive credential redaction.

Click the account menu → Finnhub 能力诊断 → 开始能力诊断. The seven required
symbols run sequentially with >=1.2 seconds between calls. The first rate limit
stops the run. A process lock prevents overlapping diagnostics and a five-minute
cooldown limits repeated runs. Downloads and rerenders do not repeat API calls.
Table rows group each capability by its observed status; untested pairs are
omitted, and Coverage uses the seven-symbol denominator. A full run includes
105 requests and may take several minutes depending on response times.

Local validation covers access denial, verified email/user-ID matching,
Cloud-only execution, session-owner isolation, exports, redaction, cooldown,
execution button behavior and the existing application's regression suite.
Cloud verification still requires deploying these uncommitted files through the
normal deployment process and configuring `ADMIN_EMAIL`; no Cloud deployment
or live-account audit is implied by the local tests.

## V5.5 — Finnhub Free Data Integration

The Cloud capability audit supplied for this release confirms quote, company
profile, company news, basic metrics, earnings calendar (partial symbol coverage),
earnings surprises and recommendations. V5.5 production code enables only those
seven endpoint families through `finnhub_service.FinnhubProvider`. This section
supersedes earlier live price-target integration instructions. Target adapters
remain available for explicitly injected comparisons and administrator audits;
the normal analysis path never requests price targets or earnings/revenue
estimate endpoints. Dashboard consensus target/deviation columns are hidden.

### Data boundaries and caching

Yahoo and the existing financial pipeline remain primary for historical prices,
SMA, valuation inputs, model math, MOS, zones and reliability. Finnhub results
contain `source`, `fetched_at`, `status` and selected `data`. No Supabase client,
user token, key or watchlist ownership state is cached. Environment variables
and Streamlit Secrets supply the key through the existing safe loader.

Endpoint TTLs: quote 10 minutes; company profile 24 hours; company news 20
minutes; basic financials and earnings calendar 8 hours; earnings surprises
24 hours; recommendations 12 hours. Cache is process-local and precedes news
filtering. All uncached calls are serialized and spaced at least 1.2 seconds
apart. A transient network/5xx failure retries once. HTTP 429 activates a shared
cooldown (at least 60 seconds) with no immediate retry; cached results remain
usable. Error strings never include raw responses or credentials.

### Headlines and calendar

Production 头等大事 uses real company-news for the selected watchlist/time
window and the earnings calendar for upcoming events. Demo/static data remains
behind explicit `NEWS_DEMO_MODE=true`. The default view remains the whole
watchlist; existing single-stock links apply a ticker filter.

News windows use London time: rolling 24 hours, Monday-to-now, quarter-start-to-
now. Exact timestamps exclude future news, and requests never exceed 100 days.
Filtering requires a related ticker match, a valid source URL and timestamp;
Alphabet aliases are supported. Deduplication removes tracking-query URL copies,
identical normalized headlines and near-identical syndicated headlines per
company. Ordinary price moves, analyst target chatter and speculative previews
are filtered. Rule-based event types/importance cover earnings, guidance,
regulation, M&A, contracts, capex, management, products, competition and legal
matters. Importance score then publication time controls ranking; ticker caps
are 2/3/5 for 24 hours/week/quarter.

Chinese structured summaries describe the classified topic, quote the original
headline and distinguish potential effects from confirmed facts. They do not
translate full articles or infer new numbers. Cards retain original news URLs,
publisher attribution via Finnhub, why it matters and two follow-up checks.

Calendar requests cover the next 30 days and are cached across watchlists, with
results filtered to the current user's symbols. Only future-dated entries are
shown, with date, pre/post-market timing, fiscal quarter and available calendar
EPS/revenue estimates. These embedded calendar fields do not call the paid
estimate endpoints. A missing symbol/date is explicitly shown as Finnhub 暂无该公司
未来财报日期; no date is inferred. Single-stock teasers show one highest-priority
recent event and preserve the ticker-filtered navigation link.

### Single-stock external reference

A compact 外部市场参考 block follows internal valuation and business financials.
It shows company metadata (market capitalization and shares in Finnhub's million
units), recent four-period recommendations, recent four-quarter EPS surprises
and selected metrics: explicit forwardPE if available, peTTM, pbAnnual, roeTTM,
operatingMarginTTM, revenueGrowthTTMYoy, epsGrowthTTMYoy, 52WeekHigh/Low and beta.
Missing forward PE is not replaced by normalized/trailing PE. Recommendations
are counts and sentiment context, not system trading instructions. EPS beat
counts do not imply future returns or revenue surprises.

Quote is a read-only sanity reference: >2% discrepancy warns about timestamps.
When the primary price is missing, Finnhub's quote is explicitly labeled as an
external fallback reference in this block; historical indicators/internal
valuation are not synthesized or overwritten. Forward-PE/ROE discrepancies
>25% warn about period/definition differences and never replace internal data.
Each module handles unavailable/limited data independently. Without a key, the
external block is hidden and Headlines says 实时新闻源未配置。

### Validation

The full unittest suite, including V5.5 provider/news/calendar/isolation tests,
passes. A Streamlit AppTest renders all three external-reference tables and
sanity warnings with fixtures. Baseline comparison against the previous commit
confirms identical fair values, ranges, confidence, buy/exit zones, reliability
and dispersion for AAPL/MSFT/NVDA/AMZN/GOOG/JPM/TSLA. Local credentials are absent;
these checks do not claim live Cloud API validation. No Auth/RLS, ownership,
valuation engine or financial normalization changes were made.
