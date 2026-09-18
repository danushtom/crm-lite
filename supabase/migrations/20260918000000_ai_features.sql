-- ===========================================================================
-- AI features: call notes, deal health, proposal drafting, the CRM assistant,
-- and the knowledge-base indexing state behind voice-agent RAG.
--
-- Also closes a real authorization gap that predates this work: the API checks
-- granular permissions with require_permission(), but RLS could only ever check
-- is_admin(), because no SQL-side has_permission() existed. Section 1 creates it.
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- 1. has_permission() -- the permission equivalent of is_admin().
--
-- Until now, `roles.grants_full_access` was the only role fact the database could
-- act on. That is why voice_agents.py carries a docstring admitting that a custom
-- role granted `voice_agents.write` passes the API's check and is then rejected by
-- the database: the two layers were asking different questions.
--
-- Like is_admin(), this is a chokepoint. Every policy that needs a permission check
-- calls it rather than inlining the users -> roles -> role_permissions -> permissions
-- join. CLAUDE.md records what happened the one time a policy inlined its own check
-- instead (can_access_lead(), which broke silently and caused an outage) -- do not
-- reintroduce that pattern here.
-- ---------------------------------------------------------------------------
-- `u.is_active` is not optional here. 20260909020000 made deactivation actually revoke access
-- by adding that check to current_org_id(), is_admin() and can_access_lead(); a fourth
-- chokepoint that omitted it would be a way back in for a revoked user. Every policy below also
-- compares against current_org_id(), which already fails closed for a revoked user, but the
-- chokepoint has to carry the rule on its own -- the next policy to call this function without
-- that companion clause would otherwise be quietly broken. That is precisely the mistake
-- can_access_lead() made, and CLAUDE.md records what it cost.
CREATE OR REPLACE FUNCTION public.has_permission(uid UUID, res TEXT, act TEXT)
RETURNS BOOLEAN
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.users u
    JOIN public.roles r ON r.id = u.role_id
    WHERE u.id = uid
      AND u.is_active
      AND (
        -- A full-access role bypasses the catalog entirely, exactly as it does in
        -- is_admin() and in deps.py's require_permission().
        r.grants_full_access
        OR EXISTS (
          SELECT 1
          FROM public.role_permissions rp
          JOIN public.permissions p ON p.id = rp.permission_id
          -- permissions.action is the permission_action enum, not text. Casting the column
          -- (rather than the argument) keeps the signature text-typed for callers, and an
          -- unknown action simply matches nothing instead of raising.
          WHERE rp.role_id = r.id AND p.resource = res AND p.action::TEXT = act
        )
      )
  )
$$;

COMMENT ON FUNCTION public.has_permission(UUID, TEXT, TEXT) IS
  'Single chokepoint for "holds this granular permission". Requires the user to still be '
  'active -- a revoked user holds nothing. A full-access role passes without an explicit '
  'grant, matching is_admin() and deps.py''s require_permission().';

-- Explicit grants, matching how is_admin() and current_org_id() are granted in the initial
-- schema. A policy expression executes as the querying role, so `authenticated` needs EXECUTE.
GRANT ALL ON FUNCTION public.has_permission(UUID, TEXT, TEXT) TO anon;
GRANT ALL ON FUNCTION public.has_permission(UUID, TEXT, TEXT) TO authenticated;
GRANT ALL ON FUNCTION public.has_permission(UUID, TEXT, TEXT) TO service_role;

-- ---------------------------------------------------------------------------
-- 2. Repoint the voice-agent write policies onto it.
--
-- Same organization scoping as before; the only change is that a non-admin role
-- holding voice_agents.write is now accepted by the database as well as by the API.
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS voice_agents_insert ON public.voice_agents;
CREATE POLICY voice_agents_insert ON public.voice_agents FOR INSERT WITH CHECK (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (SELECT public.has_permission(auth.uid(), 'voice_agents', 'write'))
);

DROP POLICY IF EXISTS voice_agents_update ON public.voice_agents;
CREATE POLICY voice_agents_update ON public.voice_agents FOR UPDATE
  USING (
    organization_id = (SELECT public.current_org_id(auth.uid()))
    AND (SELECT public.has_permission(auth.uid(), 'voice_agents', 'write'))
  )
  WITH CHECK (
    organization_id = (SELECT public.current_org_id(auth.uid()))
    AND (SELECT public.has_permission(auth.uid(), 'voice_agents', 'write'))
  );

