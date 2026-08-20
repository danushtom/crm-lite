-- Dracara Growth OS — initial schema + RLS (see tdd.md §10–11)

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ENUM types
CREATE TYPE public.user_role AS ENUM ('admin', 'agent', 'sdr', 'partner');
CREATE TYPE public.lead_stage AS ENUM (
  'prospect', 'contacting', 'discovery_scheduled', 'requirements_gathering',
  'solution_design', 'proposal_sent', 'negotiation', 'won',
  'delivery_transition', 'on_hold', 'followup_later', 'lost'
);
CREATE TYPE public.project_type AS ENUM ('mvp', 'saas', 'ai', 'webapp', 'erp', 'other');
CREATE TYPE public.lead_source AS ENUM ('cold_call', 'referral', 'website', 'linkedin', 'other');
CREATE TYPE public.comm_preference AS ENUM ('whatsapp', 'email', 'linkedin', 'phone', 'call');
CREATE TYPE public.activity_type AS ENUM (
  'call', 'email', 'meeting', 'note', 'stage_change', 'proposal_sent',
  'task_created', 'task_completed', 'document_uploaded'
);
CREATE TYPE public.task_status AS ENUM ('pending', 'snoozed', 'completed', 'cancelled');
CREATE TYPE public.meeting_status AS ENUM ('scheduled', 'completed', 'cancelled', 'rescheduled');
CREATE TYPE public.meeting_outcome AS ENUM (
  'interested', 'needs_proposal', 'budget_issue', 'not_interested', 'followup_later'
);
CREATE TYPE public.opportunity_status AS ENUM ('active', 'won', 'lost', 'on_hold');
CREATE TYPE public.proposal_status AS ENUM ('draft', 'sent', 'under_review', 'accepted', 'rejected');

