-- Multi-tenant foundation: organizations.
--
-- Every table so far is one shared workspace: RLS gates access purely by owner_id/created_by
-- plus a role check, and `is_admin(uid)` is used throughout as a blanket OR-bypass with no
-- notion of *which* business an admin administers. That is fine for one tenant and a genuine
-- cross-tenant data leak for more than one -- an admin invited into a second, unrelated
-- business would see the first business's entire pipeline.
--
-- This migration adds a real `organizations` table, denormalizes `organization_id` onto every
-- tenant-owned table (populated automatically by trigger, never supplied by API code), and
-- rewrites every policy and every SECURITY DEFINER function that currently relies on a bare
-- `is_admin()`/ownership check to also require the row's organization to match the caller's.
--
-- Sign-up behaviour (see the rewritten handle_new_user() in §8): a new auth user with no
-- valid invite token gets a brand-new organization and becomes its admin -- this is what
-- makes the product self-serve multi-tenant. An admin invite (POST /agents/invite) now creates
-- a single-use org_invites row and passes only its opaque id as `invite_token`, so invited
-- teammates join the inviter's org (with the role the admin chose) instead of minting a new
-- one -- and a self-signing-up stranger can never forge organization_id/role by hand-crafting
-- signup metadata, which a naive "just read organization_id off the metadata" design would
-- have allowed.
--
-- Configurable pipeline stages -- the feature this is a prerequisite for -- are not part of
-- this migration.

-- ---------------------------------------------------------------------------
-- 1. Root table.
-- ---------------------------------------------------------------------------
CREATE TABLE public.organizations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  slug TEXT UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE public.organizations IS
  'One row per tenant. Every table below is scoped to one via its organization_id column, '
  'populated automatically by trigger -- see set_*_organization() functions in this file.';

ALTER TABLE public.organizations ENABLE ROW LEVEL SECURITY;

-- Invite tokens: how a signup joins an *existing* org rather than minting a new one.
--
-- The organization_id / role a new auth user ends up with cannot be read from
-- raw_user_meta_data, because that JSON is client-settable on a public sign-up call -- anyone
-- could otherwise call supabase.auth.signUp() with { data: { organization_id: <any org>,
-- role: 'admin' } } and hand themselves admin access to a business they've never heard of.
-- An admin invite therefore creates an opaque, single-use, expiring, email-pinned token here
-- (service-role only, no client policy touches this table), and only *that* token -- not an
-- organization id or a role -- ever goes into the invitee's metadata. handle_new_user() (§8)
-- trusts the token, never the metadata's own claims.
CREATE TABLE public.org_invites (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES public.organizations (id),
  email TEXT NOT NULL,
  role public.user_role NOT NULL DEFAULT 'agent',
  created_by UUID REFERENCES public.users (id),
  expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '7 days',
  consumed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.org_invites ENABLE ROW LEVEL SECURITY;
-- No policies: written by POST /agents/invite via the service-role client, read only by
-- handle_new_user() (SECURITY DEFINER). Never reachable through a user's own token.

COMMENT ON TABLE public.org_invites IS
  'Single-use, expiring, email-pinned invite tokens. The only way a signup can join an '
  'existing organization -- see handle_new_user().';

-- ---------------------------------------------------------------------------
-- 2. organization_id everywhere, nullable for now -- backfilled in §3, locked down in §6.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
  t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'users', 'companies', 'contacts', 'leads', 'opportunities', 'lead_intelligence',
    'activities', 'tasks', 'meetings', 'proposals', 'notifications',
    'marketing_channel_metrics', 'audit_log'
  ]
  LOOP
    EXECUTE format('ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS organization_id UUID', t);
  END LOOP;
END;
$$;

-- ---------------------------------------------------------------------------
-- 3. Backfill: everything that exists today is one tenant.
-- ---------------------------------------------------------------------------
INSERT INTO public.organizations (name, slug) VALUES ('Default Organization', 'default');

DO $$
DECLARE
  bootstrap_id UUID;
  t TEXT;
BEGIN
  SELECT id INTO bootstrap_id FROM public.organizations WHERE slug = 'default';

  FOREACH t IN ARRAY ARRAY[
    'users', 'companies', 'contacts', 'leads', 'opportunities', 'lead_intelligence',
    'activities', 'tasks', 'meetings', 'proposals', 'notifications',
    'marketing_channel_metrics', 'audit_log'
  ]
  LOOP
    EXECUTE format('UPDATE public.%I SET organization_id = $1 WHERE organization_id IS NULL', t)
      USING bootstrap_id;
  END LOOP;
END;
$$;

-- ---------------------------------------------------------------------------
-- 4. current_org_id(): every policy's org check goes through this, same as is_admin().
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.current_org_id(uid UUID)
RETURNS UUID
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
  SELECT organization_id FROM public.users WHERE id = uid
$$;

-- ---------------------------------------------------------------------------
-- 5. Auto-population: organization_id is derived from a parent row, never supplied by the
-- client, so application code cannot get it wrong (or forget to set it).
-- ---------------------------------------------------------------------------
-- Always derived, never trusted from the client -- a caller talking to PostgREST directly
-- with their own token (bypassing the FastAPI schemas, which expose no such field) could
-- otherwise set organization_id to any value in the request body.
CREATE OR REPLACE FUNCTION public.set_company_organization()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  SELECT organization_id INTO NEW.organization_id
  FROM public.users WHERE id = NEW.created_by;
  IF NEW.organization_id IS NULL THEN
    RAISE EXCEPTION 'Cannot determine organization for this company' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS companies_set_org ON public.companies;