DROP POLICY IF EXISTS voice_agents_delete ON public.voice_agents;
CREATE POLICY voice_agents_delete ON public.voice_agents FOR DELETE USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (SELECT public.has_permission(auth.uid(), 'voice_agents', 'write'))
);

DROP POLICY IF EXISTS phone_numbers_insert ON public.phone_numbers;
CREATE POLICY phone_numbers_insert ON public.phone_numbers FOR INSERT WITH CHECK (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (SELECT public.has_permission(auth.uid(), 'voice_agents', 'write'))
);

-- Added in 20260906020000 because its absence silently broke the assignment sync.
-- Keep it: repointing it must not accidentally drop it again.
DROP POLICY IF EXISTS phone_numbers_update ON public.phone_numbers;
CREATE POLICY phone_numbers_update ON public.phone_numbers FOR UPDATE
  USING (
    organization_id = (SELECT public.current_org_id(auth.uid()))
    AND (SELECT public.has_permission(auth.uid(), 'voice_agents', 'write'))
  )
  WITH CHECK (
    organization_id = (SELECT public.current_org_id(auth.uid()))
    AND (SELECT public.has_permission(auth.uid(), 'voice_agents', 'write'))
  );

DROP POLICY IF EXISTS phone_numbers_delete ON public.phone_numbers;
CREATE POLICY phone_numbers_delete ON public.phone_numbers FOR DELETE USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (SELECT public.has_permission(auth.uid(), 'voice_agents', 'write'))
);

DROP POLICY IF EXISTS voice_agent_documents_insert ON public.voice_agent_documents;
CREATE POLICY voice_agent_documents_insert ON public.voice_agent_documents FOR INSERT WITH CHECK (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (SELECT public.has_permission(auth.uid(), 'voice_agents', 'write'))
);

DROP POLICY IF EXISTS voice_agent_documents_delete ON public.voice_agent_documents;
CREATE POLICY voice_agent_documents_delete ON public.voice_agent_documents FOR DELETE USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (SELECT public.has_permission(auth.uid(), 'voice_agents', 'write'))
);

-- ---------------------------------------------------------------------------
-- 3. Knowledge-base indexing state on voice_agent_documents.
--
-- Deliberately no UPDATE policy: these columns are stamped only by the API's
-- service-role client after it indexes the file, never by a user session -- the
-- same writer model as `calls`. Adding an `authenticated` UPDATE policy here would
-- widen the surface for no caller.
-- ---------------------------------------------------------------------------
ALTER TABLE public.voice_agent_documents
  ADD COLUMN indexed_at TIMESTAMPTZ,
  ADD COLUMN chunk_count INTEGER,
  ADD COLUMN extracted_chars INTEGER,
  ADD COLUMN index_error TEXT;

COMMENT ON COLUMN public.voice_agent_documents.index_error IS
  'Why indexing failed. The upload still succeeds when indexing does not -- the file is stored '
  'and can be re-indexed by the worker; it is simply not searchable by the agent until then.';

-- The worker's reindex pass scans for documents that were never indexed. A partial index keeps
-- that scan from walking every document in every organization.
CREATE INDEX voice_agent_documents_unindexed_idx
  ON public.voice_agent_documents (created_at)
  WHERE indexed_at IS NULL;

-- ---------------------------------------------------------------------------
-- 4. AI call notes on `calls`.
--
-- These sit BESIDE the voice platform's own `summary`/`outcome`, never over them.
-- The platform's summary is a record of what its model said at the time; ours is a
-- derived artefact we can regenerate. Overwriting one with the other would destroy
-- the ability to tell them apart, or to re-run notes after a prompt change.
-- ---------------------------------------------------------------------------
ALTER TABLE public.calls
  ADD COLUMN ai_summary TEXT,
  ADD COLUMN ai_action_items JSONB NOT NULL DEFAULT '[]'::JSONB,
  ADD COLUMN ai_suggested_followup_date DATE,
  ADD COLUMN ai_sentiment TEXT,
  ADD COLUMN ai_notes_generated_at TIMESTAMPTZ,
  ADD COLUMN ai_notes_error TEXT;

