-- V4.1 production migration
-- CLOUD MIGRATION = NOT EXECUTED from the 2026-10-01 verification runner.
-- Safe to re-run. Does NOT drop tables. Does NOT disable RLS. Does NOT use service_role.
-- Execute in Supabase SQL Editor against the production project, then re-verify PV-01.

-- Keep owner-scoped unique keys if an older database was created without them.
create unique index if not exists watchlist_user_ticker_uidx
  on public.watchlist(user_id, ticker);
create unique index if not exists snapshots_user_ticker_date_uidx
  on public.valuation_snapshots(user_id, ticker, snapshot_date);

-- V4 / V4.1 snapshot columns. Legacy rows remain readable with NULL values.
alter table public.valuation_snapshots add column if not exists valuation_class text;
alter table public.valuation_snapshots add column if not exists confidence text;
alter table public.valuation_snapshots add column if not exists models_json jsonb;
alter table public.valuation_snapshots add column if not exists model_version text;
alter table public.valuation_snapshots add column if not exists reliability_score numeric;
alter table public.valuation_snapshots add column if not exists dispersion_pct numeric;
alter table public.valuation_snapshots add column if not exists blended_low numeric;
alter table public.valuation_snapshots add column if not exists blended_high numeric;
alter table public.valuation_snapshots add column if not exists volatility_1y numeric;
alter table public.valuation_snapshots add column if not exists reliability_json jsonb;

-- Recreate a single authenticated-only policy set. Duplicate historical names are dropped first.
alter table public.profiles enable row level security;
alter table public.watchlist enable row level security;
alter table public.valuation_snapshots enable row level security;

drop policy if exists "profiles_select_own" on public.profiles;
drop policy if exists "profiles_insert_own" on public.profiles;
drop policy if exists "profiles_update_own" on public.profiles;
drop policy if exists "profiles_delete_own" on public.profiles;
drop policy if exists "Users can view own profiles" on public.profiles;
drop policy if exists "Users can insert own profiles" on public.profiles;
drop policy if exists "Users can update own profiles" on public.profiles;
drop policy if exists "Users can delete own profiles" on public.profiles;

create policy "profiles_select_own"
on public.profiles for select to authenticated
using (auth.uid() = user_id);
create policy "profiles_insert_own"
on public.profiles for insert to authenticated
with check (auth.uid() = user_id);
create policy "profiles_update_own"
on public.profiles for update to authenticated
using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "profiles_delete_own"
on public.profiles for delete to authenticated
using (auth.uid() = user_id);

drop policy if exists "watchlist_select_own" on public.watchlist;
drop policy if exists "watchlist_insert_own" on public.watchlist;
drop policy if exists "watchlist_update_own" on public.watchlist;
drop policy if exists "watchlist_delete_own" on public.watchlist;
drop policy if exists "Users can view own watchlist" on public.watchlist;
drop policy if exists "Users can insert own watchlist" on public.watchlist;
drop policy if exists "Users can update own watchlist" on public.watchlist;
drop policy if exists "Users can delete own watchlist" on public.watchlist;

create policy "watchlist_select_own"
on public.watchlist for select to authenticated
using (auth.uid() = user_id);
create policy "watchlist_insert_own"
on public.watchlist for insert to authenticated
with check (auth.uid() = user_id);
create policy "watchlist_update_own"
on public.watchlist for update to authenticated
using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "watchlist_delete_own"
on public.watchlist for delete to authenticated
using (auth.uid() = user_id);

drop policy if exists "snapshots_select_own" on public.valuation_snapshots;
drop policy if exists "snapshots_insert_own" on public.valuation_snapshots;
drop policy if exists "snapshots_update_own" on public.valuation_snapshots;
drop policy if exists "snapshots_delete_own" on public.valuation_snapshots;
drop policy if exists "Users can view own valuation_snapshots" on public.valuation_snapshots;
drop policy if exists "Users can insert own valuation_snapshots" on public.valuation_snapshots;
drop policy if exists "Users can update own valuation_snapshots" on public.valuation_snapshots;
drop policy if exists "Users can delete own valuation_snapshots" on public.valuation_snapshots;

create policy "snapshots_select_own"
on public.valuation_snapshots for select to authenticated
using (auth.uid() = user_id);
create policy "snapshots_insert_own"
on public.valuation_snapshots for insert to authenticated
with check (auth.uid() = user_id);
create policy "snapshots_update_own"
on public.valuation_snapshots for update to authenticated
using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "snapshots_delete_own"
on public.valuation_snapshots for delete to authenticated
using (auth.uid() = user_id);

-- Optional inspection (read-only). Run separately if needed:
-- select column_name from information_schema.columns
-- where table_schema = 'public' and table_name = 'valuation_snapshots'
-- order by ordinal_position;
