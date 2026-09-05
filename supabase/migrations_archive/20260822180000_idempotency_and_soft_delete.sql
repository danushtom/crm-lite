-- Two more review findings: retried creates duplicated records, and deletes were permanent
-- and cascaded hard.

-- ---------------------------------------------------------------------------
-- 1. Idempotency keys.
--
-- A POST retried after a timeout -- a flaky connection, a client-side retry, an impatient
-- double click -- created a second lead. There was no way for the server to tell a retry
-- from a genuine second request.
--
-- Clients now send Idempotency-Key on creates; the first response is recorded against that
-- key and replayed for any repeat. The request body is fingerprinted too, so reusing a key
-- with different content is reported rather than silently returning the wrong response.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.idempotency_keys (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  -- Hash of the caller's bearer token rather than a user id: the key is recorded before
  -- authentication has necessarily resolved a profile, and raw credentials must never be stored.
  caller_hash TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  endpoint TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  status_code INTEGER NOT NULL,
  response_body JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (caller_hash, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idempotency_keys_created_idx
  ON public.idempotency_keys (created_at);

ALTER TABLE public.idempotency_keys ENABLE ROW LEVEL SECURITY;

-- No policies at all: this table is written and read exclusively by the API using the
-- service role. Nothing reaches it through a user's token.

COMMENT ON TABLE public.idempotency_keys IS
  'Replay cache for POST requests carrying Idempotency-Key. Service-role access only; '
  'prune rows older than 24 hours.';

CREATE OR REPLACE FUNCTION public.prune_idempotency_keys(older_than INTERVAL DEFAULT '24 hours')
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  removed INTEGER;
BEGIN
  DELETE FROM public.idempotency_keys WHERE created_at < NOW() - older_than;
  GET DIAGNOSTICS removed = ROW_COUNT;
  RETURN removed;
END;
$$;

-- ---------------------------------------------------------------------------
-- 2. Soft delete.
--
-- Deleting a lead cascaded to its activities, tasks, meetings, opportunities and every
-- proposal version. One misclick erased a deal's entire commercial history, with no
-- retention and no undo.
--
-- Core records now carry deleted_at. The SELECT policies exclude soft-deleted rows, so
-- every existing query hides them without any change to the application, while the rows
-- remain for recovery and audit. Hard DELETE still works for a genuine purge.
-- ---------------------------------------------------------------------------
ALTER TABLE public.leads         ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE public.opportunities ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE public.contacts      ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE public.companies     ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS leads_live_idx ON public.leads (updated_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS opportunities_live_idx ON public.opportunities (updated_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS contacts_live_idx ON public.contacts (company_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS companies_live_idx ON public.companies (created_at DESC) WHERE deleted_at IS NULL;

-- can_access_lead underpins the policies on activities, opportunities, intelligence and
-- proposals; teaching it about deletion hides a deleted lead's whole subtree at once.
CREATE OR REPLACE FUNCTION public.can_access_lead(uid UUID, lid UUID)
RETURNS BOOLEAN
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.leads l
    WHERE l.id = lid
      AND l.deleted_at IS NULL
      AND (l.owner_id = uid OR public.is_admin(uid))
  )
$$;

DROP POLICY IF EXISTS leads_select ON public.leads;
CREATE POLICY leads_select ON public.leads FOR SELECT USING (
  deleted_at IS NULL
  AND (owner_id = (SELECT auth.uid()) OR (SELECT public.is_admin(auth.uid())))
);

DROP POLICY IF EXISTS opp_select ON public.opportunities;
CREATE POLICY opp_select ON public.opportunities FOR SELECT USING (
  deleted_at IS NULL
  AND (SELECT public.can_access_lead(auth.uid(), opportunities.lead_id))
);

DROP POLICY IF EXISTS contacts_select ON public.contacts;
CREATE POLICY contacts_select ON public.contacts FOR SELECT USING (
  deleted_at IS NULL
  AND (
    (SELECT public.is_admin(auth.uid()))
    OR EXISTS (
      SELECT 1 FROM public.companies c
      WHERE c.id = contacts.company_id AND c.created_by = (SELECT auth.uid())
    )
    OR EXISTS (
      SELECT 1 FROM public.leads l
      WHERE l.company_id = contacts.company_id
        AND (SELECT public.can_access_lead(auth.uid(), l.id))
    )
  )
);

DROP POLICY IF EXISTS companies_select ON public.companies;
CREATE POLICY companies_select ON public.companies FOR SELECT USING (
  deleted_at IS NULL
  AND (
    created_by = (SELECT auth.uid())
    OR (SELECT public.is_admin(auth.uid()))
    OR EXISTS (
      SELECT 1 FROM public.leads l
      WHERE l.company_id = companies.id
        AND (SELECT public.can_access_lead(auth.uid(), l.id))
    )
  )
);

COMMENT ON COLUMN public.leads.deleted_at IS
  'Soft delete. SELECT policies hide these rows; the data is retained for recovery and audit.';
