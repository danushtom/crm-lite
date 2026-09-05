-- Aggregated dashboard metrics — avoids full-table scans from FastAPI (SECURITY DEFINER uses caller auth.uid())

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

COMMENT ON FUNCTION public.dashboard_metrics IS 'Dashboard KPIs scoped to auth.uid(); admins see org totals.';
