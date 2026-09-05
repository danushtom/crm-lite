-- AI voice sales agents: org-configurable Twilio/voice-AI-platform assistants that place and
-- receive phone calls, with per-contact consent gating and an enforced disclosure preamble.
-- See the approved plan for the full design rationale.

-- ---------------------------------------------------------------------------
-- 1. Enums.
-- ---------------------------------------------------------------------------
CREATE TYPE public.voice_agent_direction AS ENUM ('inbound', 'outbound', 'both');
CREATE TYPE public.call_direction AS ENUM ('inbound', 'outbound');
CREATE TYPE public.call_status AS ENUM (
  'queued', 'ringing', 'in_progress', 'completed', 'failed', 'no_consent_blocked'
);

-- ---------------------------------------------------------------------------
-- 2. voice_agents -- one configured AI assistant per organization.
-- ---------------------------------------------------------------------------
CREATE TABLE public.voice_agents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  name TEXT NOT NULL,
  system_prompt TEXT NOT NULL,
  direction public.voice_agent_direction NOT NULL DEFAULT 'outbound',
  voice_id TEXT,
  platform TEXT NOT NULL DEFAULT 'vapi',
  platform_assistant_id TEXT,
  phone_number_id UUID,
  -- Fixed, org-branded disclosure text bound to the platform's own greeting/first-message
  -- field (never the admin-authored system_prompt) -- see voice_platform.create_assistant().
  -- Kept as its own column, not folded into system_prompt, specifically so it can be enforced
  -- structurally rather than relying on prompt discipline.
  disclosure_script TEXT NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_by UUID NOT NULL REFERENCES public.users (id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  version INTEGER NOT NULL DEFAULT 1,
  deleted_at TIMESTAMPTZ
);

CREATE INDEX voice_agents_org_idx ON public.voice_agents (organization_id) WHERE deleted_at IS NULL;

CREATE TRIGGER voice_agents_set_org BEFORE INSERT ON public.voice_agents
  FOR EACH ROW EXECUTE FUNCTION public.set_parent_organization('users', 'created_by');

CREATE TRIGGER voice_agents_touch BEFORE UPDATE ON public.voice_agents
  FOR EACH ROW EXECUTE FUNCTION public.touch_updated_at();

CREATE TRIGGER voice_agents_version BEFORE UPDATE ON public.voice_agents
  FOR EACH ROW EXECUTE FUNCTION public.bump_version();

-- ---------------------------------------------------------------------------
-- 3. phone_numbers -- numbers an org has attached (v1: manually registered, already owned).
-- ---------------------------------------------------------------------------
CREATE TABLE public.phone_numbers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  e164_number TEXT NOT NULL,
  provider TEXT NOT NULL DEFAULT 'twilio',
  provider_number_sid TEXT,
  assigned_voice_agent_id UUID REFERENCES public.voice_agents (id),
  created_by UUID NOT NULL REFERENCES public.users (id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (e164_number)
);

CREATE TRIGGER phone_numbers_set_org BEFORE INSERT ON public.phone_numbers
  FOR EACH ROW EXECUTE FUNCTION public.set_parent_organization('users', 'created_by');

ALTER TABLE public.voice_agents
  ADD CONSTRAINT voice_agents_phone_number_id_fkey
  FOREIGN KEY (phone_number_id) REFERENCES public.phone_numbers (id);

