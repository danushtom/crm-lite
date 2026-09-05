-- Fixes from reviewing 20260905120000_organizations.sql.
--
-- One is a real security hole; the rest are correctness/perf/maintainability cleanups found
-- reviewing the same diff. 20260905120000 is already applied, so these land as CREATE OR
-- REPLACE / targeted ALTERs rather than edits to that file.

-- ---------------------------------------------------------------------------
-- 1. SECURITY: users_update_self let a user hijack their way into another organization.
--
-- users_update_self (USING/WITH CHECK: id = auth.uid()) says nothing about organization_id,
-- which this feature turned into a real, load-bearing tenant-boundary column. A user calling
-- PostgREST directly with their own token -- bypassing the FastAPI app, whose CurrentUserUpdate
-- schema never exposes this field -- could PATCH their own row's organization_id to any other
-- tenant's id and immediately gain that tenant's data scope everywhere current_org_id() is
-- trusted. RLS has no way to express "this column may never change" in a single policy (USING
-- sees only the old row, WITH CHECK only the new one), so the guard belongs in the trigger that
-- already exists for exactly this class of problem.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.guard_role_escalation()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  admin_count INTEGER;
BEGIN
  IF NEW.role IS DISTINCT FROM OLD.role AND NOT public.is_admin(auth.uid()) THEN
    RAISE EXCEPTION 'Only an admin may change a role' USING ERRCODE = '42501';
  END IF;

  -- Organization membership changes only through handle_new_user() (a fresh signup or a
  -- redeemed invite) -- never a raw UPDATE, by anyone, admin included.
  IF NEW.organization_id IS DISTINCT FROM OLD.organization_id THEN
    RAISE EXCEPTION 'organization_id cannot be changed' USING ERRCODE = '42501';
  END IF;

  -- Combines what were two separate, identical COUNT(*) queries (one per condition) into one.
  IF (OLD.role = 'admin' AND NEW.role <> 'admin')
     OR (OLD.is_active AND NOT NEW.is_active AND OLD.role = 'admin') THEN
    SELECT COUNT(*) INTO admin_count
    FROM public.users
    WHERE role = 'admin' AND is_active AND organization_id = OLD.organization_id;

    IF admin_count <= 1 THEN
      IF OLD.role = 'admin' AND NEW.role <> 'admin' THEN
        RAISE EXCEPTION 'Cannot remove the last active admin' USING ERRCODE = 'check_violation';
      ELSE
        RAISE EXCEPTION 'Cannot deactivate the last active admin' USING ERRCODE = 'check_violation';
      END IF;
    END IF;
  END IF;

  RETURN NEW;
END;
$$;

-- ---------------------------------------------------------------------------
-- 2. set_marketing_metric_organization() broke every service-role insert (auth.uid() IS NULL
-- under a service-role connection, e.g. scripts/seed_database.py), since it unconditionally
-- derived organization_id from auth.uid() and nothing else. A service-role caller has already
-- bypassed RLS entirely, so it can be trusted to state the organization directly; only an
-- authenticated end-user request (auth.uid() IS NOT NULL) needs the value force-overwritten so
-- it can't be spoofed via a direct PostgREST call.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.set_marketing_metric_organization()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF auth.uid() IS NOT NULL THEN
    NEW.organization_id := public.current_org_id(auth.uid());
  END IF;
  IF NEW.organization_id IS NULL THEN
    RAISE EXCEPTION 'Cannot determine organization for this metric' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

-- ---------------------------------------------------------------------------
-- 3. can_access_lead() called current_org_id() and is_admin() as two separate SECURITY
-- DEFINER function calls, each independently querying public.users for the same auth.uid().
-- Neither is inlinable, and can_access_lead is itself invoked once per row from several other
-- tables' policies, so this doubled a per-row users lookup that a single JOIN avoids.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.can_access_lead(uid UUID, lid UUID)
RETURNS BOOLEAN
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM public.leads l
    JOIN public.users u ON u.id = uid
    WHERE l.id = lid
      AND l.deleted_at IS NULL
      AND l.organization_id = u.organization_id
      AND (l.owner_id = uid OR u.role = 'admin')
  )
$$;