ALTER TABLE public.calls
  ADD CONSTRAINT calls_ai_sentiment_check
  CHECK (ai_sentiment IS NULL OR ai_sentiment IN ('positive', 'neutral', 'negative'));

-- Drives the worker's call-notes pass: completed calls that have a transcript and have not been
-- analysed yet. Partial, so it stays small -- the steady state is zero rows.
CREATE INDEX calls_pending_ai_notes_idx
  ON public.calls (ended_at)
  WHERE ai_notes_generated_at IS NULL AND transcript IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 5. ai_usage -- per-organization token accounting.
--
-- One API key serves every tenant. Without attribution there is no way to answer
-- "which organization caused this bill", and no way to stop one of them consuming
-- the budget of all the others (see app/services/ai/budget.py).
-- ---------------------------------------------------------------------------
CREATE TABLE public.ai_usage (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  feature TEXT NOT NULL,
  model TEXT NOT NULL,
  prompt_tokens INTEGER NOT NULL DEFAULT 0,
  completion_tokens INTEGER NOT NULL DEFAULT 0,
  total_tokens INTEGER NOT NULL DEFAULT 0,
  cost_usd NUMERIC(12, 6) NOT NULL DEFAULT 0,
  --- Who triggered it, when a user did. NULL for scheduled work (call notes, deal health).
  user_id UUID REFERENCES public.users (id) ON DELETE SET NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- The budget check sums a month of rows for one organization on every AI request, so this
-- index is load-bearing, not housekeeping.
CREATE INDEX ai_usage_org_created_idx ON public.ai_usage (organization_id, created_at DESC);

-- ai_usage has no owning FK to derive an organization from -- `feature` and `model` are plain
-- text, not references -- so organization_id is supplied by the writer. That is the same shape
-- as `calls` and `roles`, and it gets the same guard: a service-role caller (no auth.uid()) has
-- already resolved the organization and is trusted to state it, but any real user session has
-- its own organization forced in regardless of what the payload claimed.
--
-- Today only service-role code writes here, so the auth.uid() branch is unreachable. It exists
-- so that stays true by construction rather than by everyone remembering: the day someone adds
-- an INSERT policy, a user still cannot bill their usage to another tenant.
CREATE OR REPLACE FUNCTION public.set_ai_usage_organization()
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
    RAISE EXCEPTION 'Cannot determine organization for this AI usage record'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER ai_usage_set_org BEFORE INSERT ON public.ai_usage
  FOR EACH ROW EXECUTE FUNCTION public.set_ai_usage_organization();

ALTER TABLE public.ai_usage ENABLE ROW LEVEL SECURITY;

-- Read-only for admins, and only within their own organization. No INSERT/UPDATE/DELETE policy
-- for `authenticated` at all: rows are written exclusively by service-role callers, matching
-- the `calls` and `audit_log` precedent. A user who could forge usage rows could exhaust
-- another tenant's budget.
CREATE POLICY ai_usage_select ON public.ai_usage FOR SELECT USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (SELECT public.has_permission(auth.uid(), 'ai', 'manage'))
);

-- ---------------------------------------------------------------------------
-- 6. deal_health_snapshots -- the nightly at-risk assessment.
-- ---------------------------------------------------------------------------
CREATE TABLE public.deal_health_snapshots (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  opportunity_id UUID NOT NULL REFERENCES public.opportunities (id) ON DELETE CASCADE,
  risk_level TEXT NOT NULL,
  reasons JSONB NOT NULL DEFAULT '[]'::JSONB,
  suggested_action TEXT,
  --- FALSE when the deterministic gate cleared the deal without a model call, so a reader can
  --- tell "nothing looked wrong" apart from "a model considered this and cleared it".
  assessed_by_model BOOLEAN NOT NULL DEFAULT FALSE,
  generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  --- The day this snapshot is for, as a real stored column rather than an expression over
  --- generated_at. Two reasons: `generated_at::DATE` is not immutable (it depends on TimeZone)
  --- so it cannot be a generated column, and PostgREST can only infer an upsert's conflict
  --- target from named columns -- an expression index is not addressable via `on_conflict`,
  --- which would leave the worker's re-run hitting a unique violation instead of updating.
  snapshot_date DATE NOT NULL DEFAULT CURRENT_DATE,
  CONSTRAINT deal_health_risk_level_check CHECK (risk_level IN ('low', 'medium', 'high'))
);