-- ---------------------------------------------------------------------------
-- 4. voice_agent_documents -- uploaded knowledge-base files (pricing sheets, FAQs, scripts).
-- ---------------------------------------------------------------------------
CREATE TABLE public.voice_agent_documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  voice_agent_id UUID NOT NULL REFERENCES public.voice_agents (id) ON DELETE CASCADE,
  filename TEXT NOT NULL,
  file_url TEXT NOT NULL,
  content_type TEXT,
  uploaded_by UUID NOT NULL REFERENCES public.users (id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX voice_agent_documents_agent_idx ON public.voice_agent_documents (voice_agent_id);

CREATE TRIGGER voice_agent_documents_set_org BEFORE INSERT ON public.voice_agent_documents
  FOR EACH ROW EXECUTE FUNCTION public.set_parent_organization('voice_agents', 'voice_agent_id');

-- ---------------------------------------------------------------------------
-- 5. calls -- one row per call attempt. Written only by service-role code (the webhook
-- handler, or the outbound-call-placement endpoint) -- never directly by an authenticated
-- user's own RLS-scoped client. See set_call_organization() below for why that matters.
-- ---------------------------------------------------------------------------
CREATE TABLE public.calls (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  voice_agent_id UUID NOT NULL REFERENCES public.voice_agents (id),
  contact_id UUID REFERENCES public.contacts (id),
  lead_id UUID REFERENCES public.leads (id),
  direction public.call_direction NOT NULL,
  status public.call_status NOT NULL DEFAULT 'queued',
  provider_call_id TEXT,
  twilio_call_sid TEXT,
  to_number TEXT NOT NULL,
  from_number TEXT NOT NULL,
  started_at TIMESTAMPTZ,
  ended_at TIMESTAMPTZ,
  duration_seconds INTEGER,
  recording_url TEXT,
  transcript TEXT,
  summary TEXT,
  suggested_next_action TEXT,
  outcome TEXT,
  initiated_by UUID REFERENCES public.users (id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  version INTEGER NOT NULL DEFAULT 1,
  UNIQUE (provider_call_id)
);

CREATE INDEX calls_org_created_idx ON public.calls (organization_id, created_at DESC);
CREATE INDEX calls_lead_idx ON public.calls (lead_id);

-- Trust organization_id when a service-role caller (no auth.uid()) has already resolved and
-- supplied it directly -- exactly the same shape as set_role_organization(), which exists for
-- the identical reason (roles has no single owning FK either). When a real user session is
-- present, derive it from the agent instead of trusting the row.
CREATE OR REPLACE FUNCTION public.set_call_organization()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF auth.uid() IS NOT NULL THEN
    SELECT organization_id INTO NEW.organization_id
    FROM public.voice_agents WHERE id = NEW.voice_agent_id;
  END IF;
  IF NEW.organization_id IS NULL THEN
    RAISE EXCEPTION 'Cannot determine organization for this call' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER calls_set_org BEFORE INSERT ON public.calls
  FOR EACH ROW EXECUTE FUNCTION public.set_call_organization();

CREATE TRIGGER calls_touch BEFORE UPDATE ON public.calls
  FOR EACH ROW EXECUTE FUNCTION public.touch_updated_at();

CREATE TRIGGER calls_version BEFORE UPDATE ON public.calls
  FOR EACH ROW EXECUTE FUNCTION public.bump_version();

-- ---------------------------------------------------------------------------
-- 6. Consent (contacts) and per-org compliance acknowledgment (organizations).
-- ---------------------------------------------------------------------------
ALTER TABLE public.contacts
  ADD COLUMN ai_call_consent BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN ai_call_consent_at TIMESTAMPTZ,
  ADD COLUMN ai_call_consent_recorded_by UUID REFERENCES public.users (id);

ALTER TABLE public.organizations
  ADD COLUMN ai_calling_compliance_ack_at TIMESTAMPTZ,
  ADD COLUMN ai_calling_compliance_ack_by UUID REFERENCES public.users (id);

-- ---------------------------------------------------------------------------
-- 7. RLS.
-- ---------------------------------------------------------------------------
ALTER TABLE public.voice_agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.phone_numbers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.voice_agent_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.calls ENABLE ROW LEVEL SECURITY;

CREATE POLICY voice_agents_select ON public.voice_agents FOR SELECT USING (
  deleted_at IS NULL
  AND organization_id = (SELECT public.current_org_id(auth.uid()))
);

CREATE POLICY voice_agents_insert ON public.voice_agents FOR INSERT WITH CHECK (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (SELECT public.is_admin(auth.uid()))
);

CREATE POLICY voice_agents_update ON public.voice_agents FOR UPDATE
  USING (
    organization_id = (SELECT public.current_org_id(auth.uid()))
    AND (SELECT public.is_admin(auth.uid()))
  )
  WITH CHECK (
    organization_id = (SELECT public.current_org_id(auth.uid()))
    AND (SELECT public.is_admin(auth.uid()))
  );

CREATE POLICY voice_agents_delete ON public.voice_agents FOR DELETE USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (SELECT public.is_admin(auth.uid()))
);

CREATE POLICY phone_numbers_select ON public.phone_numbers FOR SELECT USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
);

