-- =============================================================================
-- Dracara Growth OS -- consolidated baseline schema
--
-- Generated from `supabase db dump -s public` against the live project on
-- 2026-09-05 (i.e. this is the actual current schema, not a reconstruction
-- from the migration history). It replaces 22 incremental migrations
-- ("fix_leads_rls_self_reference", "separate_leads_from_opportunities",
-- "complete_delete_coverage", ...) that are kept only as history in
-- supabase/migrations_archive/ -- this file is the single source of truth
-- for the schema going forward. Every statement below is pg_dump's own
-- output, reorganized into labeled sections and stripped of ownership/
-- session noise; nothing was hand-retyped.
--
-- Validated end-to-end against an empty local Supabase project (`supabase
-- start` + `supabase db reset`): the resulting schema was diffed
-- statement-for-statement against the live dump (zero mismatches across
-- types, tables, columns, functions, triggers, indexes, policies,
-- constraints and foreign keys), and real signups (self-serve and via a
-- redeemed org_invites token) were run against it directly to confirm the
-- auth.users -> handle_new_user() trigger chain actually works -- see (3)
-- below, which a schema-only diff cannot catch.
--
-- One thing `supabase db dump -s public` cannot see and this file adds back
-- by hand: `on_auth_user_created` is a trigger ON auth.users (a table
-- outside the public schema), even though its function lives in public.
-- A schema-only dump of "public" silently omits it. Without this trigger,
-- no signup would ever get a row in public.users.
-- =============================================================================

-- check_function_bodies is off because SQL-language functions below (is_admin,
-- current_org_id, can_access_lead) are defined before the tables they query --
-- matching this file's function-then-table ordering, which mirrors how
-- pg_dump itself safely orders a restore.
SET check_function_bodies = false;

-- -----------------------------------------------------------------------------
-- Extensions
-- -----------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "pgcrypto" WITH SCHEMA "extensions";
-- Installed into "public" on the live project (not the usual "extensions" schema) --
-- gin_trgm_ops is referenced unqualified as public.gin_trgm_ops by the indexes below, so it
-- has to live here for them to resolve.
CREATE EXTENSION IF NOT EXISTS "pg_trgm" WITH SCHEMA "public";


-- -----------------------------------------------------------------------------
-- Custom Types (Enums)
-- -----------------------------------------------------------------------------

CREATE TYPE "public"."activity_type" AS ENUM (
    'call',
    'email',
    'meeting',
    'note',
    'stage_change',
    'proposal_sent',
    'task_created',
    'task_completed',
    'document_uploaded'
);

CREATE TYPE "public"."actor_type" AS ENUM (
    'user',
    'system'
);

CREATE TYPE "public"."comm_preference" AS ENUM (
    'whatsapp',
    'email',
    'linkedin',
    'phone',
    'call'
);

CREATE TYPE "public"."company_segment" AS ENUM (
    'sme',
    'startup',
    'enterprise'
);

CREATE TYPE "public"."lead_source" AS ENUM (
    'cold_call',
    'referral',
    'website',
    'linkedin',
    'other'
);

CREATE TYPE "public"."lead_stage" AS ENUM (
    'prospect',
    'contacting',
    'discovery_scheduled',
    'requirements_gathering',
    'solution_design',
    'proposal_sent',
    'negotiation',
    'won',
    'delivery_transition',
    'on_hold',
    'followup_later',
    'lost'
);

CREATE TYPE "public"."meeting_outcome" AS ENUM (
    'interested',
    'needs_proposal',
    'budget_issue',
    'not_interested',
    'followup_later'
);

CREATE TYPE "public"."meeting_status" AS ENUM (
    'scheduled',
    'completed',
    'cancelled',
    'rescheduled'
);

CREATE TYPE "public"."opportunity_status" AS ENUM (
    'active',
    'won',
    'lost',
    'on_hold'
);

CREATE TYPE "public"."project_type" AS ENUM (
    'mvp',
    'saas',
    'ai',
    'webapp',
    'erp',
    'other'
);

CREATE TYPE "public"."proposal_status" AS ENUM (
    'draft',
    'sent',
    'under_review',
    'accepted',
    'rejected'
);

CREATE TYPE "public"."task_status" AS ENUM (
    'pending',
    'snoozed',
    'completed',
    'cancelled'
);

CREATE TYPE "public"."user_role" AS ENUM (
    'admin',
    'agent',
    'sdr',
    'partner'
);


-- -----------------------------------------------------------------------------
-- Functions
-- -----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION "public"."bump_version"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public'
    AS $$
BEGIN
  IF (to_jsonb(NEW) - 'updated_at' - 'version')
     IS DISTINCT FROM
     (to_jsonb(OLD) - 'updated_at' - 'version')
  THEN
    NEW.version = COALESCE(OLD.version, 0) + 1;
  ELSE
    NEW.version = OLD.version;
    NEW.updated_at = OLD.updated_at;
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION "public"."can_access_lead"("uid" "uuid", "lid" "uuid") RETURNS boolean
    LANGUAGE "sql" STABLE SECURITY DEFINER
    SET "search_path" TO 'public'
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

CREATE OR REPLACE FUNCTION "public"."current_org_id"("uid" "uuid") RETURNS "uuid"
    LANGUAGE "sql" STABLE SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
  SELECT organization_id FROM public.users WHERE id = uid
$$;

CREATE OR REPLACE FUNCTION "public"."dashboard_metrics"() RETURNS "jsonb"
    LANGUAGE "plpgsql" STABLE SECURITY DEFINER
    SET "search_path" TO 'public'
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

COMMENT ON FUNCTION "public"."dashboard_metrics"() IS 'Dashboard KPIs scoped to auth.uid(); admins see org totals. pipeline_total is only meaningful when mixed_currency is false -- read pipeline_by_currency otherwise.';

CREATE OR REPLACE FUNCTION "public"."ensure_lead_intelligence"() RETURNS "trigger"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
BEGIN
  INSERT INTO public.lead_intelligence (lead_id) VALUES (NEW.id);
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION "public"."ensure_opportunity_for_lead"() RETURNS "trigger"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
BEGIN
  INSERT INTO public.opportunities (lead_id, owner_id, title, stage, status)
  VALUES (
    NEW.id,
    NEW.owner_id,
    'Initial pursuit',
    'prospect'::public.lead_stage,
    'active'::public.opportunity_status
  );
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION "public"."guard_role_escalation"() RETURNS "trigger"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
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

CREATE OR REPLACE FUNCTION "public"."handle_new_user"() RETURNS "trigger"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $_$
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
$_$;

CREATE OR REPLACE FUNCTION "public"."is_admin"("uid" "uuid") RETURNS boolean
    LANGUAGE "sql" STABLE SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
  SELECT EXISTS (SELECT 1 FROM public.users u WHERE u.id = uid AND u.role = 'admin')
$$;

CREATE OR REPLACE FUNCTION "public"."log_lead_stage_change"() RETURNS "trigger"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
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

CREATE OR REPLACE FUNCTION "public"."log_opportunity_stage_change"() RETURNS "trigger"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
DECLARE
  actor uuid := auth.uid();
BEGIN
  IF TG_OP = 'UPDATE' AND OLD.stage IS DISTINCT FROM NEW.stage THEN
    INSERT INTO public.activities (
      lead_id, type, description, performed_by, actor_type, metadata
    )
    VALUES (
      NEW.lead_id,
      'stage_change'::public.activity_type,
      'Opportunity stage changed from ' || OLD.stage::TEXT || ' to ' || NEW.stage::TEXT,
      actor,
      CASE WHEN actor IS NULL THEN 'system' ELSE 'user' END::public.actor_type,
      jsonb_build_object(
        'opportunity_id', NEW.id::TEXT,
        'old_stage', OLD.stage::TEXT,
        'new_stage', NEW.stage::TEXT
      )
    );
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION "public"."pipeline_trend"("months" integer DEFAULT 6) RETURNS "jsonb"
    LANGUAGE "plpgsql" STABLE SECURITY DEFINER
    SET "search_path" TO 'public'
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

COMMENT ON FUNCTION "public"."pipeline_trend"("months" integer) IS 'Monthly won and opened value, scoped by RLS. Replaces a chart that was generated from a formula over the current pipeline total and described nothing that had happened.';

CREATE OR REPLACE FUNCTION "public"."prune_idempotency_keys"("older_than" interval DEFAULT '24:00:00'::interval) RETURNS integer
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
DECLARE
  removed INTEGER;
BEGIN
  DELETE FROM public.idempotency_keys WHERE created_at < NOW() - older_than;
  GET DIAGNOSTICS removed = ROW_COUNT;
  RETURN removed;
END;
$$;

CREATE OR REPLACE FUNCTION "public"."set_lead_organization"() RETURNS "trigger"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
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

CREATE OR REPLACE FUNCTION "public"."set_marketing_metric_organization"() RETURNS "trigger"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
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

