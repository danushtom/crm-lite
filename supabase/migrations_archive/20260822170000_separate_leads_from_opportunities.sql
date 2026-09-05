-- Give leads and opportunities one owner each for every fact they describe.
--
-- The tables were in a strict 1:1 (opportunities.lead_id UNIQUE, a row auto-created by
-- trigger for every lead) while duplicating six facts between them: stage, currency,
-- deal_probability, priority_score, tags, and estimated_value/quoted_value -- the same
-- number under two names. A trigger copied opportunities back onto leads on every write,
-- so the API had to split each incoming update across both tables and then re-read, because
-- the trigger had rewritten what it just wrote.
--
-- On top of that sat leads.is_opportunity, a boolean entirely independent of whether an
-- opportunity row existed: 4 of 14 leads were flagged, all 14 had a row. "Conversion"
-- therefore converted nothing -- it set a title on a row that already existed and flipped a
-- flag -- and UNIQUE(lead_id) meant a lead could never have a second opportunity, which is
-- exactly the agency case: the build, then the retainer.
--
-- The columns that were *not* duplicated already split cleanly along the right seam, so the
-- two entities are kept and the duplication removed:
--
--   leads         qualification -- who, from where, what kind of work, when to follow up
--   opportunities the pursuit   -- stage, commercials, scope, proposals; N per lead
--
-- Anything a lead needs to know about its pipeline position is read from its opportunities.

-- ---------------------------------------------------------------------------
-- 1. Stop the mirroring.
-- ---------------------------------------------------------------------------
DROP TRIGGER IF EXISTS opportunities_sync_lead ON public.opportunities;
DROP FUNCTION IF EXISTS public.sync_lead_from_opportunity();

-- ---------------------------------------------------------------------------
-- 2. Move the score override onto the pursuit it actually pins.
-- ---------------------------------------------------------------------------
ALTER TABLE public.opportunities
  ADD COLUMN IF NOT EXISTS score_override SMALLINT
    CHECK (score_override IS NULL OR score_override BETWEEN 0 AND 100),
  ADD COLUMN IF NOT EXISTS score_override_reason TEXT;

UPDATE public.opportunities o
SET score_override = l.score_override,
    score_override_reason = l.score_override_reason
FROM public.leads l
WHERE l.id = o.lead_id
  AND l.score_override IS NOT NULL;

-- Make sure nothing is lost before the lead columns go: the trigger kept these in step, but
-- assert rather than assume.
DO $$
DECLARE
  drifted INT;
BEGIN
  SELECT COUNT(*) INTO drifted
  FROM public.leads l
  JOIN public.opportunities o ON o.lead_id = l.id
  WHERE l.stage IS DISTINCT FROM o.stage
     OR l.estimated_value IS DISTINCT FROM o.quoted_value
     OR l.currency IS DISTINCT FROM o.currency
     OR l.deal_probability IS DISTINCT FROM o.deal_probability;

  IF drifted > 0 THEN
    RAISE EXCEPTION
      'Refusing to drop lead columns: % lead/opportunity pairs disagree. Reconcile first.',
      drifted;
  END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- 3. Allow more than one pursuit per lead.
-- ---------------------------------------------------------------------------
ALTER TABLE public.opportunities DROP CONSTRAINT IF EXISTS opportunities_lead_id_key;
CREATE INDEX IF NOT EXISTS opportunities_lead_idx ON public.opportunities (lead_id);

-- Only one pursuit per lead may be open at a time; closed ones are history and unbounded.
CREATE UNIQUE INDEX IF NOT EXISTS opportunities_one_active_per_lead_idx
  ON public.opportunities (lead_id)
  WHERE status = 'active'::public.opportunity_status;

-- ---------------------------------------------------------------------------
-- 4. Drop the mirrored columns from leads.
-- ---------------------------------------------------------------------------
ALTER TABLE public.leads
  DROP COLUMN IF EXISTS stage,
  DROP COLUMN IF EXISTS estimated_value,
  DROP COLUMN IF EXISTS currency,
  DROP COLUMN IF EXISTS deal_probability,
  DROP COLUMN IF EXISTS priority_score,
  DROP COLUMN IF EXISTS tags,
  DROP COLUMN IF EXISTS is_opportunity,
  DROP COLUMN IF EXISTS score_override,
  DROP COLUMN IF EXISTS score_override_reason;

