-- Run this once in Supabase SQL Editor.
-- Authentication itself is handled by Supabase Auth; do NOT create a plaintext password table.

create extension if not exists pgcrypto;

create table if not exists public.profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  display_name text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.watchlist (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  ticker text not null,
  nickname text,
  created_at timestamptz not null default now(),
  unique(user_id, ticker)
);

create table if not exists public.valuation_snapshots (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  ticker text not null,
  snapshot_date date not null,
  price numeric,
  sma30 numeric,
  sma50 numeric,
  sma200 numeric,
  volume_zone_low numeric,
  volume_zone_high numeric,
  fair_value numeric,
  pe_model jsonb,
  dcf_model jsonb,
  growth_model jsonb,
  first_low numeric,
  first_high numeric,
  core_low numeric,
  core_high numeric,
  deep_low numeric,
  deep_high numeric,
  status text,
  raw jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(user_id, ticker, snapshot_date)
);

alter table public.profiles enable row level security;
alter table public.watchlist enable row level security;
alter table public.valuation_snapshots enable row level security;

-- Re-create policies safely.
drop policy if exists "profiles_select_own" on public.profiles;
drop policy if exists "profiles_insert_own" on public.profiles;
drop policy if exists "profiles_update_own" on public.profiles;
create policy "profiles_select_own" on public.profiles for select using (auth.uid() = user_id);
create policy "profiles_insert_own" on public.profiles for insert with check (auth.uid() = user_id);
create policy "profiles_update_own" on public.profiles for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "watchlist_select_own" on public.watchlist;
drop policy if exists "watchlist_insert_own" on public.watchlist;
drop policy if exists "watchlist_update_own" on public.watchlist;
drop policy if exists "watchlist_delete_own" on public.watchlist;
create policy "watchlist_select_own" on public.watchlist for select using (auth.uid() = user_id);
create policy "watchlist_insert_own" on public.watchlist for insert with check (auth.uid() = user_id);
create policy "watchlist_update_own" on public.watchlist for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "watchlist_delete_own" on public.watchlist for delete using (auth.uid() = user_id);

drop policy if exists "snapshots_select_own" on public.valuation_snapshots;
drop policy if exists "snapshots_insert_own" on public.valuation_snapshots;
drop policy if exists "snapshots_update_own" on public.valuation_snapshots;
drop policy if exists "snapshots_delete_own" on public.valuation_snapshots;
create policy "snapshots_select_own" on public.valuation_snapshots for select using (auth.uid() = user_id);
create policy "snapshots_insert_own" on public.valuation_snapshots for insert with check (auth.uid() = user_id);
create policy "snapshots_update_own" on public.valuation_snapshots for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "snapshots_delete_own" on public.valuation_snapshots for delete using (auth.uid() = user_id);

create index if not exists idx_watchlist_user on public.watchlist(user_id);
create index if not exists idx_snapshot_user_ticker_date on public.valuation_snapshots(user_id, ticker, snapshot_date desc);
