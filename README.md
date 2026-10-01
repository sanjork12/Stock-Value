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