CREATE TRIGGER companies_set_org BEFORE INSERT ON public.companies
  FOR EACH ROW EXECUTE FUNCTION public.set_company_organization();

CREATE OR REPLACE FUNCTION public.set_contact_organization()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  SELECT organization_id INTO NEW.organization_id
  FROM public.companies WHERE id = NEW.company_id;
  IF NEW.organization_id IS NULL THEN
    RAISE EXCEPTION 'Cannot determine organization for this contact' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS contacts_set_org ON public.contacts;
CREATE TRIGGER contacts_set_org BEFORE INSERT ON public.contacts
  FOR EACH ROW EXECUTE FUNCTION public.set_contact_organization();

-- A lead's organization comes from its company; owner_id must belong to that same
-- organization, since a lead owned by a user outside the tenant makes no sense.
CREATE OR REPLACE FUNCTION public.set_lead_organization()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  company_org UUID;
  owner_org UUID;
BEGIN
  SELECT organization_id INTO company_org FROM public.companies WHERE id = NEW.company_id;
  SELECT organization_id INTO owner_org FROM public.users WHERE id = NEW.owner_id;

  IF company_org IS NULL THEN
    RAISE EXCEPTION 'Cannot determine organization for this lead' USING ERRCODE = '23514';
  END IF;
  IF owner_org IS DISTINCT FROM company_org THEN
    RAISE EXCEPTION 'Lead owner must belong to the same organization as the company'
      USING ERRCODE = '23514';
  END IF;

  NEW.organization_id := company_org;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS leads_set_org ON public.leads;
CREATE TRIGGER leads_set_org BEFORE INSERT ON public.leads
  FOR EACH ROW EXECUTE FUNCTION public.set_lead_organization();

-- opportunities, lead_intelligence, activities and tasks all hang off a lead_id and inherit
-- its organization directly.
CREATE OR REPLACE FUNCTION public.set_lead_child_organization()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  SELECT organization_id INTO NEW.organization_id
  FROM public.leads WHERE id = NEW.lead_id;
  IF NEW.organization_id IS NULL THEN
    RAISE EXCEPTION 'Cannot determine organization for this record' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS opportunities_set_org ON public.opportunities;
CREATE TRIGGER opportunities_set_org BEFORE INSERT ON public.opportunities
  FOR EACH ROW EXECUTE FUNCTION public.set_lead_child_organization();

DROP TRIGGER IF EXISTS lead_intelligence_set_org ON public.lead_intelligence;
CREATE TRIGGER lead_intelligence_set_org BEFORE INSERT ON public.lead_intelligence
  FOR EACH ROW EXECUTE FUNCTION public.set_lead_child_organization();

DROP TRIGGER IF EXISTS activities_set_org ON public.activities;
CREATE TRIGGER activities_set_org BEFORE INSERT ON public.activities
  FOR EACH ROW EXECUTE FUNCTION public.set_lead_child_organization();

DROP TRIGGER IF EXISTS tasks_set_org ON public.tasks;
CREATE TRIGGER tasks_set_org BEFORE INSERT ON public.tasks
  FOR EACH ROW EXECUTE FUNCTION public.set_lead_child_organization();

-- meetings.lead_id is nullable (standalone meetings), so fall back to the owner's org.
CREATE OR REPLACE FUNCTION public.set_meeting_organization()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF NEW.lead_id IS NOT NULL THEN
    SELECT organization_id INTO NEW.organization_id FROM public.leads WHERE id = NEW.lead_id;
  ELSE
    SELECT organization_id INTO NEW.organization_id FROM public.users WHERE id = NEW.owner_id;
  END IF;
  IF NEW.organization_id IS NULL THEN
    RAISE EXCEPTION 'Cannot determine organization for this meeting' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS meetings_set_org ON public.meetings;
CREATE TRIGGER meetings_set_org BEFORE INSERT ON public.meetings
  FOR EACH ROW EXECUTE FUNCTION public.set_meeting_organization();

CREATE OR REPLACE FUNCTION public.set_proposal_organization()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  SELECT organization_id INTO NEW.organization_id
  FROM public.opportunities WHERE id = NEW.opportunity_id;
  IF NEW.organization_id IS NULL THEN
    RAISE EXCEPTION 'Cannot determine organization for this proposal' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS proposals_set_org ON public.proposals;
CREATE TRIGGER proposals_set_org BEFORE INSERT ON public.proposals
  FOR EACH ROW EXECUTE FUNCTION public.set_proposal_organization();

CREATE OR REPLACE FUNCTION public.set_notification_organization()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  SELECT organization_id INTO NEW.organization_id
  FROM public.users WHERE id = NEW.user_id;
  IF NEW.organization_id IS NULL THEN
    RAISE EXCEPTION 'Cannot determine organization for this notification' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS notifications_set_org ON public.notifications;
CREATE TRIGGER notifications_set_org BEFORE INSERT ON public.notifications
  FOR EACH ROW EXECUTE FUNCTION public.set_notification_organization();

-- marketing_channel_metrics has no natural parent row; always the caller's own org, never a
-- client-supplied value (same reasoning as set_company_organization above).
CREATE OR REPLACE FUNCTION public.set_marketing_metric_organization()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  NEW.organization_id := public.current_org_id(auth.uid());
  IF NEW.organization_id IS NULL THEN
    RAISE EXCEPTION 'Cannot determine organization for this metric' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS marketing_channel_metrics_set_org ON public.marketing_channel_metrics;
CREATE TRIGGER marketing_channel_metrics_set_org BEFORE INSERT ON public.marketing_channel_metrics
  FOR EACH ROW EXECUTE FUNCTION public.set_marketing_metric_organization();

