-- V4.2 Dynamic Overvaluation / Exit Zone migration
-- Safe to re-run. Does NOT drop tables. Does NOT disable RLS. Does NOT use service_role.
-- Execute in Supabase SQL Editor after deploying v4.2-exit-zone app code.

alter table public.valuation_snapshots add column if not exists hold_upper_price numeric;
alter table public.valuation_snapshots add column if not exists overvalued_price numeric;
alter table public.valuation_snapshots add column if not exists trim_price numeric;
alter table public.valuation_snapshots add column if not exists extreme_price numeric;
alter table public.valuation_snapshots add column if not exists exit_zone_json jsonb;

-- Note: exit zone is also mirrored into raw.exit_zone_json for legacy-column fallback.
-- Historical mode must read saved exit_zone_json / price columns and never recompute.