-- ---------------------------------------------------------------------------
-- 5. A new lead opens its first pursuit.
--
-- Kept, because a lead you are working is a pursuit at the 'prospect' stage -- that is what
-- the first pipeline column means. What changes is that it is no longer a shell mirroring
-- the lead: it owns the commercial fields outright, and further opportunities can be opened
-- against the same lead for upsell.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.ensure_opportunity_for_lead()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
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

-- ---------------------------------------------------------------------------
-- 6. Aggregate the dashboard from the pursuits, which now hold the money.
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

  SELECT COALESCE(SUM(o.quoted_value), 0),
         COALESCE(SUM(o.quoted_value * (o.deal_probability::numeric / 100.0)), 0)
    INTO pipeline, weighted
  FROM public.opportunities o
  JOIN public.leads l ON l.id = o.lead_id
  WHERE adm OR l.owner_id = uid;

  SELECT COALESCE(jsonb_object_agg(q.currency, q.total), '{}'::jsonb), COUNT(*)::int
    INTO by_currency, currency_count
  FROM (
    SELECT o.currency, SUM(o.quoted_value)::numeric AS total
    FROM public.opportunities o
    JOIN public.leads l ON l.id = o.lead_id
    WHERE (adm OR l.owner_id = uid) AND o.quoted_value IS NOT NULL
    GROUP BY o.currency
  ) AS q;

  SELECT COALESCE(
           (
             SELECT jsonb_object_agg(q.stage::text, q.ev)
             FROM (
               SELECT o.stage, SUM(o.quoted_value)::numeric AS ev
               FROM public.opportunities o
               JOIN public.leads l ON l.id = o.lead_id
               WHERE adm OR l.owner_id = uid
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
    AND (adm OR l.owner_id = uid);

  SELECT COUNT(*)::int INTO wins30
  FROM public.opportunities o
  JOIN public.leads l ON l.id = o.lead_id
  WHERE (adm OR l.owner_id = uid)
    AND o.stage = 'won'::public.lead_stage
    AND o.updated_at >= (NOW() - INTERVAL '30 days');

  SELECT COUNT(*)::int INTO losses30
  FROM public.opportunities o
  JOIN public.leads l ON l.id = o.lead_id
  WHERE (adm OR l.owner_id = uid)
    AND o.stage = 'lost'::public.lead_stage
    AND o.updated_at >= (NOW() - INTERVAL '30 days');

  SELECT COUNT(*)::int INTO fu_today
  FROM public.tasks t
  WHERE t.status = 'pending'::public.task_status
    AND t.due_at >= date_trunc('day', NOW())
    AND t.due_at < date_trunc('day', NOW()) + INTERVAL '1 day'
    AND (adm OR t.owner_id = uid);

  SELECT COUNT(*)::int INTO overdue
  FROM public.tasks t
  WHERE t.status = 'pending'::public.task_status
    AND t.due_at < NOW()
    AND (adm OR t.owner_id = uid);

  -- "Hot" is a property of the pursuit; "gone quiet" is a property of the lead.
  SELECT COALESCE(jsonb_agg(DISTINCT l.id), '[]'::jsonb)
    INTO hot_ids
  FROM public.opportunities o
  JOIN public.leads l ON l.id = o.lead_id
  WHERE (adm OR l.owner_id = uid)
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

GRANT EXECUTE ON FUNCTION public.dashboard_metrics() TO authenticated;

COMMENT ON TABLE public.leads IS
  'Qualification record: who the prospect is and how to work them. Pipeline position and '
  'commercials live on public.opportunities, one or more per lead.';

COMMENT ON TABLE public.opportunities IS
  'A pursuit against a lead: stage, commercials, scope and proposals. Multiple per lead '
  '(the build, then the retainer); at most one active at a time.';