-- users.organization_id is set directly by handle_new_user() (§8); audit_log's is set
-- directly by write_audit_log() (§11) -- neither needs a BEFORE INSERT trigger of its own.

-- ---------------------------------------------------------------------------
-- 6. Lock the column down: NOT NULL, FK, index. Safe now that §3 has backfilled every
-- existing row and §5's triggers cover every future one.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
  t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'users', 'companies', 'contacts', 'leads', 'opportunities', 'lead_intelligence',
    'activities', 'tasks', 'meetings', 'proposals', 'notifications',
    'marketing_channel_metrics', 'audit_log'
  ]
  LOOP
    EXECUTE format('ALTER TABLE public.%I ALTER COLUMN organization_id SET NOT NULL', t);
    EXECUTE format(
      'ALTER TABLE public.%I ADD CONSTRAINT %I FOREIGN KEY (organization_id) REFERENCES public.organizations (id)',
      t, t || '_organization_id_fkey'
    );
    EXECUTE format('CREATE INDEX %I ON public.%I (organization_id)', t || '_organization_idx', t);
  END LOOP;
END;
$$;

-- Two different tenants may reuse the same channel/month; scope the uniqueness accordingly.
ALTER TABLE public.marketing_channel_metrics
  DROP CONSTRAINT IF EXISTS marketing_channel_metrics_period_month_channel_key;
ALTER TABLE public.marketing_channel_metrics
  ADD CONSTRAINT marketing_channel_metrics_org_period_channel_key
  UNIQUE (organization_id, period_month, channel);

-- ---------------------------------------------------------------------------
-- 7. can_access_lead(): the central chokepoint. Everything reached only via can_access_lead
-- (opportunities, lead_intelligence, activities, proposals through opportunities) becomes
-- correctly org-scoped transitively once this one function is fixed.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.can_access_lead(uid UUID, lid UUID)
RETURNS BOOLEAN
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.leads l
    WHERE l.id = lid
      AND l.deleted_at IS NULL
      AND l.organization_id = public.current_org_id(uid)
      AND (l.owner_id = uid OR public.is_admin(uid))
  )
$$;

-- ---------------------------------------------------------------------------
-- 8. Signup: redeem a valid invite token to join an existing org, or mint a brand-new one.
--
-- A bogus, expired, already-used or email-mismatched token is treated exactly like no token
-- at all -- it grants nothing and simply falls through to "start a new tenant". This is what
-- makes the product self-serve multi-tenant without requiring any frontend change: whatever
-- signup call already exists today (no token in its metadata) falls into that branch and gets
-- a correctly isolated new org with this user as its admin.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  invite_token TEXT := NULLIF(NEW.raw_user_meta_data->>'invite_token', '');
  invite public.org_invites%ROWTYPE;
  invite_found BOOLEAN := FALSE;
  resolved_role public.user_role;
  resolved_org UUID;
  org_name TEXT;
BEGIN
  IF invite_token IS NOT NULL
     AND invite_token ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
  THEN
    SELECT * INTO invite
    FROM public.org_invites
    WHERE id = invite_token::UUID
      AND consumed_at IS NULL
      AND expires_at > NOW()
      AND lower(email) = lower(NEW.email)
    FOR UPDATE;
    invite_found := FOUND;
  END IF;

  IF invite_found THEN
    resolved_org := invite.organization_id;
    resolved_role := invite.role;
    UPDATE public.org_invites SET consumed_at = NOW() WHERE id = invite.id;
  ELSE
    org_name := COALESCE(
      NULLIF(NEW.raw_user_meta_data->>'organization_name', ''),
      NULLIF(NEW.raw_user_meta_data->>'full_name', '') || '''s workspace',
      NULLIF(split_part(NEW.email, '@', 1), '') || '''s workspace',
      'New workspace'
    );
    INSERT INTO public.organizations (name) VALUES (org_name) RETURNING id INTO resolved_org;
    resolved_role := 'admin';
  END IF;

  INSERT INTO public.users (id, email, full_name, role, organization_id)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(
      NULLIF(NEW.raw_user_meta_data->>'full_name', ''),
      NULLIF(split_part(NEW.email, '@', 1), ''),
      'User'
    ),
    resolved_role,
    resolved_org
  )
  ON CONFLICT (id) DO NOTHING;

  RETURN NEW;
END;
$$;

-- ---------------------------------------------------------------------------
-- 9. "Last active admin" must be counted per organization, not workspace-wide -- otherwise
-- an org with exactly one admin could never be blocked from losing it as soon as any other
-- org in the system also happens to have an active admin.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.guard_role_escalation()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF NEW.role IS DISTINCT FROM OLD.role AND NOT public.is_admin(auth.uid()) THEN
    RAISE EXCEPTION 'Only an admin may change a role' USING ERRCODE = '42501';
  END IF;

  IF OLD.role = 'admin' AND NEW.role <> 'admin' THEN
    IF (
      SELECT COUNT(*) FROM public.users
      WHERE role = 'admin' AND is_active AND organization_id = OLD.organization_id
    ) <= 1 THEN
      RAISE EXCEPTION 'Cannot remove the last active admin' USING ERRCODE = 'check_violation';
    END IF;
  END IF;

  IF OLD.is_active AND NOT NEW.is_active AND OLD.role = 'admin' THEN
    IF (
      SELECT COUNT(*) FROM public.users
      WHERE role = 'admin' AND is_active AND organization_id = OLD.organization_id
    ) <= 1 THEN
      RAISE EXCEPTION 'Cannot deactivate the last active admin' USING ERRCODE = 'check_violation';
    END IF;
  END IF;

  RETURN NEW;
