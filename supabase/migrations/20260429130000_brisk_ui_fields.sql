-- Brisk-style UI fields + marketing channel snapshots (CAC widgets)

-- Company branding / discovery fields
ALTER TABLE public.companies ADD COLUMN IF NOT EXISTS logo_url TEXT;
ALTER TABLE public.companies ADD COLUMN IF NOT EXISTS linkedin_url TEXT;

DO $$
BEGIN
  CREATE TYPE public.company_segment AS ENUM ('sme', 'startup', 'enterprise');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END;
$$;

ALTER TABLE public.companies ADD COLUMN IF NOT EXISTS segment public.company_segment;

CREATE INDEX IF NOT EXISTS companies_segment_idx ON public.companies (segment);

-- Contact avatar (matches companies grid mock)
ALTER TABLE public.contacts ADD COLUMN IF NOT EXISTS avatar_url TEXT;

-- Monthly channel metrics for CAC-style dashboards (admin-maintained)
CREATE TABLE public.marketing_channel_metrics (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  period_month DATE NOT NULL,
  channel TEXT NOT NULL,
  spend NUMERIC(12, 2),
  new_customer_share NUMERIC(7, 4),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (period_month, channel)
);

CREATE INDEX IF NOT EXISTS marketing_channel_metrics_period_idx
  ON public.marketing_channel_metrics (period_month DESC);

ALTER TABLE public.marketing_channel_metrics ENABLE ROW LEVEL SECURITY;

CREATE POLICY marketing_metrics_select ON public.marketing_channel_metrics
  FOR SELECT USING (auth.uid() IS NOT NULL);

CREATE POLICY marketing_metrics_insert ON public.marketing_channel_metrics
  FOR INSERT WITH CHECK (public.is_admin(auth.uid()));

CREATE POLICY marketing_metrics_update ON public.marketing_channel_metrics
  FOR UPDATE USING (public.is_admin(auth.uid()));

CREATE POLICY marketing_metrics_delete ON public.marketing_channel_metrics
  FOR DELETE USING (public.is_admin(auth.uid()));

COMMENT ON TABLE public.marketing_channel_metrics IS 'CAC / acquisition channel spend snapshots; write restricted to admin.';
