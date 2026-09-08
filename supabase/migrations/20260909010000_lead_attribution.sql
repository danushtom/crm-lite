-- Marketing attribution on contacts, and the keys a public capture form authenticates with.
--
-- `contacts.source` is a five-value enum (cold_call, referral, website, linkedin, other). It
-- records a channel and nothing else: two Meta ads, or the same ad pointed at two different
-- landing pages, are indistinguishable. The UTM parameters below are what Meta, LinkedIn and
-- Google already append to a click, so recording them verbatim needs no mapping and loses
-- nothing. `source` stays as the coarse channel and is derived from these on capture.

-- 1. Attribution, as it arrives on the click.
ALTER TABLE public.contacts
    ADD COLUMN IF NOT EXISTS utm_source text,
    ADD COLUMN IF NOT EXISTS utm_medium text,
    ADD COLUMN IF NOT EXISTS utm_campaign text,
    ADD COLUMN IF NOT EXISTS utm_content text,
    ADD COLUMN IF NOT EXISTS utm_term text,
    ADD COLUMN IF NOT EXISTS landing_page_url text,
    ADD COLUMN IF NOT EXISTS referrer_url text,
    ADD COLUMN IF NOT EXISTS captured_at timestamptz;

COMMENT ON COLUMN public.contacts.utm_source IS 'Platform the click came from, as the ad network sent it: facebook, linkedin, google, newsletter. Normalised for display, never rewritten here.';
COMMENT ON COLUMN public.contacts.utm_medium IS 'cpc, paid_social, organic, referral, email. Together with utm_source this is what decides the display channel and the derived contacts.source.';
COMMENT ON COLUMN public.contacts.utm_campaign IS 'Campaign name as set in the ad platform.';
COMMENT ON COLUMN public.contacts.utm_content IS 'The specific ad or creative within the campaign -- what makes two ads in one campaign tellable apart.';
COMMENT ON COLUMN public.contacts.landing_page_url IS 'The page whose form they actually submitted.';
COMMENT ON COLUMN public.contacts.referrer_url IS 'Document referrer at submission, for the cases where no UTM was set.';
COMMENT ON COLUMN public.contacts.captured_at IS 'When the form was submitted. Distinct from created_at, which is when the row was written.';

-- Grouping contacts by channel is the Contacts page headline query.
CREATE INDEX IF NOT EXISTS contacts_attribution_idx
    ON public.contacts (organization_id, utm_source, utm_medium);

-- 2. Capture keys.
--
-- A public form has no logged-in user, so the key is what says which organization a submission
-- belongs to. It is a write-only credential: the capture endpoint resolves the organization
-- from it server-side and never echoes anything back, so holding one lets you create a lead
-- and learn nothing.
--
-- Its own table rather than a column on organizations, for three reasons: keys can be rotated
-- without downtime by running two at once, revoked individually when a landing page is retired,
-- and -- most importantly -- kept out of reach of non-admin members. A column on organizations
-- would be readable by every member through the existing org SELECT policy, including from the
-- browser's own Supabase client.
CREATE TABLE IF NOT EXISTS public.lead_capture_keys (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES public.organizations(id),
    key text NOT NULL UNIQUE,
    name text NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    -- Leads captured with this key are assigned here. Null means "the organization's first
    -- full-access user", resolved at capture time so a key does not break when someone leaves.
    owner_id uuid REFERENCES public.users(id),
    created_by uuid REFERENCES public.users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    last_used_at timestamptz
);

COMMENT ON TABLE public.lead_capture_keys IS 'Write-only credentials for the public lead-capture endpoint. One per landing page or ad platform, so a leaked key can be revoked without taking the others down.';

CREATE INDEX IF NOT EXISTS lead_capture_keys_org_idx
    ON public.lead_capture_keys (organization_id);

-- Only a live key resolves, and the endpoint looks up by key alone.
CREATE INDEX IF NOT EXISTS lead_capture_keys_active_idx
    ON public.lead_capture_keys (key) WHERE is_active;

CREATE TRIGGER lead_capture_keys_set_org BEFORE INSERT ON public.lead_capture_keys
    FOR EACH ROW EXECUTE FUNCTION public.set_parent_organization('users', 'created_by');

ALTER TABLE public.lead_capture_keys ENABLE ROW LEVEL SECURITY;

-- Admin-only in every direction, SELECT included: this is a credential, not a setting. All
-- four verbs are spelled out deliberately -- phone_numbers shipped without an UPDATE policy in
-- this same codebase, and a missing policy is silent (PostgREST reports zero rows affected as
-- success), so the gap only showed up as a write that appeared to work and did nothing.
-- The capture endpoint reads this table with the service role, which bypasses these entirely.
CREATE POLICY lead_capture_keys_select ON public.lead_capture_keys FOR SELECT USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (SELECT public.is_admin(auth.uid()))
);

CREATE POLICY lead_capture_keys_insert ON public.lead_capture_keys FOR INSERT WITH CHECK (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (SELECT public.is_admin(auth.uid()))
);

CREATE POLICY lead_capture_keys_update ON public.lead_capture_keys FOR UPDATE
  USING (
    organization_id = (SELECT public.current_org_id(auth.uid()))
    AND (SELECT public.is_admin(auth.uid()))
  )
  WITH CHECK (
    organization_id = (SELECT public.current_org_id(auth.uid()))
    AND (SELECT public.is_admin(auth.uid()))
  );

CREATE POLICY lead_capture_keys_delete ON public.lead_capture_keys FOR DELETE USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (SELECT public.is_admin(auth.uid()))
);
