-- Three defects found reviewing the schema against how the API actually uses it.

-- ---------------------------------------------------------------------------
-- 1. Invited roles were discarded.
--
-- POST /agents/invite passes {"role": "admin"} to Supabase Auth, which stores it on
-- auth.users.raw_user_meta_data. handle_new_user then ignored it and hardcoded 'agent',
-- so inviting an admin silently produced an agent and the only way to grant admin was a
-- manual UPDATE. The role is now read from the invitation, validated against the enum,
-- and falls back to 'agent' when absent or unrecognised.
--
-- Note the deliberate asymmetry: the role is only honoured on *insert*, from an invitation
-- issued by an existing admin through the service role. A user editing their own metadata
-- cannot escalate, because this trigger never fires again for them.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  requested TEXT := NULLIF(NEW.raw_user_meta_data->>'role', '');
  resolved public.user_role := 'agent';
BEGIN
  IF requested IS NOT NULL AND EXISTS (
    SELECT 1
    FROM unnest(enum_range(NULL::public.user_role)) AS r
    WHERE r::text = requested
  ) THEN
    resolved := requested::public.user_role;
  END IF;

  INSERT INTO public.users (id, email, full_name, role)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(
      NULLIF(NEW.raw_user_meta_data->>'full_name', ''),
      NULLIF(split_part(NEW.email, '@', 1), ''),
      'User'
    ),
    resolved
  )
  ON CONFLICT (id) DO NOTHING;

  RETURN NEW;
END;
$$;

-- ---------------------------------------------------------------------------
-- 2. Currency was an unconstrained TEXT column, and the dashboard summed across it.
--
-- dashboard_metrics() computed SUM(estimated_value) over every visible lead regardless of
-- currency, so a pipeline holding INR and USD reported their arithmetic sum as a single
-- figure. Every row is INR today, which is the only reason this has not produced a wrong
-- number yet -- but the API accepts any three-letter code, so it is reachable.
--
-- The column now has to look like an ISO 4217 code, and the function reports totals broken
-- down by currency alongside a flag saying whether the headline number mixes them. The
-- headline fields are kept so existing clients do not break.
-- ---------------------------------------------------------------------------
UPDATE public.leads SET currency = upper(trim(currency)) WHERE currency <> upper(trim(currency));
UPDATE public.opportunities SET currency = upper(trim(currency)) WHERE currency <> upper(trim(currency));

ALTER TABLE public.leads DROP CONSTRAINT IF EXISTS leads_currency_iso4217;
ALTER TABLE public.leads ADD CONSTRAINT leads_currency_iso4217
  CHECK (currency ~ '^[A-Z]{3}$');

ALTER TABLE public.opportunities DROP CONSTRAINT IF EXISTS opportunities_currency_iso4217;
ALTER TABLE public.opportunities ADD CONSTRAINT opportunities_currency_iso4217
  CHECK (currency ~ '^[A-Z]{3}$');