CREATE OR REPLACE FUNCTION "public"."set_meeting_organization"() RETURNS "trigger"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
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

CREATE OR REPLACE FUNCTION "public"."set_parent_organization"() RETURNS "trigger"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $_$
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
$_$;

COMMENT ON FUNCTION "public"."set_parent_organization"() IS 'Generic BEFORE INSERT organization_id populator: TG_ARGV[0] = parent table, TG_ARGV[1] = this table''s FK column into it. See set_lead_organization/set_meeting_organization/set_marketing_metric_organization for the cases that do not fit this shape.';

CREATE OR REPLACE FUNCTION "public"."soft_delete_company"("p_id" "uuid", "p_expected_version" integer DEFAULT NULL::integer) RETURNS "jsonb"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
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

CREATE OR REPLACE FUNCTION "public"."soft_delete_contact"("p_id" "uuid", "p_expected_version" integer DEFAULT NULL::integer) RETURNS "jsonb"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
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

CREATE OR REPLACE FUNCTION "public"."soft_delete_lead"("p_id" "uuid", "p_expected_version" integer DEFAULT NULL::integer) RETURNS "jsonb"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
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

COMMENT ON FUNCTION "public"."soft_delete_lead"("p_id" "uuid", "p_expected_version" integer) IS 'Marks a lead deleted. SECURITY DEFINER because the resulting row is hidden by the SELECT policy, which PostgREST cannot satisfy; the ownership check is therefore explicit here.';

CREATE OR REPLACE FUNCTION "public"."soft_delete_opportunity"("p_id" "uuid", "p_expected_version" integer DEFAULT NULL::integer) RETURNS "jsonb"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
DECLARE
  uid UUID := auth.uid();
  target public.opportunities%ROWTYPE;
BEGIN
  IF uid IS NULL THEN
    RAISE EXCEPTION 'not authenticated' USING ERRCODE = '42501';
  END IF;

  SELECT * INTO target FROM public.opportunities WHERE id = p_id;
  IF NOT FOUND OR target.deleted_at IS NOT NULL THEN
    RETURN jsonb_build_object('status', 'not_found');
  END IF;

  IF NOT public.can_access_lead(uid, target.lead_id) THEN
    RETURN jsonb_build_object('status', 'forbidden');
  END IF;

  IF p_expected_version IS NOT NULL AND target.version <> p_expected_version THEN
    RETURN jsonb_build_object('status', 'version_mismatch', 'current_version', target.version);
  END IF;

  UPDATE public.opportunities SET deleted_at = NOW() WHERE id = p_id;
  RETURN jsonb_build_object('status', 'deleted');
END;
$$;

CREATE OR REPLACE FUNCTION "public"."touch_updated_at"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public'
    AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION "public"."validate_user_timezone"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO 'public'
    AS $$
BEGIN
  IF NEW.timezone IS NULL OR NOT EXISTS (
    SELECT 1 FROM pg_timezone_names WHERE name = NEW.timezone
  ) THEN
    RAISE EXCEPTION 'Unknown IANA timezone: %', NEW.timezone
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION "public"."write_audit_log"() RETURNS "trigger"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
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


-- -----------------------------------------------------------------------------
-- Tables
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS "public"."activities" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "lead_id" "uuid" NOT NULL,
    "type" "public"."activity_type" NOT NULL,
    "description" "text" NOT NULL,
    "outcome" "text",
    "performed_by" "uuid",
    "performed_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "metadata" "jsonb",
    "actor_type" "public"."actor_type" DEFAULT 'user'::"public"."actor_type" NOT NULL,
    "organization_id" "uuid" NOT NULL
);

CREATE TABLE IF NOT EXISTS "public"."audit_log" (
    "id" bigint NOT NULL,
    "table_name" "text" NOT NULL,
    "record_id" "uuid" NOT NULL,
    "action" "text" NOT NULL,
    "actor_id" "uuid",
    "actor_type" "public"."actor_type" DEFAULT 'user'::"public"."actor_type" NOT NULL,
    "changed_columns" "text"[] DEFAULT '{}'::"text"[] NOT NULL,
    "old_values" "jsonb",
    "new_values" "jsonb",
    "occurred_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "organization_id" "uuid" NOT NULL,
    CONSTRAINT "audit_log_action_check" CHECK (("action" = ANY (ARRAY['INSERT'::"text", 'UPDATE'::"text", 'DELETE'::"text"])))
);

COMMENT ON TABLE "public"."audit_log" IS 'Append-only change history written by trigger. No write policies exist: rows arrive only via write_audit_log(), so the log cannot be edited through the API.';

ALTER TABLE "public"."audit_log" ALTER COLUMN "id" ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME "public"."audit_log_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

CREATE TABLE IF NOT EXISTS "public"."companies" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "name" "text" NOT NULL,
    "industry" "text",
    "size" "text",
    "website" "text",
    "location" "text",
    "created_by" "uuid",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "logo_url" "text",
    "linkedin_url" "text",
    "segment" "public"."company_segment",
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "version" integer DEFAULT 1 NOT NULL,
    "deleted_at" timestamp with time zone,
    "organization_id" "uuid" NOT NULL
);

CREATE TABLE IF NOT EXISTS "public"."contacts" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "company_id" "uuid" NOT NULL,
    "full_name" "text" NOT NULL,
    "role" "text",
    "email" "text",
    "phone" "text",
    "linkedin_url" "text",
    "is_primary" boolean DEFAULT false NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "avatar_url" "text",
    "source" "public"."lead_source",
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "version" integer DEFAULT 1 NOT NULL,
    "deleted_at" timestamp with time zone,
    "organization_id" "uuid" NOT NULL
);

CREATE TABLE IF NOT EXISTS "public"."idempotency_keys" (
    "id" bigint NOT NULL,
    "caller_hash" "text" NOT NULL,
    "idempotency_key" "text" NOT NULL,
    "endpoint" "text" NOT NULL,
    "request_hash" "text" NOT NULL,
    "status_code" integer NOT NULL,
    "response_body" "jsonb",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);

COMMENT ON TABLE "public"."idempotency_keys" IS 'Replay cache for POST requests carrying Idempotency-Key. Service-role access only; prune rows older than 24 hours.';

ALTER TABLE "public"."idempotency_keys" ALTER COLUMN "id" ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME "public"."idempotency_keys_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

CREATE TABLE IF NOT EXISTS "public"."lead_intelligence" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "lead_id" "uuid" NOT NULL,
    "pain_points" "text",
    "tech_stack" "text",
    "budget_hints" "text",
    "decision_makers" "text",
    "competitors_involved" "text",
    "objections_raised" "text",
    "strategic_notes" "text",
    "comm_preference" "public"."comm_preference" DEFAULT 'email'::"public"."comm_preference" NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_by" "uuid",
    "version" integer DEFAULT 1 NOT NULL,
    "organization_id" "uuid" NOT NULL
);

CREATE TABLE IF NOT EXISTS "public"."leads" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "company_id" "uuid" NOT NULL,
    "primary_contact_id" "uuid",
    "owner_id" "uuid" NOT NULL,
    "project_type" "public"."project_type" NOT NULL,
    "lead_source" "public"."lead_source" NOT NULL,
    "last_contact_date" "date",
    "next_followup_date" "date",
    "no_touch_alert" boolean DEFAULT false NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "version" integer DEFAULT 1 NOT NULL,
    "tags" "text"[] DEFAULT '{}'::"text"[] NOT NULL,
    "deleted_at" timestamp with time zone,
    "organization_id" "uuid" NOT NULL
);

COMMENT ON TABLE "public"."leads" IS 'Qualification record: who the prospect is and how to work them. Pipeline position and commercials live on public.opportunities, one or more per lead.';

COMMENT ON COLUMN "public"."leads"."tags" IS 'Free-form labels categorising the prospect. Owned here; pursuits do not carry their own.';

COMMENT ON COLUMN "public"."leads"."deleted_at" IS 'Soft delete. SELECT policies hide these rows; the data is retained for recovery and audit.';

COMMENT ON COLUMN "public"."leads"."organization_id" IS 'Set once by set_lead_organization() at insert; immutable thereafter. The tenant boundary every other lead-scoped table (opportunities, activities, tasks, ...) inherits from.';

CREATE TABLE IF NOT EXISTS "public"."marketing_channel_metrics" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "period_month" "date" NOT NULL,
    "channel" "text" NOT NULL,
    "spend" numeric(12,2),
    "new_customer_share" numeric(7,4),
    "metadata" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "organization_id" "uuid" NOT NULL
);

COMMENT ON TABLE "public"."marketing_channel_metrics" IS 'CAC / acquisition channel spend snapshots; write restricted to admin.';

