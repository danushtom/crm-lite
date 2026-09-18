-- Billing: one subscription row per organization, kept in sync with Dodo Payments by the
-- signature-verified webhook in apps/api/app/api/v1/endpoints/billing_webhooks.py.
--
-- This is deliberately its own table rather than columns on `organizations`: an admin may
-- update their organization (its name), and anything on that row is one PostgREST PATCH away
-- from being self-granted. Nothing here has an INSERT/UPDATE/DELETE policy, so only the
-- service role -- the webhook, and the API's checkout endpoint recording a customer id -- can
-- write it. Members can read their own organization's row; that is what the UI and the API's
-- write gate (app/services/billing.py) key off.

CREATE TABLE IF NOT EXISTS public.organization_subscriptions (
  organization_id UUID PRIMARY KEY REFERENCES public.organizations(id) ON DELETE CASCADE,
  -- 'trial' until a paid subscription becomes active; then the paid tier.
  plan TEXT NOT NULL DEFAULT 'trial'
    CHECK (plan IN ('trial', 'starter', 'growth', 'scale')),
  -- 'trialing' is ours; every other value mirrors Dodo's SubscriptionStatus verbatim.
  status TEXT NOT NULL DEFAULT 'trialing'
    CHECK (status IN (
      'trialing', 'pending', 'active', 'past_due', 'on_hold', 'paused',
      'cancelled', 'failed', 'expired'
    )),
  -- Paid seats (the subscription quantity). NULL while trialing: the trial cap lives in code.
  seats INTEGER CHECK (seats IS NULL OR seats > 0),
  trial_ends_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '14 days'),
  current_period_end TIMESTAMPTZ,
  cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE,
  dodo_customer_id TEXT UNIQUE,
  dodo_subscription_id TEXT UNIQUE,
  dodo_product_id TEXT,
  -- Timestamp of the newest webhook applied, so a late-arriving older event cannot roll the
  -- row back (Dodo, like every webhook sender, does not guarantee delivery order).
  last_event_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE public.organization_subscriptions IS
  'One per organization. Service-role writes only (Dodo webhook + checkout); members may read their own.';

ALTER TABLE public.organization_subscriptions ENABLE ROW LEVEL SECURITY;

CREATE POLICY organization_subscriptions_select ON public.organization_subscriptions
  FOR SELECT USING (organization_id = (SELECT public.current_org_id(auth.uid())));

GRANT SELECT ON public.organization_subscriptions TO authenticated;
GRANT ALL ON public.organization_subscriptions TO service_role;

-- Every organization gets a trial the moment it exists. A trigger on organizations (rather
-- than another branch inside handle_new_user()) also covers orgs created by the seed script.
CREATE OR REPLACE FUNCTION public.create_organization_subscription()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  INSERT INTO public.organization_subscriptions (organization_id)
  VALUES (NEW.id)
  ON CONFLICT (organization_id) DO NOTHING;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS organizations_create_subscription ON public.organizations;
CREATE TRIGGER organizations_create_subscription
  AFTER INSERT ON public.organizations
  FOR EACH ROW EXECUTE FUNCTION public.create_organization_subscription();

-- Existing organizations start a fresh 14-day trial from the day billing ships rather than
-- being locked out retroactively.
INSERT INTO public.organization_subscriptions (organization_id)
SELECT id FROM public.organizations
ON CONFLICT (organization_id) DO NOTHING;

-- Webhook idempotency. Dodo retries deliveries, and every delivery of one event carries the
-- same `webhook-id` header; recording it before applying makes a retry a no-op. No policies:
-- RLS enabled with none means only the service role can touch it.
CREATE TABLE IF NOT EXISTS public.billing_events (
  webhook_id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  organization_id UUID REFERENCES public.organizations(id) ON DELETE SET NULL,
  payload JSONB NOT NULL,
  received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.billing_events ENABLE ROW LEVEL SECURITY;
GRANT ALL ON public.billing_events TO service_role;
