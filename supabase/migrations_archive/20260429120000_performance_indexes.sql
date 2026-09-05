-- Production indexes (plan: backend production completion — Phase 1)
-- Safe to apply after initial schema migration.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Leads: list ordering + common filters + Kanban sort
CREATE INDEX IF NOT EXISTS leads_updated_at_idx ON public.leads (updated_at DESC);
CREATE INDEX IF NOT EXISTS leads_owner_stage_idx ON public.leads (owner_id, stage);
CREATE INDEX IF NOT EXISTS leads_stage_priority_idx ON public.leads (stage, priority_score DESC);
CREATE INDEX IF NOT EXISTS leads_last_contact_idx ON public.leads (last_contact_date);

-- Tasks: reminders & overdue scans
CREATE INDEX IF NOT EXISTS tasks_status_due_idx ON public.tasks (status, due_date);
CREATE INDEX IF NOT EXISTS tasks_pending_due_partial_idx ON public.tasks (due_date)
  WHERE status = 'pending'::public.task_status;

-- Meetings: calendar sync & outcome prompts
CREATE INDEX IF NOT EXISTS meetings_lead_idx ON public.meetings (lead_id);
CREATE INDEX IF NOT EXISTS meetings_owner_scheduled_idx ON public.meetings (owner_id, scheduled_at);
CREATE INDEX IF NOT EXISTS meetings_scheduled_status_idx ON public.meetings (scheduled_at, status);

-- Contacts: company lookups
CREATE INDEX IF NOT EXISTS contacts_company_idx ON public.contacts (company_id);

-- Proposals: dashboard pending filter
CREATE INDEX IF NOT EXISTS proposals_status_idx ON public.proposals (status);

-- Companies / contacts: substring search (FR-LP-06 style ilike)
CREATE INDEX IF NOT EXISTS companies_name_trgm_idx ON public.companies USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS contacts_email_trgm_idx ON public.contacts USING gin (email gin_trgm_ops);
CREATE INDEX IF NOT EXISTS contacts_full_name_trgm_idx ON public.contacts USING gin (full_name gin_trgm_ops);