CREATE TABLE IF NOT EXISTS "public"."meetings" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "lead_id" "uuid",
    "owner_id" "uuid" NOT NULL,
    "title" "text" NOT NULL,
    "google_event_id" "text",
    "google_meet_link" "text",
    "scheduled_at" timestamp with time zone NOT NULL,
    "duration_minutes" integer DEFAULT 30 NOT NULL,
    "status" "public"."meeting_status" DEFAULT 'scheduled'::"public"."meeting_status" NOT NULL,
    "outcome" "public"."meeting_outcome",
    "outcome_notes" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "version" integer DEFAULT 1 NOT NULL,
    "organization_id" "uuid" NOT NULL
);

CREATE TABLE IF NOT EXISTS "public"."notifications" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "type" "text" NOT NULL,
    "title" "text" NOT NULL,
    "body" "text",
    "metadata" "jsonb" DEFAULT '{}'::"jsonb",
    "read_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "source_task_id" "uuid",
    "meeting_id" "uuid",
    "dedupe_key" "text",
    "organization_id" "uuid" NOT NULL
);

COMMENT ON TABLE "public"."notifications" IS 'In-app notifications; worker uses service role to insert for arbitrary users.';

CREATE TABLE IF NOT EXISTS "public"."opportunities" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "lead_id" "uuid" NOT NULL,
    "owner_id" "uuid" NOT NULL,
    "title" "text" NOT NULL,
    "quoted_value" numeric(12,2),
    "currency" "text" DEFAULT 'INR'::"text" NOT NULL,
    "timeline_weeks" integer,
    "tech_stack" "text",
    "requirements_doc" "text",
    "architecture_notes" "text",
    "status" "public"."opportunity_status" DEFAULT 'active'::"public"."opportunity_status" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "stage" "public"."lead_stage" DEFAULT 'prospect'::"public"."lead_stage" NOT NULL,
    "deal_probability" smallint DEFAULT 50 NOT NULL,
    "priority_score" smallint DEFAULT 0 NOT NULL,
    "version" integer DEFAULT 1 NOT NULL,
    "score_override" smallint,
    "score_override_reason" "text",
    "deleted_at" timestamp with time zone,
    "organization_id" "uuid" NOT NULL,
    CONSTRAINT "opportunities_currency_iso4217" CHECK (("currency" ~ '^[A-Z]{3}$'::"text")),
    CONSTRAINT "opportunities_deal_probability_check" CHECK ((("deal_probability" >= 0) AND ("deal_probability" <= 100))),
    CONSTRAINT "opportunities_priority_score_check" CHECK ((("priority_score" >= 0) AND ("priority_score" <= 100))),
    CONSTRAINT "opportunities_score_override_check" CHECK ((("score_override" IS NULL) OR (("score_override" >= 0) AND ("score_override" <= 100))))
);

COMMENT ON TABLE "public"."opportunities" IS 'A pursuit against a lead: stage, commercials, scope and proposals. Multiple per lead (the build, then the retainer); at most one active at a time.';

CREATE TABLE IF NOT EXISTS "public"."org_invites" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "organization_id" "uuid" NOT NULL,
    "email" "text" NOT NULL,
    "role" "public"."user_role" DEFAULT 'agent'::"public"."user_role" NOT NULL,
    "created_by" "uuid",
    "expires_at" timestamp with time zone DEFAULT ("now"() + '7 days'::interval) NOT NULL,
    "consumed_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);

COMMENT ON TABLE "public"."org_invites" IS 'Single-use, expiring, email-pinned invite tokens. The only way a signup can join an existing organization -- see handle_new_user().';

CREATE TABLE IF NOT EXISTS "public"."organizations" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "name" "text" NOT NULL,
    "slug" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);

COMMENT ON TABLE "public"."organizations" IS 'One row per tenant. Every table below is scoped to one via its organization_id column, populated automatically by trigger -- see set_*_organization() functions in this file.';

CREATE TABLE IF NOT EXISTS "public"."proposals" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "opportunity_id" "uuid" NOT NULL,
    "version" integer DEFAULT 1 NOT NULL,
    "title" "text" NOT NULL,
    "file_url" "text",
    "figma_url" "text",
    "github_url" "text",
    "loom_url" "text",
    "quoted_price" numeric(12,2),
    "change_notes" "text",
    "status" "public"."proposal_status" DEFAULT 'draft'::"public"."proposal_status" NOT NULL,
    "sent_at" timestamp with time zone,
    "created_by" "uuid",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "organization_id" "uuid" NOT NULL
);

CREATE TABLE IF NOT EXISTS "public"."tasks" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "lead_id" "uuid" NOT NULL,
    "owner_id" "uuid" NOT NULL,
    "title" "text" NOT NULL,
    "notes" "text",
    "status" "public"."task_status" DEFAULT 'pending'::"public"."task_status" NOT NULL,
    "outcome_note" "text",
    "completed_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "version" integer DEFAULT 1 NOT NULL,
    "due_at" timestamp with time zone NOT NULL,
    "snoozed_to" timestamp with time zone,
    "organization_id" "uuid" NOT NULL
);

COMMENT ON COLUMN "public"."tasks"."due_at" IS 'When the follow-up is due, as an absolute instant. Render it in the owner''s timezone.';

CREATE TABLE IF NOT EXISTS "public"."users" (
    "id" "uuid" NOT NULL,
    "email" "text" NOT NULL,
    "full_name" "text" DEFAULT ''::"text" NOT NULL,
    "role" "public"."user_role" DEFAULT 'agent'::"public"."user_role" NOT NULL,
    "avatar_url" "text",
    "google_access_token" "text",
    "google_refresh_token" "text",
    "is_active" boolean DEFAULT true NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "timezone" "text" DEFAULT 'Asia/Kolkata'::"text" NOT NULL,
    "organization_id" "uuid" NOT NULL
);

COMMENT ON COLUMN "public"."users"."timezone" IS 'IANA zone used to derive this user''s day boundaries for follow-up queues.';


-- -----------------------------------------------------------------------------
-- Primary Keys & Unique Constraints
-- -----------------------------------------------------------------------------

ALTER TABLE ONLY "public"."activities"
    ADD CONSTRAINT "activities_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY "public"."audit_log"
    ADD CONSTRAINT "audit_log_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY "public"."companies"
    ADD CONSTRAINT "companies_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY "public"."contacts"
    ADD CONSTRAINT "contacts_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY "public"."idempotency_keys"
    ADD CONSTRAINT "idempotency_keys_caller_hash_idempotency_key_key" UNIQUE ("caller_hash", "idempotency_key");

ALTER TABLE ONLY "public"."idempotency_keys"
    ADD CONSTRAINT "idempotency_keys_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY "public"."lead_intelligence"
    ADD CONSTRAINT "lead_intelligence_lead_id_key" UNIQUE ("lead_id");

ALTER TABLE ONLY "public"."lead_intelligence"
    ADD CONSTRAINT "lead_intelligence_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY "public"."leads"
    ADD CONSTRAINT "leads_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY "public"."marketing_channel_metrics"
    ADD CONSTRAINT "marketing_channel_metrics_org_period_channel_key" UNIQUE ("organization_id", "period_month", "channel");

ALTER TABLE ONLY "public"."marketing_channel_metrics"
    ADD CONSTRAINT "marketing_channel_metrics_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY "public"."meetings"
    ADD CONSTRAINT "meetings_google_event_id_key" UNIQUE ("google_event_id");

ALTER TABLE ONLY "public"."meetings"
    ADD CONSTRAINT "meetings_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY "public"."notifications"
    ADD CONSTRAINT "notifications_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY "public"."opportunities"
    ADD CONSTRAINT "opportunities_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY "public"."org_invites"
    ADD CONSTRAINT "org_invites_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY "public"."organizations"
    ADD CONSTRAINT "organizations_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY "public"."organizations"
    ADD CONSTRAINT "organizations_slug_key" UNIQUE ("slug");

ALTER TABLE ONLY "public"."proposals"
    ADD CONSTRAINT "proposals_opportunity_id_version_key" UNIQUE ("opportunity_id", "version");

ALTER TABLE ONLY "public"."proposals"
    ADD CONSTRAINT "proposals_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY "public"."tasks"
    ADD CONSTRAINT "tasks_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY "public"."users"
    ADD CONSTRAINT "users_email_key" UNIQUE ("email");

ALTER TABLE ONLY "public"."users"
    ADD CONSTRAINT "users_pkey" PRIMARY KEY ("id");


-- -----------------------------------------------------------------------------
-- Indexes
-- -----------------------------------------------------------------------------

CREATE INDEX "activities_lead_idx" ON "public"."activities" USING "btree" ("lead_id", "performed_at" DESC);

CREATE INDEX "activities_organization_idx" ON "public"."activities" USING "btree" ("organization_id");

CREATE INDEX "activities_performed_by_idx" ON "public"."activities" USING "btree" ("performed_by", "type");

CREATE INDEX "audit_log_actor_idx" ON "public"."audit_log" USING "btree" ("actor_id", "occurred_at" DESC);

CREATE INDEX "audit_log_organization_idx" ON "public"."audit_log" USING "btree" ("organization_id");