CREATE OR REPLACE FUNCTION public.dashboard_metrics()
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  uid uuid := auth.uid();
  adm boolean := public.is_admin(uid);
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

  SELECT COALESCE(SUM(l.estimated_value), 0),
         COALESCE(SUM(l.estimated_value * (l.deal_probability::numeric / 100.0)), 0)
    INTO pipeline, weighted
  FROM public.leads l
  WHERE adm OR l.owner_id = uid;

  SELECT COALESCE(jsonb_object_agg(q.currency, q.total), '{}'::jsonb), COUNT(*)::int
    INTO by_currency, currency_count
  FROM (
    SELECT l.currency, SUM(l.estimated_value)::numeric AS total
    FROM public.leads l
    WHERE (adm OR l.owner_id = uid) AND l.estimated_value IS NOT NULL
    GROUP BY l.currency
  ) AS q;

  SELECT COALESCE(
           (
             SELECT jsonb_object_agg(q.stage::text, q.ev)
             FROM (
               SELECT l.stage, SUM(l.estimated_value)::numeric AS ev
               FROM public.leads l
               WHERE adm OR l.owner_id = uid
               GROUP BY l.stage
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
    AND (adm OR l.owner_id = uid);

  SELECT COUNT(*)::int INTO wins30
  FROM public.leads l
  WHERE (adm OR l.owner_id = uid)
    AND l.stage = 'won'::public.lead_stage
    AND l.updated_at >= (NOW() - INTERVAL '30 days');

  SELECT COUNT(*)::int INTO losses30
  FROM public.leads l
  WHERE (adm OR l.owner_id = uid)
    AND l.stage = 'lost'::public.lead_stage
    AND l.updated_at >= (NOW() - INTERVAL '30 days');

  SELECT COUNT(*)::int INTO fu_today
  FROM public.tasks t
  WHERE t.status = 'pending'::public.task_status
    AND t.due_date = CURRENT_DATE
    AND (adm OR t.owner_id = uid);

  SELECT COUNT(*)::int INTO overdue
  FROM public.tasks t
  WHERE t.status = 'pending'::public.task_status
    AND t.due_date < CURRENT_DATE
    AND (adm OR t.owner_id = uid);

  SELECT COALESCE(jsonb_agg(l.id), '[]'::jsonb)
    INTO hot_ids
  FROM public.leads l
  WHERE (adm OR l.owner_id = uid)
    AND l.priority_score >= 80
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

GRANT EXECUTE ON FUNCTION public.dashboard_metrics() TO authenticated;

COMMENT ON FUNCTION public.dashboard_metrics IS
  'Dashboard KPIs scoped to auth.uid(); admins see org totals. pipeline_total is only '
  'meaningful when mixed_currency is false -- read pipeline_by_currency otherwise.';

-- ---------------------------------------------------------------------------
-- 3. RLS re-evaluated auth.uid() and is_admin() once per row.
--
-- Both are STABLE, but Postgres only hoists such a call into a once-per-query InitPlan when
-- it appears as a scalar subquery. Written bare, they are evaluated per candidate row, so a
-- 200-row activity timeline made 200 is_admin() calls, each running its own lookup against
-- public.users. Wrapping them in (SELECT ...) is semantically identical and lets the planner
-- evaluate them once.
--
-- Policies are otherwise unchanged.
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS users_select ON public.users;
CREATE POLICY users_select ON public.users FOR SELECT USING (
  id = (SELECT auth.uid()) OR (SELECT public.is_admin(auth.uid()))
);

DROP POLICY IF EXISTS leads_select ON public.leads;
CREATE POLICY leads_select ON public.leads FOR SELECT USING (
  owner_id = (SELECT auth.uid()) OR (SELECT public.is_admin(auth.uid()))
);

DROP POLICY IF EXISTS leads_update ON public.leads;
CREATE POLICY leads_update ON public.leads
  FOR UPDATE
  USING (owner_id = (SELECT auth.uid()) OR (SELECT public.is_admin(auth.uid())))
  WITH CHECK (owner_id = (SELECT auth.uid()) OR (SELECT public.is_admin(auth.uid())));

DROP POLICY IF EXISTS leads_insert ON public.leads;
CREATE POLICY leads_insert ON public.leads FOR INSERT WITH CHECK (
  (SELECT auth.uid()) IS NOT NULL
  AND (owner_id = (SELECT auth.uid()) OR (SELECT public.is_admin(auth.uid())))
);

DROP POLICY IF EXISTS tasks_select ON public.tasks;
CREATE POLICY tasks_select ON public.tasks FOR SELECT USING (
  owner_id = (SELECT auth.uid()) OR (SELECT public.is_admin(auth.uid()))
);

DROP POLICY IF EXISTS tasks_insert ON public.tasks;
CREATE POLICY tasks_insert ON public.tasks FOR INSERT WITH CHECK (
  owner_id = (SELECT auth.uid()) OR (SELECT public.is_admin(auth.uid()))
);

DROP POLICY IF EXISTS tasks_update ON public.tasks;
CREATE POLICY tasks_update ON public.tasks FOR UPDATE USING (
  owner_id = (SELECT auth.uid()) OR (SELECT public.is_admin(auth.uid()))
);

DROP POLICY IF EXISTS meetings_select ON public.meetings;
CREATE POLICY meetings_select ON public.meetings FOR SELECT USING (
  owner_id = (SELECT auth.uid()) OR (SELECT public.is_admin(auth.uid()))
);

DROP POLICY IF EXISTS meetings_insert ON public.meetings;
CREATE POLICY meetings_insert ON public.meetings FOR INSERT WITH CHECK (
  owner_id = (SELECT auth.uid()) OR (SELECT public.is_admin(auth.uid()))
);

DROP POLICY IF EXISTS meetings_update ON public.meetings;
CREATE POLICY meetings_update ON public.meetings FOR UPDATE USING (
  owner_id = (SELECT auth.uid()) OR (SELECT public.is_admin(auth.uid()))
);

DROP POLICY IF EXISTS activities_select ON public.activities;
CREATE POLICY activities_select ON public.activities FOR SELECT USING (
  (SELECT public.can_access_lead(auth.uid(), activities.lead_id))
);

DROP POLICY IF EXISTS activities_insert ON public.activities;
CREATE POLICY activities_insert ON public.activities FOR INSERT WITH CHECK (
  (SELECT public.can_access_lead(auth.uid(), activities.lead_id))
  AND performed_by = (SELECT auth.uid())
);

DROP POLICY IF EXISTS opp_select ON public.opportunities;
CREATE POLICY opp_select ON public.opportunities FOR SELECT USING (
  (SELECT public.can_access_lead(auth.uid(), opportunities.lead_id))
);

DROP POLICY IF EXISTS opp_insert ON public.opportunities;
CREATE POLICY opp_insert ON public.opportunities FOR INSERT WITH CHECK (
  (SELECT public.can_access_lead(auth.uid(), opportunities.lead_id))
);

DROP POLICY IF EXISTS opp_update ON public.opportunities;
CREATE POLICY opp_update ON public.opportunities FOR UPDATE USING (
  (SELECT public.can_access_lead(auth.uid(), opportunities.lead_id))
);

DROP POLICY IF EXISTS li_select ON public.lead_intelligence;
CREATE POLICY li_select ON public.lead_intelligence FOR SELECT USING (
  (SELECT public.can_access_lead(auth.uid(), lead_intelligence.lead_id))
);

DROP POLICY IF EXISTS li_insert ON public.lead_intelligence;
CREATE POLICY li_insert ON public.lead_intelligence FOR INSERT WITH CHECK (
  (SELECT public.can_access_lead(auth.uid(), lead_intelligence.lead_id))
);

DROP POLICY IF EXISTS li_update ON public.lead_intelligence;
CREATE POLICY li_update ON public.lead_intelligence FOR UPDATE USING (
  (SELECT public.can_access_lead(auth.uid(), lead_intelligence.lead_id))
);

-- Foreign keys used by the agent-performance rollup and proposal history had no indexes,
-- so those counts were sequential scans.
CREATE INDEX IF NOT EXISTS opportunities_owner_idx ON public.opportunities (owner_id);
CREATE INDEX IF NOT EXISTS activities_performed_by_idx ON public.activities (performed_by, type);
CREATE INDEX IF NOT EXISTS proposals_created_by_idx ON public.proposals (created_by);
CREATE INDEX IF NOT EXISTS contacts_is_primary_idx ON public.contacts (company_id, is_primary);