-- Profile synced from auth.users
CREATE TABLE public.users (
  id UUID PRIMARY KEY REFERENCES auth.users (id) ON DELETE CASCADE,
  email TEXT UNIQUE NOT NULL,
  full_name TEXT NOT NULL DEFAULT '',
  role public.user_role NOT NULL DEFAULT 'agent',
  avatar_url TEXT,
  google_access_token TEXT,
  google_refresh_token TEXT,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE public.companies (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  industry TEXT,
  size TEXT,
  website TEXT,
  location TEXT,
  created_by UUID REFERENCES public.users (id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE public.contacts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES public.companies (id) ON DELETE CASCADE,
  full_name TEXT NOT NULL,
  role TEXT,
  email TEXT,
  phone TEXT,
  linkedin_url TEXT,
  is_primary BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE public.leads (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES public.companies (id),
  primary_contact_id UUID REFERENCES public.contacts (id),
  owner_id UUID NOT NULL REFERENCES public.users (id),
  stage public.lead_stage NOT NULL DEFAULT 'prospect',
  project_type public.project_type NOT NULL,
  lead_source public.lead_source NOT NULL,
  estimated_value NUMERIC(12, 2),
  currency TEXT NOT NULL DEFAULT 'INR',
  deal_probability SMALLINT NOT NULL DEFAULT 50 CHECK (deal_probability BETWEEN 0 AND 100),
  priority_score SMALLINT NOT NULL DEFAULT 0 CHECK (priority_score BETWEEN 0 AND 100),
  score_override SMALLINT CHECK (score_override IS NULL OR score_override BETWEEN 0 AND 100),
  score_override_reason TEXT,
  last_contact_date DATE,
  next_followup_date DATE,
  is_opportunity BOOLEAN NOT NULL DEFAULT FALSE,
  tags TEXT[] NOT NULL DEFAULT '{}',
  no_touch_alert BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX leads_owner_idx ON public.leads (owner_id);
CREATE INDEX leads_stage_idx ON public.leads (stage);
CREATE INDEX leads_next_followup_idx ON public.leads (next_followup_date);

CREATE TABLE public.lead_intelligence (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_id UUID NOT NULL UNIQUE REFERENCES public.leads (id) ON DELETE CASCADE,
  pain_points TEXT,
  tech_stack TEXT,
  budget_hints TEXT,
  decision_makers TEXT,
  competitors_involved TEXT,
  objections_raised TEXT,
  strategic_notes TEXT,
  comm_preference public.comm_preference NOT NULL DEFAULT 'email',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_by UUID REFERENCES public.users (id)
);

CREATE OR REPLACE FUNCTION public.ensure_lead_intelligence()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  INSERT INTO public.lead_intelligence (lead_id) VALUES (NEW.id);
  RETURN NEW;
END;
$$;

CREATE TRIGGER leads_after_insert_intelligence
  AFTER INSERT ON public.leads
  FOR EACH ROW EXECUTE FUNCTION public.ensure_lead_intelligence();

CREATE TABLE public.activities (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_id UUID NOT NULL REFERENCES public.leads (id) ON DELETE CASCADE,
  type public.activity_type NOT NULL,
  description TEXT NOT NULL,
  outcome TEXT,
  performed_by UUID NOT NULL REFERENCES public.users (id),
  performed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  metadata JSONB
);

CREATE INDEX activities_lead_idx ON public.activities (lead_id, performed_at DESC);

CREATE TABLE public.tasks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_id UUID NOT NULL REFERENCES public.leads (id) ON DELETE CASCADE,
  owner_id UUID NOT NULL REFERENCES public.users (id),
  title TEXT NOT NULL,
  notes TEXT,
  due_date DATE NOT NULL,
  due_time TIME,
  status public.task_status NOT NULL DEFAULT 'pending',
  outcome_note TEXT,
  snoozed_until DATE,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX tasks_owner_due_idx ON public.tasks (owner_id, due_date);

CREATE TABLE public.meetings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_id UUID NOT NULL REFERENCES public.leads (id) ON DELETE CASCADE,
  owner_id UUID NOT NULL REFERENCES public.users (id),
  title TEXT NOT NULL,
  google_event_id TEXT UNIQUE,
  google_meet_link TEXT,
  scheduled_at TIMESTAMPTZ NOT NULL,
  duration_minutes INTEGER NOT NULL DEFAULT 30,
  status public.meeting_status NOT NULL DEFAULT 'scheduled',
  outcome public.meeting_outcome,
  outcome_notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE public.opportunities (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_id UUID NOT NULL UNIQUE REFERENCES public.leads (id) ON DELETE CASCADE,
  owner_id UUID NOT NULL REFERENCES public.users (id),
  title TEXT NOT NULL,
  quoted_value NUMERIC(12, 2),
  currency TEXT NOT NULL DEFAULT 'INR',
  timeline_weeks INTEGER,
  tech_stack TEXT,
  requirements_doc TEXT,
  architecture_notes TEXT,
  status public.opportunity_status NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE public.proposals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  opportunity_id UUID NOT NULL REFERENCES public.opportunities (id) ON DELETE CASCADE,
  version INTEGER NOT NULL DEFAULT 1,
  title TEXT NOT NULL,
  file_url TEXT,
  figma_url TEXT,
  github_url TEXT,
  loom_url TEXT,
  quoted_price NUMERIC(12, 2),
  change_notes TEXT,
  status public.proposal_status NOT NULL DEFAULT 'draft',
  sent_at TIMESTAMPTZ,
  created_by UUID REFERENCES public.users (id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (opportunity_id, version)
);

CREATE INDEX proposals_opportunity_idx ON public.proposals (opportunity_id);

-- Helper: admin check in policies
CREATE OR REPLACE FUNCTION public.is_admin(uid UUID)
RETURNS BOOLEAN
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
  SELECT EXISTS (SELECT 1 FROM public.users u WHERE u.id = uid AND u.role = 'admin')
$$;

CREATE OR REPLACE FUNCTION public.can_access_lead(uid UUID, lid UUID)
RETURNS BOOLEAN
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.leads l
    WHERE l.id = lid AND (l.owner_id = uid OR public.is_admin(uid))
  )
$$;

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  INSERT INTO public.users (id, email, full_name, role)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'full_name', COALESCE(split_part(NEW.email, '@', 1), 'User')),
    'agent'::public.user_role
  );
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

CREATE OR REPLACE FUNCTION public.touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER users_touch BEFORE UPDATE ON public.users
  FOR EACH ROW EXECUTE FUNCTION public.touch_updated_at();

CREATE TRIGGER leads_touch BEFORE UPDATE ON public.leads
  FOR EACH ROW EXECUTE FUNCTION public.touch_updated_at();

CREATE TRIGGER opportunities_touch BEFORE UPDATE ON public.opportunities
  FOR EACH ROW EXECUTE FUNCTION public.touch_updated_at();

CREATE OR REPLACE FUNCTION public.log_lead_stage_change()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF TG_OP = 'UPDATE' AND OLD.stage IS DISTINCT FROM NEW.stage THEN
    INSERT INTO public.activities (lead_id, type, description, performed_by, metadata)
    VALUES (
      NEW.id,
      'stage_change'::public.activity_type,
      'Stage changed from ' || OLD.stage::TEXT || ' to ' || NEW.stage::TEXT,
      auth.uid(),
      jsonb_build_object('old_stage', OLD.stage::TEXT, 'new_stage', NEW.stage::TEXT)
    );
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER leads_stage_change AFTER UPDATE ON public.leads
  FOR EACH ROW EXECUTE FUNCTION public.log_lead_stage_change();

-- Row Level Security
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lead_intelligence ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.activities ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.meetings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.opportunities ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.proposals ENABLE ROW LEVEL SECURITY;

-- users
CREATE POLICY users_select ON public.users FOR SELECT USING (id = auth.uid() OR public.is_admin(auth.uid()));
CREATE POLICY users_update_self ON public.users FOR UPDATE USING (id = auth.uid());

-- companies — visible if linked to accessible lead or creator
CREATE POLICY companies_select ON public.companies FOR SELECT USING (
  created_by = auth.uid()
  OR public.is_admin(auth.uid())
  OR EXISTS (
    SELECT 1 FROM public.leads l
    WHERE l.company_id = companies.id AND public.can_access_lead(auth.uid(), l.id)
  )
);
CREATE POLICY companies_insert ON public.companies FOR INSERT WITH CHECK (
  auth.uid() IS NOT NULL AND created_by = auth.uid()
);
CREATE POLICY companies_update ON public.companies FOR UPDATE USING (
  created_by = auth.uid() OR public.is_admin(auth.uid())
);

-- contacts — same visibility as parent company policy via leads
CREATE POLICY contacts_select ON public.contacts FOR SELECT USING (
  EXISTS (
    SELECT 1 FROM public.leads l
    WHERE l.company_id = contacts.company_id AND public.can_access_lead(auth.uid(), l.id)
  )
  OR public.is_admin(auth.uid())
);
CREATE POLICY contacts_insert ON public.contacts FOR INSERT WITH CHECK (
  auth.uid() IS NOT NULL AND (
    EXISTS (
      SELECT 1 FROM public.companies c
      WHERE c.id = contacts.company_id AND (c.created_by = auth.uid() OR public.is_admin(auth.uid()))
    )
    OR EXISTS (
      SELECT 1 FROM public.leads l
      WHERE l.company_id = contacts.company_id AND public.can_access_lead(auth.uid(), l.id)
    )
  )
);
CREATE POLICY contacts_update ON public.contacts FOR UPDATE USING (
  EXISTS (
    SELECT 1 FROM public.leads l
    WHERE l.company_id = contacts.company_id AND public.can_access_lead(auth.uid(), l.id)
  )
  OR public.is_admin(auth.uid())
);

-- leads
CREATE POLICY leads_select ON public.leads FOR SELECT USING (public.can_access_lead(auth.uid(), id));
CREATE POLICY leads_insert ON public.leads FOR INSERT WITH CHECK (
  auth.uid() IS NOT NULL AND (owner_id = auth.uid() OR public.is_admin(auth.uid()))
);
CREATE POLICY leads_update ON public.leads FOR UPDATE USING (public.can_access_lead(auth.uid(), id));

-- lead_intelligence
CREATE POLICY li_select ON public.lead_intelligence FOR SELECT USING (
  public.can_access_lead(auth.uid(), lead_id)
);
CREATE POLICY li_insert ON public.lead_intelligence FOR INSERT WITH CHECK (
  public.can_access_lead(auth.uid(), lead_id)
);
CREATE POLICY li_update ON public.lead_intelligence FOR UPDATE USING (
  public.can_access_lead(auth.uid(), lead_id)
);

-- activities
CREATE POLICY activities_select ON public.activities FOR SELECT USING (
  public.can_access_lead(auth.uid(), lead_id)
);
CREATE POLICY activities_insert ON public.activities FOR INSERT WITH CHECK (
  public.can_access_lead(auth.uid(), lead_id) AND performed_by = auth.uid()
);

-- tasks (owner or admin)
CREATE POLICY tasks_select ON public.tasks FOR SELECT USING (
  owner_id = auth.uid() OR public.is_admin(auth.uid())
);
CREATE POLICY tasks_insert ON public.tasks FOR INSERT WITH CHECK (
  owner_id = auth.uid() OR public.is_admin(auth.uid())
);
CREATE POLICY tasks_update ON public.tasks FOR UPDATE USING (
  owner_id = auth.uid() OR public.is_admin(auth.uid())
);

CREATE POLICY meetings_select ON public.meetings FOR SELECT USING (
  owner_id = auth.uid() OR public.is_admin(auth.uid())
);
CREATE POLICY meetings_insert ON public.meetings FOR INSERT WITH CHECK (
  owner_id = auth.uid() OR public.is_admin(auth.uid())
);
CREATE POLICY meetings_update ON public.meetings FOR UPDATE USING (
  owner_id = auth.uid() OR public.is_admin(auth.uid())
);

CREATE POLICY opp_select ON public.opportunities FOR SELECT USING (
  public.can_access_lead(auth.uid(), lead_id)
);
CREATE POLICY opp_insert ON public.opportunities FOR INSERT WITH CHECK (
  public.can_access_lead(auth.uid(), lead_id)
);
CREATE POLICY opp_update ON public.opportunities FOR UPDATE USING (
  public.can_access_lead(auth.uid(), lead_id)
);

CREATE POLICY prop_select ON public.proposals FOR SELECT USING (
  EXISTS (
    SELECT 1 FROM public.opportunities o
    WHERE o.id = proposals.opportunity_id AND public.can_access_lead(auth.uid(), o.lead_id)
  )
);
CREATE POLICY prop_insert ON public.proposals FOR INSERT WITH CHECK (
  EXISTS (
    SELECT 1 FROM public.opportunities o
    WHERE o.id = proposals.opportunity_id AND public.can_access_lead(auth.uid(), o.lead_id)
  )
);
CREATE POLICY prop_update ON public.proposals FOR UPDATE USING (
  EXISTS (
    SELECT 1 FROM public.opportunities o
    WHERE o.id = proposals.opportunity_id AND public.can_access_lead(auth.uid(), o.lead_id)
  )
);