CREATE INDEX "audit_log_record_idx" ON "public"."audit_log" USING "btree" ("table_name", "record_id", "occurred_at" DESC);

CREATE INDEX "companies_live_idx" ON "public"."companies" USING "btree" ("created_at" DESC) WHERE ("deleted_at" IS NULL);

CREATE INDEX "companies_name_trgm_idx" ON "public"."companies" USING "gin" ("name" "public"."gin_trgm_ops");

CREATE INDEX "companies_organization_idx" ON "public"."companies" USING "btree" ("organization_id");

CREATE INDEX "companies_segment_idx" ON "public"."companies" USING "btree" ("segment");

CREATE INDEX "contacts_company_idx" ON "public"."contacts" USING "btree" ("company_id");

CREATE INDEX "contacts_email_trgm_idx" ON "public"."contacts" USING "gin" ("email" "public"."gin_trgm_ops");

CREATE INDEX "contacts_full_name_trgm_idx" ON "public"."contacts" USING "gin" ("full_name" "public"."gin_trgm_ops");

CREATE INDEX "contacts_is_primary_idx" ON "public"."contacts" USING "btree" ("company_id", "is_primary");

CREATE INDEX "contacts_live_idx" ON "public"."contacts" USING "btree" ("company_id") WHERE ("deleted_at" IS NULL);

CREATE INDEX "contacts_organization_idx" ON "public"."contacts" USING "btree" ("organization_id");

CREATE INDEX "idempotency_keys_created_idx" ON "public"."idempotency_keys" USING "btree" ("created_at");

CREATE INDEX "lead_intelligence_organization_idx" ON "public"."lead_intelligence" USING "btree" ("organization_id");

CREATE INDEX "leads_last_contact_idx" ON "public"."leads" USING "btree" ("last_contact_date");

CREATE INDEX "leads_live_idx" ON "public"."leads" USING "btree" ("updated_at" DESC) WHERE ("deleted_at" IS NULL);

CREATE INDEX "leads_next_followup_idx" ON "public"."leads" USING "btree" ("next_followup_date");

CREATE INDEX "leads_organization_idx" ON "public"."leads" USING "btree" ("organization_id");

CREATE INDEX "leads_owner_idx" ON "public"."leads" USING "btree" ("owner_id");

CREATE INDEX "leads_tags_idx" ON "public"."leads" USING "gin" ("tags");

CREATE INDEX "leads_updated_at_idx" ON "public"."leads" USING "btree" ("updated_at" DESC);

CREATE INDEX "marketing_channel_metrics_period_idx" ON "public"."marketing_channel_metrics" USING "btree" ("period_month" DESC);

CREATE INDEX "meetings_lead_idx" ON "public"."meetings" USING "btree" ("lead_id");

CREATE INDEX "meetings_organization_idx" ON "public"."meetings" USING "btree" ("organization_id");

CREATE INDEX "meetings_owner_scheduled_idx" ON "public"."meetings" USING "btree" ("owner_id", "scheduled_at");

CREATE INDEX "meetings_scheduled_status_idx" ON "public"."meetings" USING "btree" ("scheduled_at", "status");

CREATE UNIQUE INDEX "notifications_dedupe_unique_idx" ON "public"."notifications" USING "btree" ("user_id", "dedupe_key") WHERE ("dedupe_key" IS NOT NULL);

CREATE INDEX "notifications_organization_idx" ON "public"."notifications" USING "btree" ("organization_id");

CREATE INDEX "notifications_unread_idx" ON "public"."notifications" USING "btree" ("user_id", "created_at" DESC) WHERE ("read_at" IS NULL);

CREATE INDEX "notifications_user_created_idx" ON "public"."notifications" USING "btree" ("user_id", "created_at" DESC);

CREATE INDEX "opportunities_lead_idx" ON "public"."opportunities" USING "btree" ("lead_id");

CREATE INDEX "opportunities_live_idx" ON "public"."opportunities" USING "btree" ("updated_at" DESC) WHERE ("deleted_at" IS NULL);

CREATE UNIQUE INDEX "opportunities_one_active_per_lead_idx" ON "public"."opportunities" USING "btree" ("lead_id") WHERE ("status" = 'active'::"public"."opportunity_status");

CREATE INDEX "opportunities_organization_idx" ON "public"."opportunities" USING "btree" ("organization_id");

CREATE INDEX "opportunities_owner_idx" ON "public"."opportunities" USING "btree" ("owner_id");

CREATE INDEX "opportunities_stage_idx" ON "public"."opportunities" USING "btree" ("stage");

CREATE INDEX "proposals_created_by_idx" ON "public"."proposals" USING "btree" ("created_by");

CREATE INDEX "proposals_opportunity_idx" ON "public"."proposals" USING "btree" ("opportunity_id");

CREATE INDEX "proposals_organization_idx" ON "public"."proposals" USING "btree" ("organization_id");

CREATE INDEX "proposals_status_idx" ON "public"."proposals" USING "btree" ("status");

CREATE INDEX "tasks_organization_idx" ON "public"."tasks" USING "btree" ("organization_id");

CREATE INDEX "tasks_owner_due_at_idx" ON "public"."tasks" USING "btree" ("owner_id", "due_at");

CREATE INDEX "tasks_pending_due_at_idx" ON "public"."tasks" USING "btree" ("due_at") WHERE ("status" = 'pending'::"public"."task_status");

CREATE INDEX "tasks_status_due_at_idx" ON "public"."tasks" USING "btree" ("status", "due_at");

CREATE INDEX "users_organization_idx" ON "public"."users" USING "btree" ("organization_id");


-- -----------------------------------------------------------------------------
-- Triggers
-- -----------------------------------------------------------------------------

CREATE OR REPLACE TRIGGER "activities_set_org" BEFORE INSERT ON "public"."activities" FOR EACH ROW EXECUTE FUNCTION "public"."set_parent_organization"('leads', 'lead_id');

CREATE OR REPLACE TRIGGER "companies_audit" AFTER INSERT OR DELETE OR UPDATE ON "public"."companies" FOR EACH ROW EXECUTE FUNCTION "public"."write_audit_log"();

CREATE OR REPLACE TRIGGER "companies_set_org" BEFORE INSERT ON "public"."companies" FOR EACH ROW EXECUTE FUNCTION "public"."set_parent_organization"('users', 'created_by');

CREATE OR REPLACE TRIGGER "companies_touch" BEFORE UPDATE ON "public"."companies" FOR EACH ROW EXECUTE FUNCTION "public"."touch_updated_at"();

CREATE OR REPLACE TRIGGER "companies_version" BEFORE UPDATE ON "public"."companies" FOR EACH ROW EXECUTE FUNCTION "public"."bump_version"();

CREATE OR REPLACE TRIGGER "contacts_audit" AFTER INSERT OR DELETE OR UPDATE ON "public"."contacts" FOR EACH ROW EXECUTE FUNCTION "public"."write_audit_log"();

CREATE OR REPLACE TRIGGER "contacts_set_org" BEFORE INSERT ON "public"."contacts" FOR EACH ROW EXECUTE FUNCTION "public"."set_parent_organization"('companies', 'company_id');

CREATE OR REPLACE TRIGGER "contacts_touch" BEFORE UPDATE ON "public"."contacts" FOR EACH ROW EXECUTE FUNCTION "public"."touch_updated_at"();

CREATE OR REPLACE TRIGGER "contacts_version" BEFORE UPDATE ON "public"."contacts" FOR EACH ROW EXECUTE FUNCTION "public"."bump_version"();

CREATE OR REPLACE TRIGGER "lead_intelligence_audit" AFTER INSERT OR DELETE OR UPDATE ON "public"."lead_intelligence" FOR EACH ROW EXECUTE FUNCTION "public"."write_audit_log"();

CREATE OR REPLACE TRIGGER "lead_intelligence_set_org" BEFORE INSERT ON "public"."lead_intelligence" FOR EACH ROW EXECUTE FUNCTION "public"."set_parent_organization"('leads', 'lead_id');

CREATE OR REPLACE TRIGGER "lead_intelligence_version" BEFORE UPDATE ON "public"."lead_intelligence" FOR EACH ROW EXECUTE FUNCTION "public"."bump_version"();

CREATE OR REPLACE TRIGGER "leads_after_insert_intelligence" AFTER INSERT ON "public"."leads" FOR EACH ROW EXECUTE FUNCTION "public"."ensure_lead_intelligence"();

CREATE OR REPLACE TRIGGER "leads_after_insert_opportunity" AFTER INSERT ON "public"."leads" FOR EACH ROW EXECUTE FUNCTION "public"."ensure_opportunity_for_lead"();

CREATE OR REPLACE TRIGGER "leads_audit" AFTER INSERT OR DELETE OR UPDATE ON "public"."leads" FOR EACH ROW EXECUTE FUNCTION "public"."write_audit_log"();