-- One snapshot per opportunity per day, so a re-run updates the day's row instead of stacking
-- duplicates. The worker addresses this with `on_conflict=opportunity_id,snapshot_date`.
CREATE UNIQUE INDEX deal_health_snapshots_daily_idx
  ON public.deal_health_snapshots (opportunity_id, snapshot_date);

CREATE INDEX deal_health_snapshots_org_idx
  ON public.deal_health_snapshots (organization_id, generated_at DESC);

CREATE TRIGGER deal_health_snapshots_set_org BEFORE INSERT ON public.deal_health_snapshots
  FOR EACH ROW EXECUTE FUNCTION public.set_parent_organization('opportunities', 'opportunity_id');

ALTER TABLE public.deal_health_snapshots ENABLE ROW LEVEL SECURITY;

-- Visible to whoever can see the opportunity itself. Reusing can_access_lead() through the
-- opportunity keeps this in step with opp_select rather than restating its ownership rule.
CREATE POLICY deal_health_snapshots_select ON public.deal_health_snapshots FOR SELECT USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND EXISTS (
    SELECT 1 FROM public.opportunities o
    WHERE o.id = deal_health_snapshots.opportunity_id
      AND o.deleted_at IS NULL
      AND (SELECT public.can_access_lead(auth.uid(), o.lead_id))
  )
);

-- ---------------------------------------------------------------------------
-- 7. AI-drafted proposals.
-- ---------------------------------------------------------------------------
ALTER TABLE public.proposals
  ADD COLUMN ai_generated BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN ai_draft_markdown TEXT;

COMMENT ON COLUMN public.proposals.ai_generated IS
  'TRUE when this version started as an AI draft. It stays TRUE after editing -- it records '
  'provenance, not current authorship.';

-- ---------------------------------------------------------------------------
-- 8. Permissions catalog + role grants.
-- ---------------------------------------------------------------------------
INSERT INTO public.permissions (resource, action, description) VALUES
  ('ai', 'read', 'Ask the CRM assistant about records they can already see (it only reads)'),
  ('ai', 'manage', 'View the organization''s AI usage and cost -- admin only');

-- Admin picks both up from seed_default_roles()'s blanket `SELECT id FROM permissions`.
-- Redefine the function only to add ai.read to the Agent/SDR allow-list: the assistant reads
-- through the caller's own RLS-scoped connection, so it can never show a rep more than the
-- CRM already shows them. ai.manage stays admin-only because it exposes spend. (The action is `read`, not a new
-- `use` value: permission_action is an enum, and ALTER TYPE ... ADD VALUE cannot be used in
-- the same transaction that adds it.)
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
    ('voice_agents', 'read'),
    ('ai', 'read')
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

-- Backfill: seed_default_roles() only runs for organizations created from here on, so existing
-- Agent/SDR roles need ai.read granted explicitly. Same shape as the voice_agents.read backfill
-- in 20260906000000.
DO $$
DECLARE
  ai_read_id UUID;
BEGIN
  SELECT id INTO ai_read_id FROM public.permissions
    WHERE resource = 'ai' AND action = 'read';

  INSERT INTO public.role_permissions (role_id, permission_id)
  SELECT r.id, ai_read_id
  FROM public.roles r
  WHERE r.is_system AND r.name IN ('Agent', 'SDR')
  ON CONFLICT DO NOTHING;

  -- Full-access roles pass has_permission() without a grant, but seed_default_roles() gives
  -- Admin every catalog row explicitly, so keep existing Admin roles consistent with new ones.
  INSERT INTO public.role_permissions (role_id, permission_id)
  SELECT r.id, p.id
  FROM public.roles r
  CROSS JOIN public.permissions p
  WHERE r.grants_full_access AND p.resource = 'ai'
  ON CONFLICT DO NOTHING;
END;
$$;