END;
$$;

-- ---------------------------------------------------------------------------
-- 10. dashboard_metrics() and pipeline_trend() are SECURITY DEFINER and reimplement their own
-- `adm OR owner_id = uid` filter directly in SQL -- they bypass RLS entirely, so the same
-- global-admin-bypass bug exists here independently of the policies above.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.dashboard_metrics()
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  uid uuid := auth.uid();
  org uuid;
  adm boolean;
  pipeline numeric := 0;
  weighted numeric := 0;
  by_currency jsonb := '{}'::jsonb;
  currency_count int := 0;
  proposals_pending int := 0;
  wins30 int := 0;
  losses30 int := 0;
  fu_today int := 0;
  overdue int := 0;
  stage_json jsonb := '{}'::jsonb;
  hot_ids jsonb := '[]'::jsonb;
BEGIN
  IF uid IS NULL THEN
    RAISE EXCEPTION 'not authenticated';
  END IF;
  org := public.current_org_id(uid);
  adm := public.is_admin(uid);

  SELECT COALESCE(SUM(o.quoted_value), 0),
         COALESCE(SUM(o.quoted_value * (o.deal_probability::numeric / 100.0)), 0)
    INTO pipeline, weighted
  FROM public.opportunities o
  JOIN public.leads l ON l.id = o.lead_id
  WHERE l.organization_id = org AND (adm OR l.owner_id = uid);

  SELECT COALESCE(jsonb_object_agg(q.currency, q.total), '{}'::jsonb), COUNT(*)::int
    INTO by_currency, currency_count
  FROM (
    SELECT o.currency, SUM(o.quoted_value)::numeric AS total
    FROM public.opportunities o
    JOIN public.leads l ON l.id = o.lead_id
    WHERE l.organization_id = org AND (adm OR l.owner_id = uid) AND o.quoted_value IS NOT NULL
    GROUP BY o.currency
  ) AS q;

  SELECT COALESCE(
           (
             SELECT jsonb_object_agg(q.stage::text, q.ev)
             FROM (
               SELECT o.stage, SUM(o.quoted_value)::numeric AS ev
               FROM public.opportunities o
               JOIN public.leads l ON l.id = o.lead_id
               WHERE l.organization_id = org AND (adm OR l.owner_id = uid)
               GROUP BY o.stage
             ) AS q
           ),
           '{}'::jsonb
         )
    INTO stage_json;

  SELECT COUNT(*)::int INTO proposals_pending
  FROM public.proposals p
  JOIN public.opportunities o ON o.id = p.opportunity_id
  JOIN public.leads l ON l.id = o.lead_id
  WHERE p.status IN ('sent', 'under_review')
    AND l.organization_id = org AND (adm OR l.owner_id = uid);

  SELECT COUNT(*)::int INTO wins30
  FROM public.opportunities o
  JOIN public.leads l ON l.id = o.lead_id
  WHERE l.organization_id = org AND (adm OR l.owner_id = uid)
    AND o.stage = 'won'::public.lead_stage
    AND o.updated_at >= (NOW() - INTERVAL '30 days');

  SELECT COUNT(*)::int INTO losses30
  FROM public.opportunities o
  JOIN public.leads l ON l.id = o.lead_id
  WHERE l.organization_id = org AND (adm OR l.owner_id = uid)
    AND o.stage = 'lost'::public.lead_stage
    AND o.updated_at >= (NOW() - INTERVAL '30 days');

  SELECT COUNT(*)::int INTO fu_today
  FROM public.tasks t
  WHERE t.status = 'pending'::public.task_status
    AND t.due_at >= date_trunc('day', NOW())
    AND t.due_at < date_trunc('day', NOW()) + INTERVAL '1 day'
    AND t.organization_id = org AND (adm OR t.owner_id = uid);

  SELECT COUNT(*)::int INTO overdue
  FROM public.tasks t
  WHERE t.status = 'pending'::public.task_status
    AND t.due_at < NOW()
    AND t.organization_id = org AND (adm OR t.owner_id = uid);

  SELECT COALESCE(jsonb_agg(DISTINCT l.id), '[]'::jsonb)
    INTO hot_ids
  FROM public.opportunities o
  JOIN public.leads l ON l.id = o.lead_id
  WHERE l.organization_id = org AND (adm OR l.owner_id = uid)
    AND o.priority_score >= 80
    AND o.status = 'active'::public.opportunity_status
    AND l.last_contact_date IS NOT NULL
    AND (CURRENT_DATE - l.last_contact_date) > 3;

  RETURN jsonb_build_object(
    'pipeline_total', pipeline,
    'weighted_forecast', weighted,
    'pipeline_by_currency', by_currency,
    'mixed_currency', currency_count > 1,
    'stage_values', COALESCE(stage_json, '{}'::jsonb),
    'followups_today_count', fu_today,
    'overdue_tasks_count', overdue,
    'proposals_pending_response', proposals_pending,
    'hot_leads_needing_action', COALESCE(hot_ids, '[]'::jsonb),
    'win_loss_ratio_30d', jsonb_build_object('wins', wins30, 'losses', losses30)
  );
END;
$$;

CREATE OR REPLACE FUNCTION public.pipeline_trend(months INTEGER DEFAULT 6)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  uid uuid := auth.uid();
  org uuid;
  adm boolean;
  span INTEGER := GREATEST(1, LEAST(months, 24));
  result jsonb;
