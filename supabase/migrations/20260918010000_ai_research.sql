-- ===========================================================================
-- Company research and pre-call briefs.
--
-- Both tables hold AI output derived from the public web plus (for briefs) CRM facts.
-- Written only by the API's service-role client after it has proven, through the
-- caller's own RLS-scoped connection, that the caller can see the company or lead.
-- Read by anyone who can see that company or lead -- and nobody else.
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- company_research: one row per research run. History is kept (it is cheap and
-- lets a rep see how a company's profile changed); readers take the newest.
-- ---------------------------------------------------------------------------
CREATE TABLE public.company_research (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  company_id UUID NOT NULL REFERENCES public.companies (id) ON DELETE CASCADE,
  profile JSONB NOT NULL,
  suspicious_content BOOLEAN NOT NULL DEFAULT FALSE,
  requested_by UUID REFERENCES public.users (id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX company_research_company_idx ON public.company_research (company_id, created_at DESC);

-- Derived from the company, unconditionally. set_parent_organization() overwrites whatever the
-- writer supplied, so even a service-role caller cannot file research under the wrong tenant.
CREATE TRIGGER company_research_set_org BEFORE INSERT ON public.company_research
  FOR EACH ROW EXECUTE FUNCTION public.set_parent_organization('companies', 'company_id');

ALTER TABLE public.company_research ENABLE ROW LEVEL SECURITY;

-- Visibility follows the company. The EXISTS subquery runs under the caller's own RLS on
-- `companies`, so this inherits companies_select's rule (creator, or reachable through an
-- accessible lead, or full access) rather than restating it -- restating an ownership rule is
-- how can_access_lead() drifted and broke.
CREATE POLICY company_research_select ON public.company_research FOR SELECT USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND EXISTS (SELECT 1 FROM public.companies c WHERE c.id = company_research.company_id)
);
-- No INSERT/UPDATE/DELETE policy for `authenticated`: service-role writes only. A user able to
-- write here could plant "research" -- text and links -- that a colleague would read as sourced.

-- ---------------------------------------------------------------------------
-- lead_briefs: the pre-call brief for a lead. Same shape and same rules.
-- ---------------------------------------------------------------------------
CREATE TABLE public.lead_briefs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  lead_id UUID NOT NULL REFERENCES public.leads (id) ON DELETE CASCADE,
  brief JSONB NOT NULL,
  research_id UUID REFERENCES public.company_research (id) ON DELETE SET NULL,
  requested_by UUID REFERENCES public.users (id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX lead_briefs_lead_idx ON public.lead_briefs (lead_id, created_at DESC);

CREATE TRIGGER lead_briefs_set_org BEFORE INSERT ON public.lead_briefs
  FOR EACH ROW EXECUTE FUNCTION public.set_parent_organization('leads', 'lead_id');

ALTER TABLE public.lead_briefs ENABLE ROW LEVEL SECURITY;

-- A brief contains CRM facts (stage, value, intelligence notes), so it is exactly as private as
-- the lead: can_access_lead() is the chokepoint for that, and is_active is checked inside it.
CREATE POLICY lead_briefs_select ON public.lead_briefs FOR SELECT USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (SELECT public.can_access_lead(auth.uid(), lead_briefs.lead_id))
);
