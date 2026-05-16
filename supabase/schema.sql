create table if not exists public.discord_servers (
  id bigserial primary key,
  guild_id text not null unique,
  server_name text not null,
  spring_channel_id text,
  summer_channel_id text,
  fall_channel_id text,
  sudo_id text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists discord_servers_guild_id_idx
  on public.discord_servers (guild_id);

create table if not exists public.companies (
  id bigserial primary key,
  company_name text not null unique,
  created_at timestamptz not null default now(),
  constraint companies_company_name_lowercase
    check (company_name = lower(company_name))
);

create index if not exists companies_company_name_idx
  on public.companies (company_name);

create table if not exists public.posted_jobs (
  id bigserial primary key,
  job_id text not null,
  guild_id text not null,
  season text not null,
  channel_id text not null,
  company_name text not null,
  title text not null,
  url text not null,
  job_year text,
  date_posted_label text,
  posted_at timestamptz not null default now(),
  constraint posted_jobs_season_check
    check (season in ('spring', 'summer', 'fall')),
  constraint posted_jobs_unique_job_per_guild_season
    unique (job_id, guild_id, season)
);

create index if not exists posted_jobs_guild_season_idx
  on public.posted_jobs (guild_id, season);

create index if not exists posted_jobs_job_id_idx
  on public.posted_jobs (job_id);

create index if not exists posted_jobs_posted_at_idx
  on public.posted_jobs (posted_at);

create index if not exists posted_jobs_job_year_idx
  on public.posted_jobs (job_year);

alter table public.discord_servers enable row level security;
alter table public.companies enable row level security;
alter table public.posted_jobs enable row level security;

create or replace function public.set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists set_discord_servers_updated_at on public.discord_servers;

create trigger set_discord_servers_updated_at
before update on public.discord_servers
for each row
execute function public.set_updated_at();