BEGIN
  IF uid IS NULL THEN
    RAISE EXCEPTION 'not authenticated';
  END IF;
  org := public.current_org_id(uid);
  adm := public.is_admin(uid);

  WITH bounds AS (
    SELECT date_trunc('month', NOW()) - ((span - 1) || ' months')::INTERVAL AS first_month
  ),
  buckets AS (
    SELECT generate_series(
             (SELECT first_month FROM bounds),
             date_trunc('month', NOW()),
             '1 month'::INTERVAL
           ) AS month
  ),
  visible AS (
    SELECT o.*
    FROM public.opportunities o
    JOIN public.leads l ON l.id = o.lead_id
    WHERE o.deleted_at IS NULL
      AND l.deleted_at IS NULL
      AND l.organization_id = org
      AND (adm OR l.owner_id = uid)
  ),
  won AS (
    SELECT
      date_trunc(
        'month',
        COALESCE(
          (
            SELECT MAX(a.occurred_at)
            FROM public.audit_log a
            WHERE a.table_name = 'opportunities'
              AND a.record_id = v.id
              AND a.new_values ->> 'stage' = 'won'
          ),
          v.updated_at
        )
      ) AS month,
      COALESCE(v.quoted_value, 0) AS value
    FROM visible v
    WHERE v.stage = 'won'::public.lead_stage
  ),
  opened AS (
    SELECT date_trunc('month', v.created_at) AS month,
           COALESCE(v.quoted_value, 0) AS value
    FROM visible v
  )
  SELECT jsonb_agg(
           jsonb_build_object(
             'month', to_char(b.month, 'YYYY-MM'),
             'label', to_char(b.month, 'Mon'),
             'won_value', COALESCE(w.total, 0),
             'won_count', COALESCE(w.n, 0),
             'opened_value', COALESCE(o.total, 0),
             'opened_count', COALESCE(o.n, 0)
           )
           ORDER BY b.month
         )
    INTO result
  FROM buckets b
  LEFT JOIN (
    SELECT month, SUM(value)::numeric AS total, COUNT(*)::int AS n FROM won GROUP BY month
  ) w ON w.month = b.month
  LEFT JOIN (
    SELECT month, SUM(value)::numeric AS total, COUNT(*)::int AS n FROM opened GROUP BY month
  ) o ON o.month = b.month;

  RETURN COALESCE(result, '[]'::jsonb);
END;
$$;