CREATE OR REPLACE TRIGGER "leads_set_org" BEFORE INSERT ON "public"."leads" FOR EACH ROW EXECUTE FUNCTION "public"."set_lead_organization"();

CREATE OR REPLACE TRIGGER "leads_touch" BEFORE UPDATE ON "public"."leads" FOR EACH ROW EXECUTE FUNCTION "public"."touch_updated_at"();

CREATE OR REPLACE TRIGGER "leads_version" BEFORE UPDATE ON "public"."leads" FOR EACH ROW EXECUTE FUNCTION "public"."bump_version"();

CREATE OR REPLACE TRIGGER "marketing_channel_metrics_set_org" BEFORE INSERT ON "public"."marketing_channel_metrics" FOR EACH ROW EXECUTE FUNCTION "public"."set_marketing_metric_organization"();

CREATE OR REPLACE TRIGGER "meetings_set_org" BEFORE INSERT ON "public"."meetings" FOR EACH ROW EXECUTE FUNCTION "public"."set_meeting_organization"();

CREATE OR REPLACE TRIGGER "meetings_touch" BEFORE UPDATE ON "public"."meetings" FOR EACH ROW EXECUTE FUNCTION "public"."touch_updated_at"();

CREATE OR REPLACE TRIGGER "meetings_version" BEFORE UPDATE ON "public"."meetings" FOR EACH ROW EXECUTE FUNCTION "public"."bump_version"();

CREATE OR REPLACE TRIGGER "notifications_set_org" BEFORE INSERT ON "public"."notifications" FOR EACH ROW EXECUTE FUNCTION "public"."set_parent_organization"('users', 'user_id');

CREATE OR REPLACE TRIGGER "opportunities_audit" AFTER INSERT OR DELETE OR UPDATE ON "public"."opportunities" FOR EACH ROW EXECUTE FUNCTION "public"."write_audit_log"();

CREATE OR REPLACE TRIGGER "opportunities_set_org" BEFORE INSERT ON "public"."opportunities" FOR EACH ROW EXECUTE FUNCTION "public"."set_parent_organization"('leads', 'lead_id');

CREATE OR REPLACE TRIGGER "opportunities_stage_change_log" AFTER UPDATE ON "public"."opportunities" FOR EACH ROW EXECUTE FUNCTION "public"."log_opportunity_stage_change"();

CREATE OR REPLACE TRIGGER "opportunities_touch" BEFORE UPDATE ON "public"."opportunities" FOR EACH ROW EXECUTE FUNCTION "public"."touch_updated_at"();

CREATE OR REPLACE TRIGGER "opportunities_version" BEFORE UPDATE ON "public"."opportunities" FOR EACH ROW EXECUTE FUNCTION "public"."bump_version"();

CREATE OR REPLACE TRIGGER "proposals_audit" AFTER INSERT OR DELETE OR UPDATE ON "public"."proposals" FOR EACH ROW EXECUTE FUNCTION "public"."write_audit_log"();

CREATE OR REPLACE TRIGGER "proposals_set_org" BEFORE INSERT ON "public"."proposals" FOR EACH ROW EXECUTE FUNCTION "public"."set_parent_organization"('opportunities', 'opportunity_id');

CREATE OR REPLACE TRIGGER "proposals_touch" BEFORE UPDATE ON "public"."proposals" FOR EACH ROW EXECUTE FUNCTION "public"."touch_updated_at"();

CREATE OR REPLACE TRIGGER "proposals_version" BEFORE UPDATE ON "public"."proposals" FOR EACH ROW EXECUTE FUNCTION "public"."bump_version"();

CREATE OR REPLACE TRIGGER "tasks_set_org" BEFORE INSERT ON "public"."tasks" FOR EACH ROW EXECUTE FUNCTION "public"."set_parent_organization"('leads', 'lead_id');

CREATE OR REPLACE TRIGGER "tasks_touch" BEFORE UPDATE ON "public"."tasks" FOR EACH ROW EXECUTE FUNCTION "public"."touch_updated_at"();

CREATE OR REPLACE TRIGGER "tasks_version" BEFORE UPDATE ON "public"."tasks" FOR EACH ROW EXECUTE FUNCTION "public"."bump_version"();

CREATE OR REPLACE TRIGGER "users_guard_role" BEFORE UPDATE ON "public"."users" FOR EACH ROW EXECUTE FUNCTION "public"."guard_role_escalation"();

CREATE OR REPLACE TRIGGER "users_timezone_check" BEFORE INSERT OR UPDATE OF "timezone" ON "public"."users" FOR EACH ROW EXECUTE FUNCTION "public"."validate_user_timezone"();

CREATE OR REPLACE TRIGGER "users_touch" BEFORE UPDATE ON "public"."users" FOR EACH ROW EXECUTE FUNCTION "public"."touch_updated_at"();

-- Not captured by `supabase db dump -s public`: this trigger is attached to auth.users,
-- a table outside the public schema, even though its function lives in public. Without it,
-- no signup ever gets a row in public.users (confirmed by testing an actual signup against
-- this migration applied fresh -- the schema-diff comparison alone did not catch this).
DROP TRIGGER IF EXISTS "on_auth_user_created" ON "auth"."users";
CREATE TRIGGER "on_auth_user_created" AFTER INSERT ON "auth"."users" FOR EACH ROW EXECUTE FUNCTION "public"."handle_new_user"();


-- -----------------------------------------------------------------------------
-- Foreign Keys (Relationships)
-- -----------------------------------------------------------------------------

ALTER TABLE ONLY "public"."activities"
    ADD CONSTRAINT "activities_lead_id_fkey" FOREIGN KEY ("lead_id") REFERENCES "public"."leads"("id") ON DELETE CASCADE;

ALTER TABLE ONLY "public"."activities"
    ADD CONSTRAINT "activities_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");

ALTER TABLE ONLY "public"."activities"
    ADD CONSTRAINT "activities_performed_by_fkey" FOREIGN KEY ("performed_by") REFERENCES "public"."users"("id");

ALTER TABLE ONLY "public"."audit_log"
    ADD CONSTRAINT "audit_log_actor_id_fkey" FOREIGN KEY ("actor_id") REFERENCES "public"."users"("id") ON DELETE SET NULL;

ALTER TABLE ONLY "public"."audit_log"
    ADD CONSTRAINT "audit_log_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");

ALTER TABLE ONLY "public"."companies"
    ADD CONSTRAINT "companies_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "public"."users"("id");

ALTER TABLE ONLY "public"."companies"
    ADD CONSTRAINT "companies_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");

ALTER TABLE ONLY "public"."contacts"
    ADD CONSTRAINT "contacts_company_id_fkey" FOREIGN KEY ("company_id") REFERENCES "public"."companies"("id") ON DELETE CASCADE;

ALTER TABLE ONLY "public"."contacts"
    ADD CONSTRAINT "contacts_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");

ALTER TABLE ONLY "public"."lead_intelligence"
    ADD CONSTRAINT "lead_intelligence_lead_id_fkey" FOREIGN KEY ("lead_id") REFERENCES "public"."leads"("id") ON DELETE CASCADE;

ALTER TABLE ONLY "public"."lead_intelligence"
    ADD CONSTRAINT "lead_intelligence_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");

ALTER TABLE ONLY "public"."lead_intelligence"
    ADD CONSTRAINT "lead_intelligence_updated_by_fkey" FOREIGN KEY ("updated_by") REFERENCES "public"."users"("id");

ALTER TABLE ONLY "public"."leads"
    ADD CONSTRAINT "leads_company_id_fkey" FOREIGN KEY ("company_id") REFERENCES "public"."companies"("id");

ALTER TABLE ONLY "public"."leads"
    ADD CONSTRAINT "leads_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");

ALTER TABLE ONLY "public"."leads"
    ADD CONSTRAINT "leads_owner_id_fkey" FOREIGN KEY ("owner_id") REFERENCES "public"."users"("id");

ALTER TABLE ONLY "public"."leads"
    ADD CONSTRAINT "leads_primary_contact_id_fkey" FOREIGN KEY ("primary_contact_id") REFERENCES "public"."contacts"("id");

ALTER TABLE ONLY "public"."marketing_channel_metrics"
    ADD CONSTRAINT "marketing_channel_metrics_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");

ALTER TABLE ONLY "public"."meetings"
    ADD CONSTRAINT "meetings_lead_id_fkey" FOREIGN KEY ("lead_id") REFERENCES "public"."leads"("id") ON DELETE CASCADE;

ALTER TABLE ONLY "public"."meetings"
    ADD CONSTRAINT "meetings_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");

ALTER TABLE ONLY "public"."meetings"
    ADD CONSTRAINT "meetings_owner_id_fkey" FOREIGN KEY ("owner_id") REFERENCES "public"."users"("id");

ALTER TABLE ONLY "public"."notifications"
    ADD CONSTRAINT "notifications_meeting_id_fkey" FOREIGN KEY ("meeting_id") REFERENCES "public"."meetings"("id") ON DELETE SET NULL;

