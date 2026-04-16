-- Phase 1: Lead Discovery
create table if not exists practices (
  id bigserial primary key,
  place_id text unique not null,
  name text not null,
  address text,
  city text,
  state text,
  phone text,
  website text,
  rating numeric(2,1),
  review_count int default 0,
  category text,
  lat double precision,
  lng double precision,
  opening_hours text,

  -- Phase 2 (AI analysis) — columns exist but nullable
  summary text,
  pain_points text,
  sales_angles text,
  recommended_service text,
  lead_score int,
  urgency_score int,
  hiring_signal_score int,

  -- Phase 3 (Call Playbook + CRM)
  call_script text,

  -- Phase 3 (CRM) — columns exist but nullable
  status text default 'NEW',
  notes text,

  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create index if not exists idx_practices_place_id on practices (place_id);
create index if not exists idx_practices_category on practices (category);
create index if not exists idx_practices_city on practices (city);
create index if not exists idx_practices_score on practices (lead_score desc nulls last);