-- ---------------------------------------------------------------------------
-- 11. Soft-delete RPCs are SECURITY DEFINER and re-implement their own permission check
-- (see 20260822190000/20260826120000) precisely because they bypass RLS -- each one needs the
-- same org check added directly, not just the policies. soft_delete_opportunity is unchanged:
-- it already delegates entirely to can_access_lead(), fixed in §7.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.soft_delete_lead(
  p_id UUID,
  p_expected_version INTEGER DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  uid UUID := auth.uid();
  target public.leads%ROWTYPE;
BEGIN
  IF uid IS NULL THEN
    RAISE EXCEPTION 'not authenticated' USING ERRCODE = '42501';
  END IF;

  SELECT * INTO target FROM public.leads WHERE id = p_id;

  IF NOT FOUND OR target.deleted_at IS NOT NULL THEN
    RETURN jsonb_build_object('status', 'not_found');
  END IF;

  IF NOT (
    target.organization_id = public.current_org_id(uid)
    AND (target.owner_id = uid OR public.is_admin(uid))
  ) THEN
    RETURN jsonb_build_object('status', 'forbidden');
  END IF;

  IF p_expected_version IS NOT NULL AND target.version <> p_expected_version THEN
    RETURN jsonb_build_object('status', 'version_mismatch', 'current_version', target.version);
  END IF;

  UPDATE public.leads SET deleted_at = NOW() WHERE id = p_id;
  RETURN jsonb_build_object('status', 'deleted');
END;
$$;

CREATE OR REPLACE FUNCTION public.soft_delete_contact(
  p_id UUID,
  p_expected_version INTEGER DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  uid UUID := auth.uid();
  target public.contacts%ROWTYPE;
  permitted BOOLEAN;
BEGIN
  IF uid IS NULL THEN
    RAISE EXCEPTION 'not authenticated' USING ERRCODE = '42501';
  END IF;

  SELECT * INTO target FROM public.contacts WHERE id = p_id;

  IF NOT FOUND OR target.deleted_at IS NOT NULL THEN
    RETURN jsonb_build_object('status', 'not_found');
  END IF;

  SELECT target.organization_id = public.current_org_id(uid) AND (
    public.is_admin(uid) OR EXISTS (
      SELECT 1 FROM public.companies c
      WHERE c.id = target.company_id AND c.created_by = uid
    )
  ) INTO permitted;

  IF NOT permitted THEN
    RETURN jsonb_build_object('status', 'forbidden');
  END IF;

  IF EXISTS (
    SELECT 1 FROM public.leads l
    WHERE l.primary_contact_id = p_id AND l.deleted_at IS NULL
  ) THEN
    RETURN jsonb_build_object('status', 'referenced');
  END IF;

  IF p_expected_version IS NOT NULL AND target.version <> p_expected_version THEN
    RETURN jsonb_build_object('status', 'version_mismatch', 'current_version', target.version);
  END IF;

  UPDATE public.contacts SET deleted_at = NOW() WHERE id = p_id;
  RETURN jsonb_build_object('status', 'deleted');
END;
$$;

CREATE OR REPLACE FUNCTION public.soft_delete_company(
  p_id UUID,
  p_expected_version INTEGER DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  uid UUID := auth.uid();
  target public.companies%ROWTYPE;
BEGIN
  IF uid IS NULL THEN
    RAISE EXCEPTION 'not authenticated' USING ERRCODE = '42501';
  END IF;

  SELECT * INTO target FROM public.companies WHERE id = p_id;
  IF NOT FOUND OR target.deleted_at IS NOT NULL THEN
    RETURN jsonb_build_object('status', 'not_found');
  END IF;

  IF NOT (
    target.organization_id = public.current_org_id(uid)
    AND (target.created_by = uid OR public.is_admin(uid))
  ) THEN
    RETURN jsonb_build_object('status', 'forbidden');
  END IF;

  IF EXISTS (
    SELECT 1 FROM public.leads l WHERE l.company_id = p_id AND l.deleted_at IS NULL
  ) THEN
    RETURN jsonb_build_object('status', 'referenced');
  END IF;

  IF p_expected_version IS NOT NULL AND target.version <> p_expected_version THEN
    RETURN jsonb_build_object('status', 'version_mismatch', 'current_version', target.version);
  END IF;

  UPDATE public.companies SET deleted_at = NOW() WHERE id = p_id;
  RETURN jsonb_build_object('status', 'deleted');
END;
$$;

-- ---------------------------------------------------------------------------
-- 12. write_audit_log() writes generically via to_jsonb(NEW/OLD); every table it's attached
-- to (leads, opportunities, contacts, companies, proposals, lead_intelligence) now carries
-- organization_id, so it can be read straight off the row being audited.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.write_audit_log()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  actor uuid := auth.uid();
  old_json JSONB;
  new_json JSONB;
  changed TEXT[];
  record_id UUID;
  org_id UUID;
BEGIN
  IF TG_OP = 'DELETE' THEN
    old_json := to_jsonb(OLD);
    record_id := OLD.id;
    org_id := OLD.organization_id;
  ELSIF TG_OP = 'INSERT' THEN
    new_json := to_jsonb(NEW);
    record_id := NEW.id;
    org_id := NEW.organization_id;
  ELSE
    old_json := to_jsonb(OLD);
    new_json := to_jsonb(NEW);
    record_id := NEW.id;
    org_id := NEW.organization_id;

    SELECT COALESCE(array_agg(key ORDER BY key), '{}')
      INTO changed
    FROM jsonb_each(new_json) AS n(key, value)
    WHERE n.value IS DISTINCT FROM old_json -> n.key
      AND n.key NOT IN ('updated_at', 'version');

    IF changed = '{}' THEN
      RETURN NULL;
    END IF;

    old_json := (SELECT jsonb_object_agg(k, old_json -> k) FROM unnest(changed) AS k);
    new_json := (SELECT jsonb_object_agg(k, new_json -> k) FROM unnest(changed) AS k);
  END IF;

  INSERT INTO public.audit_log (
    table_name, record_id, action, actor_id, actor_type,
    changed_columns, old_values, new_values, organization_id
  )
  VALUES (
    TG_TABLE_NAME,
    record_id,
    TG_OP,
    actor,
    CASE WHEN actor IS NULL THEN 'system' ELSE 'user' END::public.actor_type,
    COALESCE(changed, '{}'),
    old_json,
    new_json,
    org_id
  );

  RETURN NULL;
END;
$$;

-- ---------------------------------------------------------------------------
-- 13. RLS policies, table by table. The pattern throughout: wrap the existing condition in
-- `organization_id = current_org_id(auth.uid()) AND (...)`. This is always safe even for the
-- "is the owner" branches (a row's organization_id is set to match its owner's org at insert
-- time, so owner_id = auth.uid() already implies the wrap is true) and closes the "is_admin()
-- alone" cross-tenant bypass on every other branch.
-- ---------------------------------------------------------------------------

-- organizations: a user may see their own org's row. Nothing else is exposed here yet
-- (no org-settings endpoint in this pass) -- created only by handle_new_user().
CREATE POLICY organizations_select ON public.organizations FOR SELECT USING (
  id = (SELECT public.current_org_id(auth.uid()))
);

-- users
DROP POLICY IF EXISTS users_select ON public.users;
CREATE POLICY users_select ON public.users FOR SELECT USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (id = (SELECT auth.uid()) OR (SELECT public.is_admin(auth.uid())))
);

DROP POLICY IF EXISTS users_update_admin ON public.users;
CREATE POLICY users_update_admin ON public.users FOR UPDATE
  USING (
    organization_id = (SELECT public.current_org_id(auth.uid()))
    AND (SELECT public.is_admin(auth.uid()))
  )
  WITH CHECK (
    organization_id = (SELECT public.current_org_id(auth.uid()))
    AND (SELECT public.is_admin(auth.uid()))
  );

-- users_update_self (id = auth.uid() only) is already maximally scoped; left unchanged.

-- companies
DROP POLICY IF EXISTS companies_select ON public.companies;
CREATE POLICY companies_select ON public.companies FOR SELECT USING (
  deleted_at IS NULL
  AND organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (
    created_by = (SELECT auth.uid())
    OR (SELECT public.is_admin(auth.uid()))
    OR EXISTS (
      SELECT 1 FROM public.leads l
      WHERE l.company_id = companies.id
        AND (SELECT public.can_access_lead(auth.uid(), l.id))
    )
  )
);

DROP POLICY IF EXISTS companies_insert ON public.companies;
CREATE POLICY companies_insert ON public.companies FOR INSERT WITH CHECK (
  (SELECT auth.uid()) IS NOT NULL
  AND organization_id = (SELECT public.current_org_id(auth.uid()))
  AND created_by = (SELECT auth.uid())
);

DROP POLICY IF EXISTS companies_update ON public.companies;
CREATE POLICY companies_update ON public.companies FOR UPDATE USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (created_by = (SELECT auth.uid()) OR (SELECT public.is_admin(auth.uid())))
);

-- contacts
DROP POLICY IF EXISTS contacts_select ON public.contacts;
CREATE POLICY contacts_select ON public.contacts FOR SELECT USING (
  deleted_at IS NULL
  AND organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (
    (SELECT public.is_admin(auth.uid()))
    OR EXISTS (
      SELECT 1 FROM public.companies c
      WHERE c.id = contacts.company_id AND c.created_by = (SELECT auth.uid())
    )
    OR EXISTS (
      SELECT 1 FROM public.leads l
      WHERE l.company_id = contacts.company_id
        AND (SELECT public.can_access_lead(auth.uid(), l.id))
    )
  )
);

DROP POLICY IF EXISTS contacts_insert ON public.contacts;
CREATE POLICY contacts_insert ON public.contacts FOR INSERT WITH CHECK (
  (SELECT auth.uid()) IS NOT NULL
  AND organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (
    EXISTS (
      SELECT 1 FROM public.companies c
      WHERE c.id = contacts.company_id
        AND (c.created_by = (SELECT auth.uid()) OR (SELECT public.is_admin(auth.uid())))
    )
    OR EXISTS (
      SELECT 1 FROM public.leads l
      WHERE l.company_id = contacts.company_id
        AND (SELECT public.can_access_lead(auth.uid(), l.id))
    )
  )
);

DROP POLICY IF EXISTS contacts_update ON public.contacts;
CREATE POLICY contacts_update ON public.contacts FOR UPDATE USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (
    (SELECT public.is_admin(auth.uid()))
    OR EXISTS (
      SELECT 1 FROM public.companies c
      WHERE c.id = contacts.company_id AND c.created_by = (SELECT auth.uid())
    )
    OR EXISTS (
      SELECT 1 FROM public.leads l
      WHERE l.company_id = contacts.company_id
        AND (SELECT public.can_access_lead(auth.uid(), l.id))
    )
  )
);

