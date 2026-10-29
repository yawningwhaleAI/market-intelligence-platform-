create extension if not exists pgcrypto;

create table if not exists public.research_projects (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null check (char_length(name) between 2 and 120),
  brief jsonb not null default '{}'::jsonb,
  scope jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table public.research_projects add constraint research_projects_id_user_unique unique (id, user_id);
alter table public.research_projects enable row level security;
create policy "Users can read their research projects" on public.research_projects for select using (auth.uid() = user_id);
create policy "Users can create their research projects" on public.research_projects for insert with check (auth.uid() = user_id);
create policy "Users can update their research projects" on public.research_projects for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "Users can delete their research projects" on public.research_projects for delete using (auth.uid() = user_id);

create table if not exists public.apify_connections (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  encrypted_token text not null,
  account_label text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id)
);
alter table public.apify_connections enable row level security;
create policy "Users can read their Apify connection" on public.apify_connections for select using (auth.uid() = user_id);
create policy "Users can create their Apify connection" on public.apify_connections for insert with check (auth.uid() = user_id);
create policy "Users can update their Apify connection" on public.apify_connections for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "Users can delete their Apify connection" on public.apify_connections for delete using (auth.uid() = user_id);

create table if not exists public.research_runs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid not null references public.research_projects(id) on delete cascade,
  platform text not null check (platform in ('blinkit','zepto','instamart','amazon','flipkart')),
  actor_run_id text,
  status text not null default 'draft' check (status in ('draft','queued','running','succeeded','failed','cancelled')),
  estimate jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint research_runs_project_owner_fk foreign key (project_id, user_id) references public.research_projects(id, user_id) on delete cascade
);
alter table public.research_runs add constraint research_runs_id_user_unique unique (id, user_id);
alter table public.research_runs enable row level security;
create policy "Users can read their research runs" on public.research_runs for select using (auth.uid() = user_id);
create policy "Users can create their research runs" on public.research_runs for insert with check (auth.uid() = user_id);
create policy "Users can update their research runs" on public.research_runs for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "Users can delete their research runs" on public.research_runs for delete using (auth.uid() = user_id);

create table if not exists public.market_observations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  run_id uuid not null,
  platform text not null,
  observed_at timestamptz not null default now(),
  payload jsonb not null,
  source_url text,
  constraint market_observations_run_owner_fk foreign key (run_id, user_id) references public.research_runs(id, user_id) on delete cascade
);
alter table public.market_observations enable row level security;
create policy "Users can read their observations" on public.market_observations for select using (auth.uid() = user_id);
create policy "Users can create their observations" on public.market_observations for insert with check (auth.uid() = user_id);
create policy "Users can update their observations" on public.market_observations for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "Users can delete their observations" on public.market_observations for delete using (auth.uid() = user_id);

create index if not exists research_projects_user_updated_idx on public.research_projects(user_id, updated_at desc);
create index if not exists research_runs_user_created_idx on public.research_runs(user_id, created_at desc);
create index if not exists market_observations_run_idx on public.market_observations(run_id, observed_at desc);
