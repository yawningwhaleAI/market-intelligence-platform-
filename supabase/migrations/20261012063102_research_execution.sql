-- Persist resumable research drafts, Apify scan batches, and collected items.
-- Every record is user-owned; reads and writes remain behind Auth + RLS.

alter table public.research_projects
  add column if not exists lifecycle_status text not null default 'draft';

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'research_projects_lifecycle_status_check'
      and conrelid = 'public.research_projects'::regclass
  ) then
    alter table public.research_projects
      add constraint research_projects_lifecycle_status_check
      check (lifecycle_status in ('draft', 'ready', 'running', 'completed', 'partial', 'failed'));
  end if;
end $$;

create table if not exists public.research_scans (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid not null,
  idempotency_key uuid not null,
  status text not null default 'queued'
    check (status in ('queued', 'running', 'succeeded', 'partial', 'failed')),
  scope jsonb not null default '{}'::jsonb,
  estimate jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  completed_at timestamptz,
  unique (id, user_id),
  unique (user_id, idempotency_key),
  foreign key (project_id, user_id)
    references public.research_projects(id, user_id) on delete cascade
);
alter table public.research_scans enable row level security;
drop policy if exists "Users can read their research scans" on public.research_scans;
create policy "Users can read their research scans"
  on public.research_scans for select to authenticated
  using ((select auth.uid()) = user_id);
drop policy if exists "Users can create their research scans" on public.research_scans;
create policy "Users can create their research scans"
  on public.research_scans for insert to authenticated
  with check ((select auth.uid()) = user_id);
drop policy if exists "Users can update their research scans" on public.research_scans;
create policy "Users can update their research scans"
  on public.research_scans for update to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);
drop policy if exists "Users can delete their research scans" on public.research_scans;
create policy "Users can delete their research scans"
  on public.research_scans for delete to authenticated
  using ((select auth.uid()) = user_id);
grant select, insert, update, delete on public.research_scans to authenticated;

alter table public.research_runs
  add column if not exists scan_id uuid,
  add column if not exists default_dataset_id text,
  add column if not exists run_scope jsonb not null default '{}'::jsonb,
  add column if not exists item_count integer not null default 0,
  add column if not exists actual_cost_usd numeric(12, 6),
  add column if not exists error_message text,
  add column if not exists started_at timestamptz,
  add column if not exists completed_at timestamptz;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'research_runs_scan_owner_fk'
      and conrelid = 'public.research_runs'::regclass
  ) then
    alter table public.research_runs
      add constraint research_runs_scan_owner_fk
      foreign key (scan_id, user_id)
      references public.research_scans(id, user_id) on delete cascade;
  end if;
end $$;

alter table public.market_observations
  add column if not exists item_index integer;
create unique index if not exists market_observations_run_item_unique
  on public.market_observations(run_id, item_index);

create index if not exists research_scans_project_created_idx
  on public.research_scans(user_id, project_id, created_at desc);
create index if not exists research_runs_scan_status_idx
  on public.research_runs(user_id, scan_id, status);
create index if not exists market_observations_run_item_idx
  on public.market_observations(user_id, run_id, item_index);

grant select, insert, update, delete on public.research_projects to authenticated;
grant select, insert, update, delete on public.research_runs to authenticated;
grant select, insert, update, delete on public.market_observations to authenticated;