ALTER TABLE ONLY "public"."notifications"
    ADD CONSTRAINT "notifications_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");

ALTER TABLE ONLY "public"."notifications"
    ADD CONSTRAINT "notifications_source_task_id_fkey" FOREIGN KEY ("source_task_id") REFERENCES "public"."tasks"("id") ON DELETE SET NULL;

ALTER TABLE ONLY "public"."notifications"
    ADD CONSTRAINT "notifications_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id") ON DELETE CASCADE;

ALTER TABLE ONLY "public"."opportunities"
    ADD CONSTRAINT "opportunities_lead_id_fkey" FOREIGN KEY ("lead_id") REFERENCES "public"."leads"("id") ON DELETE CASCADE;

ALTER TABLE ONLY "public"."opportunities"
    ADD CONSTRAINT "opportunities_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");

ALTER TABLE ONLY "public"."opportunities"
    ADD CONSTRAINT "opportunities_owner_id_fkey" FOREIGN KEY ("owner_id") REFERENCES "public"."users"("id");

ALTER TABLE ONLY "public"."org_invites"
    ADD CONSTRAINT "org_invites_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "public"."users"("id");

ALTER TABLE ONLY "public"."org_invites"
    ADD CONSTRAINT "org_invites_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");

ALTER TABLE ONLY "public"."proposals"
    ADD CONSTRAINT "proposals_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "public"."users"("id");

ALTER TABLE ONLY "public"."proposals"
    ADD CONSTRAINT "proposals_opportunity_id_fkey" FOREIGN KEY ("opportunity_id") REFERENCES "public"."opportunities"("id") ON DELETE CASCADE;

ALTER TABLE ONLY "public"."proposals"
    ADD CONSTRAINT "proposals_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");

ALTER TABLE ONLY "public"."tasks"
    ADD CONSTRAINT "tasks_lead_id_fkey" FOREIGN KEY ("lead_id") REFERENCES "public"."leads"("id") ON DELETE CASCADE;

ALTER TABLE ONLY "public"."tasks"
    ADD CONSTRAINT "tasks_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");

ALTER TABLE ONLY "public"."tasks"
    ADD CONSTRAINT "tasks_owner_id_fkey" FOREIGN KEY ("owner_id") REFERENCES "public"."users"("id");