CREATE POLICY phone_numbers_insert ON public.phone_numbers FOR INSERT WITH CHECK (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (SELECT public.is_admin(auth.uid()))
);

CREATE POLICY phone_numbers_delete ON public.phone_numbers FOR DELETE USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (SELECT public.is_admin(auth.uid()))
);

CREATE POLICY voice_agent_documents_select ON public.voice_agent_documents FOR SELECT USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
);

CREATE POLICY voice_agent_documents_insert ON public.voice_agent_documents FOR INSERT WITH CHECK (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (SELECT public.is_admin(auth.uid()))
);

CREATE POLICY voice_agent_documents_delete ON public.voice_agent_documents FOR DELETE USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (SELECT public.is_admin(auth.uid()))
);

-- calls: SELECT only. initiated_by is NULL for inbound/system calls, so ownership is checked
-- through the lead rather than a bare initiated_by = auth.uid(). No INSERT/UPDATE/DELETE
-- policy for `authenticated` at all -- rows arrive only via a service-role writer (the webhook
-- handler, or the call-placement endpoint's admin client), matching the audit_log precedent.
CREATE POLICY calls_select ON public.calls FOR SELECT USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (
    (SELECT public.is_admin(auth.uid()))
    OR EXISTS (
      SELECT 1 FROM public.leads l WHERE l.id = calls.lead_id AND l.owner_id = auth.uid()
    )
  )
);

