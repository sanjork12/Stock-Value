-- V4.2.1 Exit Reliability Guard migration
-- Safe to re-run. Does NOT drop tables. Does NOT disable RLS.

alter table public.valuation_snapshots add column if not exists exit_confidence text;
alter table public.valuation_snapshots add column if not exists exit_display_mode text;
alter table public.valuation_snapshots add column if not exists exit_reliability_score numeric;
alter table public.valuation_snapshots add column if not exists exit_reason_codes jsonb;

-- Precise exit prices remain null when exit_display_mode != 'precise'.
-- Historical mode must read saved exit_* fields / exit_zone_json and never recompute.