DROP POLICY IF EXISTS contacts_delete ON public.contacts;
CREATE POLICY contacts_delete ON public.contacts FOR DELETE USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (
    (SELECT public.is_admin(auth.uid()))
    OR EXISTS (
      SELECT 1 FROM public.companies c
      WHERE c.id = contacts.company_id AND c.created_by = (SELECT auth.uid())
    )
  )
);

-- leads
DROP POLICY IF EXISTS leads_select ON public.leads;
CREATE POLICY leads_select ON public.leads FOR SELECT USING (
  deleted_at IS NULL
  AND organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (owner_id = (SELECT auth.uid()) OR (SELECT public.is_admin(auth.uid())))
);

DROP POLICY IF EXISTS leads_insert ON public.leads;
CREATE POLICY leads_insert ON public.leads FOR INSERT WITH CHECK (
  (SELECT auth.uid()) IS NOT NULL
  AND organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (owner_id = (SELECT auth.uid()) OR (SELECT public.is_admin(auth.uid())))
);

DROP POLICY IF EXISTS leads_update ON public.leads;
CREATE POLICY leads_update ON public.leads
  FOR UPDATE
  USING (
    organization_id = (SELECT public.current_org_id(auth.uid()))
    AND (owner_id = (SELECT auth.uid()) OR (SELECT public.is_admin(auth.uid())))
  )
  WITH CHECK (
    organization_id = (SELECT public.current_org_id(auth.uid()))
    AND (owner_id = (SELECT auth.uid()) OR (SELECT public.is_admin(auth.uid())))
  );

-- lead_intelligence, activities, opportunities: gated via can_access_lead(), already fixed in
-- §7; the explicit organization_id check added here is redundant defense-in-depth, not load-
-- bearing on its own.
DROP POLICY IF EXISTS li_select ON public.lead_intelligence;
CREATE POLICY li_select ON public.lead_intelligence FOR SELECT USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (SELECT public.can_access_lead(auth.uid(), lead_intelligence.lead_id))
);

DROP POLICY IF EXISTS li_insert ON public.lead_intelligence;
CREATE POLICY li_insert ON public.lead_intelligence FOR INSERT WITH CHECK (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (SELECT public.can_access_lead(auth.uid(), lead_intelligence.lead_id))
);

DROP POLICY IF EXISTS li_update ON public.lead_intelligence;
CREATE POLICY li_update ON public.lead_intelligence FOR UPDATE USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (SELECT public.can_access_lead(auth.uid(), lead_intelligence.lead_id))
);

DROP POLICY IF EXISTS activities_select ON public.activities;
CREATE POLICY activities_select ON public.activities FOR SELECT USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (SELECT public.can_access_lead(auth.uid(), activities.lead_id))
);

DROP POLICY IF EXISTS activities_insert ON public.activities;
CREATE POLICY activities_insert ON public.activities FOR INSERT WITH CHECK (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (SELECT public.can_access_lead(auth.uid(), activities.lead_id))
  AND performed_by = (SELECT auth.uid())
);

DROP POLICY IF EXISTS opp_select ON public.opportunities;
CREATE POLICY opp_select ON public.opportunities FOR SELECT USING (
  deleted_at IS NULL
  AND organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (SELECT public.can_access_lead(auth.uid(), opportunities.lead_id))
);

DROP POLICY IF EXISTS opp_insert ON public.opportunities;
CREATE POLICY opp_insert ON public.opportunities FOR INSERT WITH CHECK (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (SELECT public.can_access_lead(auth.uid(), opportunities.lead_id))
);

