create table public.jobs (
  id bigserial not null,
  job_id text not null,
  title text null,
  job_url text null,
  company text null,
  company_url text null,
  location text null,
  publication_date date null,
  description text null,
  created_at timestamp with time zone null default now(),
  deleted_at timestamp with time zone null,
  cfo_score integer null,
  scored_at timestamp with time zone null,
  job_info timestamp with time zone null,
  last_seen timestamp with time zone null,
  region text[] null,
  embedding_created_at timestamp with time zone null,
  embedding public.vector null,
  cluster_id integer null,
  constraint jobs_pkey primary key (id),
  constraint jobs_job_id_key unique (job_id),
  constraint jobs_cfo_score_check check (
    (
      (cfo_score >= 0)
      and (cfo_score <= 3)
    )
  )
) TABLESPACE pg_default;

create index IF not exists idx_jobs_job_id on public.jobs using btree (job_id) TABLESPACE pg_default;

create index IF not exists idx_jobs_company on public.jobs using btree (company) TABLESPACE pg_default;

create index IF not exists idx_jobs_publication_date on public.jobs using btree (publication_date) TABLESPACE pg_default;

create index IF not exists idx_jobs_deleted_at on public.jobs using btree (deleted_at) TABLESPACE pg_default;

create index IF not exists idx_jobs_cfo_score on public.jobs using btree (cfo_score) TABLESPACE pg_default;

create index IF not exists idx_jobs_scored_at on public.jobs using btree (scored_at) TABLESPACE pg_default;

create index IF not exists idx_jobs_high_priority on public.jobs using btree (cfo_score) TABLESPACE pg_default
where
  (cfo_score = 3);

create index IF not exists idx_jobs_last_seen on public.jobs using btree (last_seen) TABLESPACE pg_default;

create index IF not exists idx_jobs_rls_deleted_at on public.jobs using btree (deleted_at) TABLESPACE pg_default
where
  (deleted_at is null);

create index IF not exists idx_jobs_rls_last_seen on public.jobs using btree (last_seen) TABLESPACE pg_default
where
  (deleted_at is null);

create index IF not exists idx_jobs_rls_created_at on public.jobs using btree (created_at) TABLESPACE pg_default;

-- Cluster-related indexes
create index IF not exists idx_jobs_cluster_id on public.jobs using btree (cluster_id) TABLESPACE pg_default;

create trigger job_audit_trigger
after INSERT
or DELETE
or
update on jobs for EACH row
execute FUNCTION audit_job_changes ();

-- Weekly insights table to store per-week cluster summaries
create table if not exists public.weekly_insights (
  id bigserial primary key,
  week_start_date date not null,
  cluster_id integer not null,
  cluster_name text null,
  job_count integer not null default 0,
  top_keywords text[] null,
  top_companies text[] null,
  created_at timestamp with time zone not null default now(),
  constraint weekly_insights_unique_week_cluster unique (week_start_date, cluster_id)
) TABLESPACE pg_default;

create index if not exists idx_weekly_insights_week on public.weekly_insights using btree (week_start_date) TABLESPACE pg_default;
create index if not exists idx_weekly_insights_cluster on public.weekly_insights using btree (cluster_id) TABLESPACE pg_default;