ALTER TABLE ONLY "public"."users"
    ADD CONSTRAINT "users_id_fkey" FOREIGN KEY ("id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;

ALTER TABLE ONLY "public"."users"
    ADD CONSTRAINT "users_organization_id_fkey" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");


-- -----------------------------------------------------------------------------
-- Row Level Security
-- -----------------------------------------------------------------------------

ALTER TABLE "public"."activities" ENABLE ROW LEVEL SECURITY;

CREATE POLICY "activities_insert" ON "public"."activities" FOR INSERT WITH CHECK ((("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND ( SELECT "public"."can_access_lead"("auth"."uid"(), "activities"."lead_id") AS "can_access_lead") AND ("performed_by" = ( SELECT "auth"."uid"() AS "uid"))));

CREATE POLICY "activities_select" ON "public"."activities" FOR SELECT USING ((("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND ( SELECT "public"."can_access_lead"("auth"."uid"(), "activities"."lead_id") AS "can_access_lead")));

ALTER TABLE "public"."audit_log" ENABLE ROW LEVEL SECURITY;

CREATE POLICY "audit_log_select" ON "public"."audit_log" FOR SELECT USING ((("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND (("actor_id" = ( SELECT "auth"."uid"() AS "uid")) OR ( SELECT "public"."is_admin"("auth"."uid"()) AS "is_admin"))));

ALTER TABLE "public"."companies" ENABLE ROW LEVEL SECURITY;

CREATE POLICY "companies_insert" ON "public"."companies" FOR INSERT WITH CHECK (((( SELECT "auth"."uid"() AS "uid") IS NOT NULL) AND ("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND ("created_by" = ( SELECT "auth"."uid"() AS "uid"))));

CREATE POLICY "companies_select" ON "public"."companies" FOR SELECT USING ((("deleted_at" IS NULL) AND ("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND (("created_by" = ( SELECT "auth"."uid"() AS "uid")) OR ( SELECT "public"."is_admin"("auth"."uid"()) AS "is_admin") OR (EXISTS ( SELECT 1
   FROM "public"."leads" "l"
  WHERE (("l"."company_id" = "companies"."id") AND ( SELECT "public"."can_access_lead"("auth"."uid"(), "l"."id") AS "can_access_lead")))))));

CREATE POLICY "companies_update" ON "public"."companies" FOR UPDATE USING ((("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND (("created_by" = ( SELECT "auth"."uid"() AS "uid")) OR ( SELECT "public"."is_admin"("auth"."uid"()) AS "is_admin"))));

ALTER TABLE "public"."contacts" ENABLE ROW LEVEL SECURITY;

CREATE POLICY "contacts_delete" ON "public"."contacts" FOR DELETE USING ((("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND (( SELECT "public"."is_admin"("auth"."uid"()) AS "is_admin") OR (EXISTS ( SELECT 1
   FROM "public"."companies" "c"
  WHERE (("c"."id" = "contacts"."company_id") AND ("c"."created_by" = ( SELECT "auth"."uid"() AS "uid"))))))));

CREATE POLICY "contacts_insert" ON "public"."contacts" FOR INSERT WITH CHECK (((( SELECT "auth"."uid"() AS "uid") IS NOT NULL) AND ("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND ((EXISTS ( SELECT 1
   FROM "public"."companies" "c"
  WHERE (("c"."id" = "contacts"."company_id") AND (("c"."created_by" = ( SELECT "auth"."uid"() AS "uid")) OR ( SELECT "public"."is_admin"("auth"."uid"()) AS "is_admin"))))) OR (EXISTS ( SELECT 1
   FROM "public"."leads" "l"
  WHERE (("l"."company_id" = "contacts"."company_id") AND ( SELECT "public"."can_access_lead"("auth"."uid"(), "l"."id") AS "can_access_lead")))))));

CREATE POLICY "contacts_select" ON "public"."contacts" FOR SELECT USING ((("deleted_at" IS NULL) AND ("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND (( SELECT "public"."is_admin"("auth"."uid"()) AS "is_admin") OR (EXISTS ( SELECT 1
   FROM "public"."companies" "c"
  WHERE (("c"."id" = "contacts"."company_id") AND ("c"."created_by" = ( SELECT "auth"."uid"() AS "uid"))))) OR (EXISTS ( SELECT 1
   FROM "public"."leads" "l"
  WHERE (("l"."company_id" = "contacts"."company_id") AND ( SELECT "public"."can_access_lead"("auth"."uid"(), "l"."id") AS "can_access_lead")))))));

CREATE POLICY "contacts_update" ON "public"."contacts" FOR UPDATE USING ((("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND (( SELECT "public"."is_admin"("auth"."uid"()) AS "is_admin") OR (EXISTS ( SELECT 1
   FROM "public"."companies" "c"
  WHERE (("c"."id" = "contacts"."company_id") AND ("c"."created_by" = ( SELECT "auth"."uid"() AS "uid"))))) OR (EXISTS ( SELECT 1
   FROM "public"."leads" "l"
  WHERE (("l"."company_id" = "contacts"."company_id") AND ( SELECT "public"."can_access_lead"("auth"."uid"(), "l"."id") AS "can_access_lead")))))));

ALTER TABLE "public"."idempotency_keys" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "public"."lead_intelligence" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "public"."leads" ENABLE ROW LEVEL SECURITY;

CREATE POLICY "leads_insert" ON "public"."leads" FOR INSERT WITH CHECK (((( SELECT "auth"."uid"() AS "uid") IS NOT NULL) AND ("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND (("owner_id" = ( SELECT "auth"."uid"() AS "uid")) OR ( SELECT "public"."is_admin"("auth"."uid"()) AS "is_admin"))));

CREATE POLICY "leads_select" ON "public"."leads" FOR SELECT USING ((("deleted_at" IS NULL) AND ("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND (("owner_id" = ( SELECT "auth"."uid"() AS "uid")) OR ( SELECT "public"."is_admin"("auth"."uid"()) AS "is_admin"))));

CREATE POLICY "leads_update" ON "public"."leads" FOR UPDATE USING ((("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND (("owner_id" = ( SELECT "auth"."uid"() AS "uid")) OR ( SELECT "public"."is_admin"("auth"."uid"()) AS "is_admin")))) WITH CHECK ((("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND (("owner_id" = ( SELECT "auth"."uid"() AS "uid")) OR ( SELECT "public"."is_admin"("auth"."uid"()) AS "is_admin"))));

CREATE POLICY "li_insert" ON "public"."lead_intelligence" FOR INSERT WITH CHECK ((("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND ( SELECT "public"."can_access_lead"("auth"."uid"(), "lead_intelligence"."lead_id") AS "can_access_lead")));

CREATE POLICY "li_select" ON "public"."lead_intelligence" FOR SELECT USING ((("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND ( SELECT "public"."can_access_lead"("auth"."uid"(), "lead_intelligence"."lead_id") AS "can_access_lead")));

CREATE POLICY "li_update" ON "public"."lead_intelligence" FOR UPDATE USING ((("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND ( SELECT "public"."can_access_lead"("auth"."uid"(), "lead_intelligence"."lead_id") AS "can_access_lead")));

ALTER TABLE "public"."marketing_channel_metrics" ENABLE ROW LEVEL SECURITY;

CREATE POLICY "marketing_metrics_delete" ON "public"."marketing_channel_metrics" FOR DELETE USING ((("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND ( SELECT "public"."is_admin"("auth"."uid"()) AS "is_admin")));

CREATE POLICY "marketing_metrics_insert" ON "public"."marketing_channel_metrics" FOR INSERT WITH CHECK ((("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND ( SELECT "public"."is_admin"("auth"."uid"()) AS "is_admin")));

CREATE POLICY "marketing_metrics_select" ON "public"."marketing_channel_metrics" FOR SELECT USING (("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")));

CREATE POLICY "marketing_metrics_update" ON "public"."marketing_channel_metrics" FOR UPDATE USING ((("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND ( SELECT "public"."is_admin"("auth"."uid"()) AS "is_admin")));

ALTER TABLE "public"."meetings" ENABLE ROW LEVEL SECURITY;

CREATE POLICY "meetings_delete" ON "public"."meetings" FOR DELETE USING ((("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND (("owner_id" = ( SELECT "auth"."uid"() AS "uid")) OR ( SELECT "public"."is_admin"("auth"."uid"()) AS "is_admin"))));

CREATE POLICY "meetings_insert" ON "public"."meetings" FOR INSERT WITH CHECK ((("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND (("owner_id" = ( SELECT "auth"."uid"() AS "uid")) OR ( SELECT "public"."is_admin"("auth"."uid"()) AS "is_admin"))));

CREATE POLICY "meetings_select" ON "public"."meetings" FOR SELECT USING ((("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND (("owner_id" = ( SELECT "auth"."uid"() AS "uid")) OR ( SELECT "public"."is_admin"("auth"."uid"()) AS "is_admin"))));

CREATE POLICY "meetings_update" ON "public"."meetings" FOR UPDATE USING ((("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND (("owner_id" = ( SELECT "auth"."uid"() AS "uid")) OR ( SELECT "public"."is_admin"("auth"."uid"()) AS "is_admin"))));

ALTER TABLE "public"."notifications" ENABLE ROW LEVEL SECURITY;

CREATE POLICY "notifications_delete_own" ON "public"."notifications" FOR DELETE USING (("user_id" = ( SELECT "auth"."uid"() AS "uid")));

CREATE POLICY "notifications_insert_own" ON "public"."notifications" FOR INSERT WITH CHECK (("user_id" = "auth"."uid"()));

CREATE POLICY "notifications_select_own" ON "public"."notifications" FOR SELECT USING (("user_id" = "auth"."uid"()));

CREATE POLICY "notifications_update_own" ON "public"."notifications" FOR UPDATE USING (("user_id" = "auth"."uid"()));

CREATE POLICY "opp_insert" ON "public"."opportunities" FOR INSERT WITH CHECK ((("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND ( SELECT "public"."can_access_lead"("auth"."uid"(), "opportunities"."lead_id") AS "can_access_lead")));

CREATE POLICY "opp_select" ON "public"."opportunities" FOR SELECT USING ((("deleted_at" IS NULL) AND ("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND ( SELECT "public"."can_access_lead"("auth"."uid"(), "opportunities"."lead_id") AS "can_access_lead")));

CREATE POLICY "opp_update" ON "public"."opportunities" FOR UPDATE USING ((("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND ( SELECT "public"."can_access_lead"("auth"."uid"(), "opportunities"."lead_id") AS "can_access_lead")));

ALTER TABLE "public"."opportunities" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "public"."org_invites" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "public"."organizations" ENABLE ROW LEVEL SECURITY;

CREATE POLICY "organizations_select" ON "public"."organizations" FOR SELECT USING (("id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")));

CREATE POLICY "prop_delete" ON "public"."proposals" FOR DELETE USING ((("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND ("status" = 'draft'::"public"."proposal_status") AND (EXISTS ( SELECT 1
   FROM "public"."opportunities" "o"
  WHERE (("o"."id" = "proposals"."opportunity_id") AND ( SELECT "public"."can_access_lead"("auth"."uid"(), "o"."lead_id") AS "can_access_lead"))))));

CREATE POLICY "prop_insert" ON "public"."proposals" FOR INSERT WITH CHECK ((("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND (EXISTS ( SELECT 1
   FROM "public"."opportunities" "o"
  WHERE (("o"."id" = "proposals"."opportunity_id") AND ( SELECT "public"."can_access_lead"("auth"."uid"(), "o"."lead_id") AS "can_access_lead"))))));

CREATE POLICY "prop_select" ON "public"."proposals" FOR SELECT USING ((("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND (EXISTS ( SELECT 1
   FROM "public"."opportunities" "o"
  WHERE (("o"."id" = "proposals"."opportunity_id") AND ( SELECT "public"."can_access_lead"("auth"."uid"(), "o"."lead_id") AS "can_access_lead"))))));

CREATE POLICY "prop_update" ON "public"."proposals" FOR UPDATE USING ((("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND (EXISTS ( SELECT 1
   FROM "public"."opportunities" "o"
  WHERE (("o"."id" = "proposals"."opportunity_id") AND ( SELECT "public"."can_access_lead"("auth"."uid"(), "o"."lead_id") AS "can_access_lead"))))));

ALTER TABLE "public"."proposals" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "public"."tasks" ENABLE ROW LEVEL SECURITY;

CREATE POLICY "tasks_delete" ON "public"."tasks" FOR DELETE USING ((("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND (("owner_id" = ( SELECT "auth"."uid"() AS "uid")) OR ( SELECT "public"."is_admin"("auth"."uid"()) AS "is_admin"))));

CREATE POLICY "tasks_insert" ON "public"."tasks" FOR INSERT WITH CHECK ((("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND (("owner_id" = ( SELECT "auth"."uid"() AS "uid")) OR ( SELECT "public"."is_admin"("auth"."uid"()) AS "is_admin"))));

CREATE POLICY "tasks_select" ON "public"."tasks" FOR SELECT USING ((("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND (("owner_id" = ( SELECT "auth"."uid"() AS "uid")) OR ( SELECT "public"."is_admin"("auth"."uid"()) AS "is_admin"))));

CREATE POLICY "tasks_update" ON "public"."tasks" FOR UPDATE USING ((("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND (("owner_id" = ( SELECT "auth"."uid"() AS "uid")) OR ( SELECT "public"."is_admin"("auth"."uid"()) AS "is_admin"))));

ALTER TABLE "public"."users" ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users_select" ON "public"."users" FOR SELECT USING ((("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND (("id" = ( SELECT "auth"."uid"() AS "uid")) OR ( SELECT "public"."is_admin"("auth"."uid"()) AS "is_admin"))));

CREATE POLICY "users_update_admin" ON "public"."users" FOR UPDATE USING ((("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND ( SELECT "public"."is_admin"("auth"."uid"()) AS "is_admin"))) WITH CHECK ((("organization_id" = ( SELECT "public"."current_org_id"("auth"."uid"()) AS "current_org_id")) AND ( SELECT "public"."is_admin"("auth"."uid"()) AS "is_admin")));

CREATE POLICY "users_update_self" ON "public"."users" FOR UPDATE USING (("id" = ( SELECT "auth"."uid"() AS "uid"))) WITH CHECK (("id" = ( SELECT "auth"."uid"() AS "uid")));


-- -----------------------------------------------------------------------------
-- Grants
-- -----------------------------------------------------------------------------

GRANT USAGE ON SCHEMA "public" TO "postgres";
GRANT USAGE ON SCHEMA "public" TO "anon";
GRANT USAGE ON SCHEMA "public" TO "authenticated";
GRANT USAGE ON SCHEMA "public" TO "service_role";

GRANT ALL ON FUNCTION "public"."bump_version"() TO "anon";
GRANT ALL ON FUNCTION "public"."bump_version"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."bump_version"() TO "service_role";

GRANT ALL ON FUNCTION "public"."can_access_lead"("uid" "uuid", "lid" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."can_access_lead"("uid" "uuid", "lid" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."can_access_lead"("uid" "uuid", "lid" "uuid") TO "service_role";

GRANT ALL ON FUNCTION "public"."current_org_id"("uid" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."current_org_id"("uid" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."current_org_id"("uid" "uuid") TO "service_role";

GRANT ALL ON FUNCTION "public"."dashboard_metrics"() TO "anon";
GRANT ALL ON FUNCTION "public"."dashboard_metrics"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."dashboard_metrics"() TO "service_role";

GRANT ALL ON FUNCTION "public"."ensure_lead_intelligence"() TO "anon";
GRANT ALL ON FUNCTION "public"."ensure_lead_intelligence"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."ensure_lead_intelligence"() TO "service_role";

GRANT ALL ON FUNCTION "public"."ensure_opportunity_for_lead"() TO "anon";
GRANT ALL ON FUNCTION "public"."ensure_opportunity_for_lead"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."ensure_opportunity_for_lead"() TO "service_role";

GRANT ALL ON FUNCTION "public"."guard_role_escalation"() TO "anon";
GRANT ALL ON FUNCTION "public"."guard_role_escalation"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."guard_role_escalation"() TO "service_role";

GRANT ALL ON FUNCTION "public"."handle_new_user"() TO "anon";
GRANT ALL ON FUNCTION "public"."handle_new_user"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."handle_new_user"() TO "service_role";

GRANT ALL ON FUNCTION "public"."is_admin"("uid" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."is_admin"("uid" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."is_admin"("uid" "uuid") TO "service_role";

GRANT ALL ON FUNCTION "public"."log_lead_stage_change"() TO "anon";
GRANT ALL ON FUNCTION "public"."log_lead_stage_change"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."log_lead_stage_change"() TO "service_role";

GRANT ALL ON FUNCTION "public"."log_opportunity_stage_change"() TO "anon";
GRANT ALL ON FUNCTION "public"."log_opportunity_stage_change"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."log_opportunity_stage_change"() TO "service_role";

GRANT ALL ON FUNCTION "public"."pipeline_trend"("months" integer) TO "anon";
GRANT ALL ON FUNCTION "public"."pipeline_trend"("months" integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."pipeline_trend"("months" integer) TO "service_role";

GRANT ALL ON FUNCTION "public"."prune_idempotency_keys"("older_than" interval) TO "anon";
GRANT ALL ON FUNCTION "public"."prune_idempotency_keys"("older_than" interval) TO "authenticated";
GRANT ALL ON FUNCTION "public"."prune_idempotency_keys"("older_than" interval) TO "service_role";

GRANT ALL ON FUNCTION "public"."set_lead_organization"() TO "anon";
GRANT ALL ON FUNCTION "public"."set_lead_organization"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."set_lead_organization"() TO "service_role";

GRANT ALL ON FUNCTION "public"."set_marketing_metric_organization"() TO "anon";
GRANT ALL ON FUNCTION "public"."set_marketing_metric_organization"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."set_marketing_metric_organization"() TO "service_role";

GRANT ALL ON FUNCTION "public"."set_meeting_organization"() TO "anon";
GRANT ALL ON FUNCTION "public"."set_meeting_organization"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."set_meeting_organization"() TO "service_role";

GRANT ALL ON FUNCTION "public"."set_parent_organization"() TO "anon";
GRANT ALL ON FUNCTION "public"."set_parent_organization"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."set_parent_organization"() TO "service_role";

GRANT ALL ON FUNCTION "public"."soft_delete_company"("p_id" "uuid", "p_expected_version" integer) TO "anon";
GRANT ALL ON FUNCTION "public"."soft_delete_company"("p_id" "uuid", "p_expected_version" integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."soft_delete_company"("p_id" "uuid", "p_expected_version" integer) TO "service_role";

GRANT ALL ON FUNCTION "public"."soft_delete_contact"("p_id" "uuid", "p_expected_version" integer) TO "anon";
GRANT ALL ON FUNCTION "public"."soft_delete_contact"("p_id" "uuid", "p_expected_version" integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."soft_delete_contact"("p_id" "uuid", "p_expected_version" integer) TO "service_role";

GRANT ALL ON FUNCTION "public"."soft_delete_lead"("p_id" "uuid", "p_expected_version" integer) TO "anon";
GRANT ALL ON FUNCTION "public"."soft_delete_lead"("p_id" "uuid", "p_expected_version" integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."soft_delete_lead"("p_id" "uuid", "p_expected_version" integer) TO "service_role";

GRANT ALL ON FUNCTION "public"."soft_delete_opportunity"("p_id" "uuid", "p_expected_version" integer) TO "anon";
GRANT ALL ON FUNCTION "public"."soft_delete_opportunity"("p_id" "uuid", "p_expected_version" integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."soft_delete_opportunity"("p_id" "uuid", "p_expected_version" integer) TO "service_role";

GRANT ALL ON FUNCTION "public"."touch_updated_at"() TO "anon";
GRANT ALL ON FUNCTION "public"."touch_updated_at"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."touch_updated_at"() TO "service_role";

GRANT ALL ON FUNCTION "public"."validate_user_timezone"() TO "anon";
GRANT ALL ON FUNCTION "public"."validate_user_timezone"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."validate_user_timezone"() TO "service_role";

GRANT ALL ON FUNCTION "public"."write_audit_log"() TO "anon";
GRANT ALL ON FUNCTION "public"."write_audit_log"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."write_audit_log"() TO "service_role";

GRANT ALL ON TABLE "public"."activities" TO "anon";
GRANT ALL ON TABLE "public"."activities" TO "authenticated";
GRANT ALL ON TABLE "public"."activities" TO "service_role";

GRANT ALL ON TABLE "public"."audit_log" TO "anon";
GRANT ALL ON TABLE "public"."audit_log" TO "authenticated";
GRANT ALL ON TABLE "public"."audit_log" TO "service_role";

GRANT ALL ON SEQUENCE "public"."audit_log_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."audit_log_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."audit_log_id_seq" TO "service_role";

GRANT ALL ON TABLE "public"."companies" TO "anon";
GRANT ALL ON TABLE "public"."companies" TO "authenticated";
GRANT ALL ON TABLE "public"."companies" TO "service_role";

GRANT ALL ON TABLE "public"."contacts" TO "anon";
GRANT ALL ON TABLE "public"."contacts" TO "authenticated";
GRANT ALL ON TABLE "public"."contacts" TO "service_role";

GRANT ALL ON TABLE "public"."idempotency_keys" TO "anon";
GRANT ALL ON TABLE "public"."idempotency_keys" TO "authenticated";
GRANT ALL ON TABLE "public"."idempotency_keys" TO "service_role";

GRANT ALL ON SEQUENCE "public"."idempotency_keys_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."idempotency_keys_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."idempotency_keys_id_seq" TO "service_role";

GRANT ALL ON TABLE "public"."lead_intelligence" TO "anon";
GRANT ALL ON TABLE "public"."lead_intelligence" TO "authenticated";
GRANT ALL ON TABLE "public"."lead_intelligence" TO "service_role";

GRANT ALL ON TABLE "public"."leads" TO "anon";
GRANT ALL ON TABLE "public"."leads" TO "authenticated";
GRANT ALL ON TABLE "public"."leads" TO "service_role";

GRANT ALL ON TABLE "public"."marketing_channel_metrics" TO "anon";
GRANT ALL ON TABLE "public"."marketing_channel_metrics" TO "authenticated";
GRANT ALL ON TABLE "public"."marketing_channel_metrics" TO "service_role";

GRANT ALL ON TABLE "public"."meetings" TO "anon";
GRANT ALL ON TABLE "public"."meetings" TO "authenticated";
GRANT ALL ON TABLE "public"."meetings" TO "service_role";

GRANT ALL ON TABLE "public"."notifications" TO "anon";
GRANT ALL ON TABLE "public"."notifications" TO "authenticated";
GRANT ALL ON TABLE "public"."notifications" TO "service_role";

GRANT ALL ON TABLE "public"."opportunities" TO "anon";
GRANT ALL ON TABLE "public"."opportunities" TO "authenticated";
GRANT ALL ON TABLE "public"."opportunities" TO "service_role";

GRANT ALL ON TABLE "public"."org_invites" TO "anon";
GRANT ALL ON TABLE "public"."org_invites" TO "authenticated";
GRANT ALL ON TABLE "public"."org_invites" TO "service_role";

GRANT ALL ON TABLE "public"."organizations" TO "anon";
GRANT ALL ON TABLE "public"."organizations" TO "authenticated";
GRANT ALL ON TABLE "public"."organizations" TO "service_role";

GRANT ALL ON TABLE "public"."proposals" TO "anon";
GRANT ALL ON TABLE "public"."proposals" TO "authenticated";
GRANT ALL ON TABLE "public"."proposals" TO "service_role";

GRANT ALL ON TABLE "public"."tasks" TO "anon";
GRANT ALL ON TABLE "public"."tasks" TO "authenticated";
GRANT ALL ON TABLE "public"."tasks" TO "service_role";

GRANT ALL ON TABLE "public"."users" TO "anon";
GRANT ALL ON TABLE "public"."users" TO "authenticated";
GRANT ALL ON TABLE "public"."users" TO "service_role";

ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "service_role";

ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "service_role";

ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "service_role";

