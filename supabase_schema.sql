-- Supabase schema for مذكرتي الذكية PWA
-- Creates private archive tables used by the local Obsidian/Markdown PWA.

create extension if not exists pgcrypto;

create table if not exists public.notes (
  id uuid primary key default gen_random_uuid(),
  local_id text unique,
  title text,
  note_type text,
  mood text,
  cause text,
  body text,
  action text,
  topics text[] default '{}',
  tags text[] default '{}',
  obsidian_path text,
  date date,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  metadata jsonb not null default '{}'::jsonb
);

create table if not exists public.links (
  id uuid primary key default gen_random_uuid(),
  local_id text unique,
  url text not null,
  title text,
  kind text,
  reason text,
  status text,
  notes text,
  topics text[] default '{}',
  tags text[] default '{}',
  image_url text,
  obsidian_path text,
  date date,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  metadata jsonb not null default '{}'::jsonb
);

create table if not exists public.places (
  id uuid primary key default gen_random_uuid(),
  local_id text unique,
  title text,
  typed_name text,
  category text,
  status text,
  notes text,
  lat double precision,
  lon double precision,
  address text,
  maps_url text,
  photo_path text,
  photo_storage_path text,
  obsidian_path text,
  date date,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  metadata jsonb not null default '{}'::jsonb
);

create table if not exists public.trackers (
  id uuid primary key default gen_random_uuid(),
  local_id text unique,
  name text not null,
  kind text,
  unit text,
  obsidian_path text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  metadata jsonb not null default '{}'::jsonb
);

create table if not exists public.tracker_entries (
  id uuid primary key default gen_random_uuid(),
  tracker_id uuid references public.trackers(id) on delete cascade,
  tracker_local_id text,
  value text,
  notes text,
  date date not null default current_date,
  created_at timestamptz not null default now(),
  metadata jsonb not null default '{}'::jsonb
);

create table if not exists public.sync_log (
  id bigserial primary key,
  entity_type text not null,
  entity_local_id text,
  entity_remote_id uuid,
  action text not null,
  status text not null,
  message text,
  created_at timestamptz not null default now(),
  metadata jsonb not null default '{}'::jsonb
);

create index if not exists idx_notes_date on public.notes(date desc);
create index if not exists idx_links_date on public.links(date desc);
create index if not exists idx_places_date on public.places(date desc);
create index if not exists idx_places_lat_lon on public.places(lat, lon);
create index if not exists idx_tracker_entries_date on public.tracker_entries(date desc);
create index if not exists idx_sync_log_created_at on public.sync_log(created_at desc);

create or replace function public.set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists set_notes_updated_at on public.notes;
create trigger set_notes_updated_at
before update on public.notes
for each row execute function public.set_updated_at();

drop trigger if exists set_links_updated_at on public.links;
create trigger set_links_updated_at
before update on public.links
for each row execute function public.set_updated_at();

drop trigger if exists set_places_updated_at on public.places;
create trigger set_places_updated_at
before update on public.places
for each row execute function public.set_updated_at();

drop trigger if exists set_trackers_updated_at on public.trackers;
create trigger set_trackers_updated_at
before update on public.trackers
for each row execute function public.set_updated_at();

-- Private-by-default: service_role can access; anon/authenticated are blocked unless policies are added later.
alter table public.notes enable row level security;
alter table public.links enable row level security;
alter table public.places enable row level security;
alter table public.trackers enable row level security;
alter table public.tracker_entries enable row level security;
alter table public.sync_log enable row level security;

-- Storage bucket for place photos.
insert into storage.buckets (id, name, public)
values ('place-photos', 'place-photos', false)
on conflict (id) do nothing;