-- ---------------------------------------------------------------------------
-- 4. dashboard_metrics() never filtered out soft-deleted opportunities/leads (a gap that
-- predates this feature -- soft delete was added after this function was last written), so a
-- deleted deal still counted toward pipeline totals, stage breakdowns and win/loss ratios.
-- pipeline_trend(), added alongside dashboard_metrics in the same prior migration, already
-- filters both; bringing dashboard_metrics in line while it's already being touched here.
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
  WHERE o.deleted_at IS NULL AND l.deleted_at IS NULL
    AND l.organization_id = org AND (adm OR l.owner_id = uid);

  SELECT COALESCE(jsonb_object_agg(q.currency, q.total), '{}'::jsonb), COUNT(*)::int
    INTO by_currency, currency_count
  FROM (
    SELECT o.currency, SUM(o.quoted_value)::numeric AS total
    FROM public.opportunities o
    JOIN public.leads l ON l.id = o.lead_id
    WHERE o.deleted_at IS NULL AND l.deleted_at IS NULL
      AND l.organization_id = org AND (adm OR l.owner_id = uid) AND o.quoted_value IS NOT NULL
    GROUP BY o.currency
  ) AS q;

  SELECT COALESCE(
           (
             SELECT jsonb_object_agg(q.stage::text, q.ev)
             FROM (
               SELECT o.stage, SUM(o.quoted_value)::numeric AS ev
               FROM public.opportunities o
               JOIN public.leads l ON l.id = o.lead_id
               WHERE o.deleted_at IS NULL AND l.deleted_at IS NULL
                 AND l.organization_id = org AND (adm OR l.owner_id = uid)
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
    AND o.deleted_at IS NULL AND l.deleted_at IS NULL
    AND l.organization_id = org AND (adm OR l.owner_id = uid);

  SELECT COUNT(*)::int INTO wins30
  FROM public.opportunities o
  JOIN public.leads l ON l.id = o.lead_id
  WHERE o.deleted_at IS NULL AND l.deleted_at IS NULL
    AND l.organization_id = org AND (adm OR l.owner_id = uid)
    AND o.stage = 'won'::public.lead_stage
    AND o.updated_at >= (NOW() - INTERVAL '30 days');

  SELECT COUNT(*)::int INTO losses30
  FROM public.opportunities o
  JOIN public.leads l ON l.id = o.lead_id
  WHERE o.deleted_at IS NULL AND l.deleted_at IS NULL
    AND l.organization_id = org AND (adm OR l.owner_id = uid)
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
  WHERE o.deleted_at IS NULL AND l.deleted_at IS NULL
    AND l.organization_id = org AND (adm OR l.owner_id = uid)
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

-- ---------------------------------------------------------------------------
-- 5. Eight near-identical set_*_organization() BEFORE INSERT functions collapsed into one,
-- parametrized by TG_ARGV -- the same dynamic-trigger idiom this codebase already uses (see
-- bump_version()'s per-table trigger loop in 20260822150000_concurrency_audit_and_timestamps.sql
-- and the field-generic to_jsonb(NEW) read in write_audit_log()). set_lead_organization()
-- (extra owner/company org-match validation), set_meeting_organization() (branches on nullable
-- lead_id) and set_marketing_metric_organization() (derives from auth.uid(), not a parent row)
-- genuinely differ in logic and stay separate.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.set_parent_organization()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  fk_value UUID;
BEGIN
  fk_value := (to_jsonb(NEW) ->> TG_ARGV[1])::UUID;
  EXECUTE format('SELECT organization_id FROM public.%I WHERE id = $1', TG_ARGV[0])
    INTO NEW.organization_id
    USING fk_value;
  IF NEW.organization_id IS NULL THEN
    RAISE EXCEPTION 'Cannot determine organization for %.% = %', TG_TABLE_NAME, TG_ARGV[1], fk_value
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS companies_set_org ON public.companies;
CREATE TRIGGER companies_set_org BEFORE INSERT ON public.companies
  FOR EACH ROW EXECUTE FUNCTION public.set_parent_organization('users', 'created_by');

DROP TRIGGER IF EXISTS contacts_set_org ON public.contacts;
CREATE TRIGGER contacts_set_org BEFORE INSERT ON public.contacts
  FOR EACH ROW EXECUTE FUNCTION public.set_parent_organization('companies', 'company_id');

DROP TRIGGER IF EXISTS opportunities_set_org ON public.opportunities;
CREATE TRIGGER opportunities_set_org BEFORE INSERT ON public.opportunities
  FOR EACH ROW EXECUTE FUNCTION public.set_parent_organization('leads', 'lead_id');

DROP TRIGGER IF EXISTS lead_intelligence_set_org ON public.lead_intelligence;
CREATE TRIGGER lead_intelligence_set_org BEFORE INSERT ON public.lead_intelligence
  FOR EACH ROW EXECUTE FUNCTION public.set_parent_organization('leads', 'lead_id');

DROP TRIGGER IF EXISTS activities_set_org ON public.activities;
CREATE TRIGGER activities_set_org BEFORE INSERT ON public.activities
  FOR EACH ROW EXECUTE FUNCTION public.set_parent_organization('leads', 'lead_id');

DROP TRIGGER IF EXISTS tasks_set_org ON public.tasks;
CREATE TRIGGER tasks_set_org BEFORE INSERT ON public.tasks
  FOR EACH ROW EXECUTE FUNCTION public.set_parent_organization('leads', 'lead_id');

DROP TRIGGER IF EXISTS proposals_set_org ON public.proposals;
CREATE TRIGGER proposals_set_org BEFORE INSERT ON public.proposals
  FOR EACH ROW EXECUTE FUNCTION public.set_parent_organization('opportunities', 'opportunity_id');

DROP TRIGGER IF EXISTS notifications_set_org ON public.notifications;
CREATE TRIGGER notifications_set_org BEFORE INSERT ON public.notifications
  FOR EACH ROW EXECUTE FUNCTION public.set_parent_organization('users', 'user_id');

DROP FUNCTION IF EXISTS public.set_company_organization();
DROP FUNCTION IF EXISTS public.set_contact_organization();
DROP FUNCTION IF EXISTS public.set_lead_child_organization();
DROP FUNCTION IF EXISTS public.set_proposal_organization();
DROP FUNCTION IF EXISTS public.set_notification_organization();

-- ---------------------------------------------------------------------------
-- 6. The composite UNIQUE(organization_id, period_month, channel) constraint already backs an
-- index with organization_id as its leading column, making the separate single-column index
-- pure write overhead with no read benefit.
-- ---------------------------------------------------------------------------
DROP INDEX IF EXISTS public.marketing_channel_metrics_organization_idx;

COMMENT ON FUNCTION public.set_parent_organization IS
  'Generic BEFORE INSERT organization_id populator: TG_ARGV[0] = parent table, TG_ARGV[1] = '
  'this table''s FK column into it. See set_lead_organization/set_meeting_organization/'
  'set_marketing_metric_organization for the cases that do not fit this shape.';
