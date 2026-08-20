-- Canonical pipeline (Kanban) lives on public.opportunities — one row per lead.
-- Leads keep mirrored stage/value fields for scoring APIs and legacy reads (synced from opportunities via trigger).
-- Proposals remain FK → opportunities.opportunity_id (unchanged).

ALTER TABLE public.opportunities
  ADD COLUMN IF NOT EXISTS stage public.lead_stage,
  ADD COLUMN IF NOT EXISTS deal_probability SMALLINT,
  ADD COLUMN IF NOT EXISTS priority_score SMALLINT,
  ADD COLUMN IF NOT EXISTS tags TEXT[] NOT NULL DEFAULT '{}';

UPDATE public.opportunities o
SET
  stage = l.stage,
  deal_probability = l.deal_probability,
  priority_score = l.priority_score,
  tags = l.tags,
  quoted_value = COALESCE(o.quoted_value, l.estimated_value),
  currency = l.currency
FROM public.leads l
WHERE l.id = o.lead_id;

INSERT INTO public.opportunities (
  lead_id,
  owner_id,
  title,
  stage,
  quoted_value,
  currency,
  deal_probability,
  priority_score,
  tags,
  status
)
SELECT
  l.id,
  l.owner_id,
  'Opportunity',
  l.stage,
  l.estimated_value,
  l.currency,
  l.deal_probability,
  l.priority_score,
  l.tags,
  'active'::public.opportunity_status
FROM public.leads l
WHERE NOT EXISTS (SELECT 1 FROM public.opportunities o WHERE o.lead_id = l.id);

UPDATE public.opportunities
SET deal_probability = 50
WHERE deal_probability IS NULL;

UPDATE public.opportunities
SET priority_score = 0
WHERE priority_score IS NULL;

ALTER TABLE public.opportunities ALTER COLUMN stage SET NOT NULL;
ALTER TABLE public.opportunities ALTER COLUMN stage SET DEFAULT 'prospect';

ALTER TABLE public.opportunities ALTER COLUMN deal_probability SET NOT NULL;
ALTER TABLE public.opportunities ALTER COLUMN deal_probability SET DEFAULT 50;

ALTER TABLE public.opportunities ALTER COLUMN priority_score SET NOT NULL;
ALTER TABLE public.opportunities ALTER COLUMN priority_score SET DEFAULT 0;

ALTER TABLE public.opportunities ADD CONSTRAINT opportunities_deal_probability_check
  CHECK (deal_probability BETWEEN 0 AND 100);

ALTER TABLE public.opportunities ADD CONSTRAINT opportunities_priority_score_check
  CHECK (priority_score BETWEEN 0 AND 100);

CREATE INDEX IF NOT EXISTS opportunities_stage_idx ON public.opportunities (stage);

-- Pipeline edits log here; avoid duplicate rows from leads (§ scoring uses leads.* mirrors).
DROP TRIGGER IF EXISTS leads_stage_change ON public.leads;

CREATE OR REPLACE FUNCTION public.sync_lead_from_opportunity()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  UPDATE public.leads
  SET
    stage = NEW.stage,
    estimated_value = NEW.quoted_value,
    currency = NEW.currency,
    deal_probability = NEW.deal_probability,
    tags = NEW.tags,
    updated_at = NEW.updated_at
  WHERE id = NEW.lead_id;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS opportunities_sync_lead ON public.opportunities;
CREATE TRIGGER opportunities_sync_lead
AFTER UPDATE ON public.opportunities
FOR EACH ROW EXECUTE FUNCTION public.sync_lead_from_opportunity();

CREATE OR REPLACE FUNCTION public.ensure_opportunity_for_lead()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  INSERT INTO public.opportunities (
    lead_id,
    owner_id,
    title,
    stage,
    quoted_value,
    currency,
    deal_probability,
    priority_score,
    tags
  )
  VALUES (
    NEW.id,
    NEW.owner_id,
    'Opportunity',
    NEW.stage,
    NEW.estimated_value,
    NEW.currency,
    NEW.deal_probability,
    NEW.priority_score,
    NEW.tags
  )
  ON CONFLICT (lead_id) DO NOTHING;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS leads_after_insert_opportunity ON public.leads;
CREATE TRIGGER leads_after_insert_opportunity
AFTER INSERT ON public.leads
FOR EACH ROW EXECUTE FUNCTION public.ensure_opportunity_for_lead();

CREATE OR REPLACE FUNCTION public.log_opportunity_stage_change()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF TG_OP = 'UPDATE' AND OLD.stage IS DISTINCT FROM NEW.stage THEN
    INSERT INTO public.activities (lead_id, type, description, performed_by, metadata)
    VALUES (
      NEW.lead_id,
      'stage_change'::public.activity_type,
      'Opportunity stage changed from ' || OLD.stage::TEXT || ' to ' || NEW.stage::TEXT,
      auth.uid(),
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

DROP TRIGGER IF EXISTS opportunities_stage_change_log ON public.opportunities;
CREATE TRIGGER opportunities_stage_change_log
AFTER UPDATE ON public.opportunities
FOR EACH ROW EXECUTE FUNCTION public.log_opportunity_stage_change();