-- ---------------------------------------------------------------------------
-- 8. Soft-delete function for voice_agents (same shape as soft_delete_company()).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.soft_delete_voice_agent(
  p_id UUID, p_expected_version INTEGER DEFAULT NULL
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  uid UUID := auth.uid();
  target public.voice_agents%ROWTYPE;
BEGIN
  IF uid IS NULL THEN
    RAISE EXCEPTION 'not authenticated' USING ERRCODE = '42501';
  END IF;

  SELECT * INTO target FROM public.voice_agents WHERE id = p_id;
  IF NOT FOUND OR target.deleted_at IS NOT NULL THEN
    RETURN jsonb_build_object('status', 'not_found');
  END IF;

  IF NOT (
    target.organization_id = public.current_org_id(uid)
    AND public.is_admin(uid)
  ) THEN
    RETURN jsonb_build_object('status', 'forbidden');
  END IF;

  IF EXISTS (
    SELECT 1 FROM public.calls c
    WHERE c.voice_agent_id = p_id AND c.status IN ('queued', 'ringing', 'in_progress')
  ) THEN
    RETURN jsonb_build_object('status', 'referenced');
  END IF;

  IF p_expected_version IS NOT NULL AND target.version <> p_expected_version THEN
    RETURN jsonb_build_object('status', 'version_mismatch', 'current_version', target.version);
  END IF;

  UPDATE public.voice_agents SET deleted_at = NOW() WHERE id = p_id;
  RETURN jsonb_build_object('status', 'deleted');
END;
$$;

-- ---------------------------------------------------------------------------
-- 9. Permissions catalog + role grants.
-- ---------------------------------------------------------------------------
INSERT INTO public.permissions (resource, action, description) VALUES
  ('voice_agents', 'read', 'View voice agents, phone numbers and call history'),
  ('voice_agents', 'write', 'Create or update a voice agent, its documents, or a phone number'),
  ('voice_agents', 'manage', 'Place outbound calls and manage the org''s AI-calling compliance acknowledgment');

-- Admin already gets every catalog permission via seed_default_roles()'s blanket
-- `SELECT id FROM permissions` -- no change needed there. Redefine the function only to add
-- voice_agents.read to the Agent/SDR allow-list (reps should see call history for leads they
-- own); write/manage stay admin-only given the cost and compliance stakes of this feature.
CREATE OR REPLACE FUNCTION public.seed_default_roles(org_id UUID)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  admin_role_id UUID;
  agent_role_id UUID;
  sdr_role_id UUID;
  partner_role_id UUID;
BEGIN
  INSERT INTO public.roles (organization_id, name, grants_full_access, is_system)
    VALUES (org_id, 'Admin', TRUE, TRUE) RETURNING id INTO admin_role_id;
  INSERT INTO public.roles (organization_id, name, grants_full_access, is_system)
    VALUES (org_id, 'Agent', FALSE, TRUE) RETURNING id INTO agent_role_id;
  INSERT INTO public.roles (organization_id, name, grants_full_access, is_system)
    VALUES (org_id, 'SDR', FALSE, TRUE) RETURNING id INTO sdr_role_id;
  INSERT INTO public.roles (organization_id, name, grants_full_access, is_system)
    VALUES (org_id, 'Partner', FALSE, TRUE) RETURNING id INTO partner_role_id;

  INSERT INTO public.role_permissions (role_id, permission_id)
  SELECT admin_role_id, id FROM public.permissions;

  INSERT INTO public.role_permissions (role_id, permission_id)
  SELECT r.rid, p.id
  FROM public.permissions p
  CROSS JOIN (VALUES (agent_role_id), (sdr_role_id)) AS r(rid)
  WHERE (p.resource, p.action) IN (
    ('companies', 'read'), ('companies', 'write'),
    ('contacts', 'read'), ('contacts', 'write'), ('contacts', 'delete'),
    ('leads', 'read'), ('leads', 'write'), ('leads', 'delete'),
    ('lead_intelligence', 'read'), ('lead_intelligence', 'write'),
    ('opportunities', 'read'), ('opportunities', 'write'), ('opportunities', 'delete'),
    ('proposals', 'read'), ('proposals', 'write'), ('proposals', 'delete'),
    ('tasks', 'read'), ('tasks', 'write'), ('tasks', 'delete'),
    ('meetings', 'read'), ('meetings', 'write'), ('meetings', 'delete'),
    ('activities', 'read'), ('activities', 'write'),
    ('marketing_metrics', 'read'),
    ('voice_agents', 'read')
  );

  INSERT INTO public.role_permissions (role_id, permission_id)
  SELECT partner_role_id, p.id
  FROM public.permissions p
  WHERE (p.resource, p.action) IN (
    ('companies', 'read'), ('companies', 'write'),
    ('contacts', 'read'), ('contacts', 'write'), ('contacts', 'delete'),
    ('leads', 'read'), ('leads', 'write'), ('leads', 'delete'),
    ('lead_intelligence', 'read'),
    ('opportunities', 'read'), ('opportunities', 'write'), ('opportunities', 'delete'),
    ('proposals', 'read'), ('proposals', 'write'), ('proposals', 'delete'),
    ('tasks', 'read'), ('tasks', 'write'), ('tasks', 'delete'),
    ('meetings', 'read'), ('meetings', 'write'), ('meetings', 'delete'),
    ('activities', 'read'), ('activities', 'write'),
    ('marketing_metrics', 'read')
  );

  RETURN admin_role_id;
END;
$$;

-- Backfill: seed_default_roles() only runs for orgs created from here on. Existing orgs'
-- Agent/SDR roles need voice_agents.read granted explicitly.
DO $$
DECLARE
  voice_agents_read_id UUID;
BEGIN
  SELECT id INTO voice_agents_read_id FROM public.permissions
    WHERE resource = 'voice_agents' AND action = 'read';

  INSERT INTO public.role_permissions (role_id, permission_id)
  SELECT r.id, voice_agents_read_id
  FROM public.roles r
  WHERE r.name IN ('Agent', 'SDR')
  ON CONFLICT DO NOTHING;
END;
$$;