DROP POLICY IF EXISTS opp_update ON public.opportunities;
CREATE POLICY opp_update ON public.opportunities FOR UPDATE USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (SELECT public.can_access_lead(auth.uid(), opportunities.lead_id))
);

-- proposals
DROP POLICY IF EXISTS prop_select ON public.proposals;
CREATE POLICY prop_select ON public.proposals FOR SELECT USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND EXISTS (
    SELECT 1 FROM public.opportunities o
    WHERE o.id = proposals.opportunity_id
      AND (SELECT public.can_access_lead(auth.uid(), o.lead_id))
  )
);

DROP POLICY IF EXISTS prop_insert ON public.proposals;
CREATE POLICY prop_insert ON public.proposals FOR INSERT WITH CHECK (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND EXISTS (
    SELECT 1 FROM public.opportunities o
    WHERE o.id = proposals.opportunity_id
      AND (SELECT public.can_access_lead(auth.uid(), o.lead_id))
  )
);

DROP POLICY IF EXISTS prop_update ON public.proposals;
CREATE POLICY prop_update ON public.proposals FOR UPDATE USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND EXISTS (
    SELECT 1 FROM public.opportunities o
    WHERE o.id = proposals.opportunity_id
      AND (SELECT public.can_access_lead(auth.uid(), o.lead_id))
  )
);

DROP POLICY IF EXISTS prop_delete ON public.proposals;
CREATE POLICY prop_delete ON public.proposals FOR DELETE USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND status = 'draft'::public.proposal_status
  AND EXISTS (
    SELECT 1 FROM public.opportunities o
    WHERE o.id = proposals.opportunity_id
      AND (SELECT public.can_access_lead(auth.uid(), o.lead_id))
  )
);

-- tasks
DROP POLICY IF EXISTS tasks_select ON public.tasks;
CREATE POLICY tasks_select ON public.tasks FOR SELECT USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (owner_id = (SELECT auth.uid()) OR (SELECT public.is_admin(auth.uid())))
);

DROP POLICY IF EXISTS tasks_insert ON public.tasks;
CREATE POLICY tasks_insert ON public.tasks FOR INSERT WITH CHECK (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (owner_id = (SELECT auth.uid()) OR (SELECT public.is_admin(auth.uid())))
);

DROP POLICY IF EXISTS tasks_update ON public.tasks;
CREATE POLICY tasks_update ON public.tasks FOR UPDATE USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (owner_id = (SELECT auth.uid()) OR (SELECT public.is_admin(auth.uid())))
);

DROP POLICY IF EXISTS tasks_delete ON public.tasks;
CREATE POLICY tasks_delete ON public.tasks FOR DELETE USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (owner_id = (SELECT auth.uid()) OR (SELECT public.is_admin(auth.uid())))
);

-- meetings
DROP POLICY IF EXISTS meetings_select ON public.meetings;
CREATE POLICY meetings_select ON public.meetings FOR SELECT USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (owner_id = (SELECT auth.uid()) OR (SELECT public.is_admin(auth.uid())))
);

DROP POLICY IF EXISTS meetings_insert ON public.meetings;
CREATE POLICY meetings_insert ON public.meetings FOR INSERT WITH CHECK (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (owner_id = (SELECT auth.uid()) OR (SELECT public.is_admin(auth.uid())))
);

DROP POLICY IF EXISTS meetings_update ON public.meetings;
CREATE POLICY meetings_update ON public.meetings FOR UPDATE USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (owner_id = (SELECT auth.uid()) OR (SELECT public.is_admin(auth.uid())))
);

DROP POLICY IF EXISTS meetings_delete ON public.meetings;
CREATE POLICY meetings_delete ON public.meetings FOR DELETE USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (owner_id = (SELECT auth.uid()) OR (SELECT public.is_admin(auth.uid())))
);

-- notifications: user_id = auth.uid() is already the tightest possible scope (a user belongs
-- to exactly one org, so this can never cross tenants); left unchanged.

-- marketing_channel_metrics: previously `auth.uid() IS NOT NULL` for SELECT -- any signed-in
-- user, in any organization, could read every tenant's spend figures. This was the worst of
-- the pre-existing leaks.
DROP POLICY IF EXISTS marketing_metrics_select ON public.marketing_channel_metrics;
CREATE POLICY marketing_metrics_select ON public.marketing_channel_metrics FOR SELECT USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
);

DROP POLICY IF EXISTS marketing_metrics_insert ON public.marketing_channel_metrics;
CREATE POLICY marketing_metrics_insert ON public.marketing_channel_metrics FOR INSERT WITH CHECK (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (SELECT public.is_admin(auth.uid()))
);

DROP POLICY IF EXISTS marketing_metrics_update ON public.marketing_channel_metrics;
CREATE POLICY marketing_metrics_update ON public.marketing_channel_metrics FOR UPDATE USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (SELECT public.is_admin(auth.uid()))
);

DROP POLICY IF EXISTS marketing_metrics_delete ON public.marketing_channel_metrics;
CREATE POLICY marketing_metrics_delete ON public.marketing_channel_metrics FOR DELETE USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (SELECT public.is_admin(auth.uid()))
);

-- audit_log
DROP POLICY IF EXISTS audit_log_select ON public.audit_log;
CREATE POLICY audit_log_select ON public.audit_log FOR SELECT USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (actor_id = (SELECT auth.uid()) OR (SELECT public.is_admin(auth.uid())))
);

COMMENT ON COLUMN public.leads.organization_id IS
  'Set once by set_lead_organization() at insert; immutable thereafter. The tenant boundary '
  'every other lead-scoped table (opportunities, activities, tasks, ...) inherits from.';
