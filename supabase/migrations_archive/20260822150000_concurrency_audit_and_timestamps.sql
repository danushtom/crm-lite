-- Integrity layer: optimistic concurrency, complete timestamps, and a real audit trail.
--
-- Addresses three review findings:
--   * every write was last-write-wins, with no way for a client to detect a lost update;
--   * updated_at existed on only three of ten tables, so "when did this last change" was
--     unanswerable for contacts, companies, tasks, meetings and proposals;
--   * activities recorded stage changes and nothing else, despite the product promising a
--     full audit trail -- and its performed_by column is NOT NULL, which forces system
--     actions to be attributed to a person.

-- ---------------------------------------------------------------------------
-- 1. updated_at everywhere, maintained by trigger.
-- ---------------------------------------------------------------------------
ALTER TABLE public.companies  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE public.contacts   ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE public.tasks      ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE public.meetings   ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE public.proposals  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

-- touch_updated_at() predates this migration and had no search_path pin.
CREATE OR REPLACE FUNCTION public.touch_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS companies_touch ON public.companies;
CREATE TRIGGER companies_touch BEFORE UPDATE ON public.companies
  FOR EACH ROW EXECUTE FUNCTION public.touch_updated_at();

DROP TRIGGER IF EXISTS contacts_touch ON public.contacts;
CREATE TRIGGER contacts_touch BEFORE UPDATE ON public.contacts
  FOR EACH ROW EXECUTE FUNCTION public.touch_updated_at();

DROP TRIGGER IF EXISTS tasks_touch ON public.tasks;
CREATE TRIGGER tasks_touch BEFORE UPDATE ON public.tasks
  FOR EACH ROW EXECUTE FUNCTION public.touch_updated_at();

DROP TRIGGER IF EXISTS meetings_touch ON public.meetings;
CREATE TRIGGER meetings_touch BEFORE UPDATE ON public.meetings
  FOR EACH ROW EXECUTE FUNCTION public.touch_updated_at();

DROP TRIGGER IF EXISTS proposals_touch ON public.proposals;
CREATE TRIGGER proposals_touch BEFORE UPDATE ON public.proposals
  FOR EACH ROW EXECUTE FUNCTION public.touch_updated_at();

-- ---------------------------------------------------------------------------
-- 2. Optimistic concurrency.
--
-- Two agents editing the same lead previously produced a silent overwrite: read-modify-write
-- with no detection. Each row now carries a monotonic version the API surfaces as an ETag and
-- requires back via If-Match, answering 412 when it has moved on.
--
-- A counter rather than updated_at: timestamps can collide within a transaction, and a client
-- comparing them has to reason about clock precision.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.bump_version()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
  -- Only advance when the row's data actually changed, so a no-op UPDATE does not
  -- invalidate a client's ETag.
  IF NEW IS DISTINCT FROM OLD THEN
    NEW.version = COALESCE(OLD.version, 0) + 1;
  END IF;
  RETURN NEW;
END;
$$;

DO $$
DECLARE
  t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'leads', 'opportunities', 'contacts', 'companies',
    'tasks', 'meetings', 'proposals', 'lead_intelligence'
  ]
  LOOP
    EXECUTE format(
      'ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1', t
    );
    EXECUTE format('DROP TRIGGER IF EXISTS %I ON public.%I', t || '_version', t);
    EXECUTE format(
      'CREATE TRIGGER %I BEFORE UPDATE ON public.%I
         FOR EACH ROW EXECUTE FUNCTION public.bump_version()',
      t || '_version', t
    );
  END LOOP;
END;
$$;

-- ---------------------------------------------------------------------------
-- 3. System actors.
--
-- activities.performed_by was NOT NULL referencing users, so a stage change made by the
-- Celery worker (which has no auth.uid()) had to be attributed to a human. An earlier fix
-- substituted the record owner, which stopped the crash but put a false name in the audit
-- trail. The column is now nullable and paired with an explicit actor type.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
  CREATE TYPE public.actor_type AS ENUM ('user', 'system');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END;
$$;

ALTER TABLE public.activities ALTER COLUMN performed_by DROP NOT NULL;
ALTER TABLE public.activities
  ADD COLUMN IF NOT EXISTS actor_type public.actor_type NOT NULL DEFAULT 'user';

-- Rows the previous fix attributed to the record owner are indistinguishable from genuine
-- user actions only by their metadata; relabel those.
UPDATE public.activities
SET actor_type = 'system'
WHERE metadata ? 'actor' AND metadata->>'actor' = 'system';

CREATE OR REPLACE FUNCTION public.log_opportunity_stage_change()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  actor uuid := auth.uid();
BEGIN
  IF TG_OP = 'UPDATE' AND OLD.stage IS DISTINCT FROM NEW.stage THEN
    INSERT INTO public.activities (
      lead_id, type, description, performed_by, actor_type, metadata
    )
    VALUES (
      NEW.lead_id,
      'stage_change'::public.activity_type,
      'Opportunity stage changed from ' || OLD.stage::TEXT || ' to ' || NEW.stage::TEXT,
      actor,
      CASE WHEN actor IS NULL THEN 'system' ELSE 'user' END::public.actor_type,
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

-- activities_insert required performed_by = auth.uid(), which now has to tolerate NULL for
-- system rows. Those are only ever written by SECURITY DEFINER triggers, never by a client.
DROP POLICY IF EXISTS activities_insert ON public.activities;
CREATE POLICY activities_insert ON public.activities FOR INSERT WITH CHECK (
  (SELECT public.can_access_lead(auth.uid(), activities.lead_id))
  AND performed_by = (SELECT auth.uid())
);

-- ---------------------------------------------------------------------------
-- 4. Audit trail.
--
-- The product promises a full audit trail; activities only ever recorded stage changes, so
-- changing a deal's value, reassigning an owner or editing CRM intelligence left no record.
-- A generic trigger captures the changed columns for every table it is attached to, which
-- means coverage does not depend on application code remembering to log.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.audit_log (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  table_name TEXT NOT NULL,
  record_id UUID NOT NULL,
  action TEXT NOT NULL CHECK (action IN ('INSERT', 'UPDATE', 'DELETE')),
  actor_id UUID REFERENCES public.users (id) ON DELETE SET NULL,
  actor_type public.actor_type NOT NULL DEFAULT 'user',
  changed_columns TEXT[] NOT NULL DEFAULT '{}',
  old_values JSONB,
  new_values JSONB,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX audit_log_record_idx ON public.audit_log (table_name, record_id, occurred_at DESC);
CREATE INDEX audit_log_actor_idx ON public.audit_log (actor_id, occurred_at DESC);

ALTER TABLE public.audit_log ENABLE ROW LEVEL SECURITY;

-- Audit history is an admin concern; agents see their own actions.
CREATE POLICY audit_log_select ON public.audit_log FOR SELECT USING (
  actor_id = (SELECT auth.uid()) OR (SELECT public.is_admin(auth.uid()))
);

-- Deliberately no INSERT/UPDATE/DELETE policies: rows arrive only through the SECURITY
-- DEFINER trigger below, and an append-only log nobody can rewrite is the point.

CREATE OR REPLACE FUNCTION public.write_audit_log()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  actor uuid := auth.uid();
  old_json JSONB;
  new_json JSONB;
  changed TEXT[];
  record_id UUID;
BEGIN
  IF TG_OP = 'DELETE' THEN
    old_json := to_jsonb(OLD);
    record_id := OLD.id;
  ELSIF TG_OP = 'INSERT' THEN
    new_json := to_jsonb(NEW);
    record_id := NEW.id;
  ELSE
    old_json := to_jsonb(OLD);
    new_json := to_jsonb(NEW);
    record_id := NEW.id;

    SELECT COALESCE(array_agg(key ORDER BY key), '{}')
      INTO changed
    FROM jsonb_each(new_json) AS n(key, value)
    WHERE n.value IS DISTINCT FROM old_json -> n.key
      -- Bookkeeping columns change on every write and would drown the diff.
      AND n.key NOT IN ('updated_at', 'version');

    -- Nothing of substance moved; do not record a row.
    IF changed = '{}' THEN
      RETURN NULL;
    END IF;

    -- Store only the columns that changed, not a full copy of the row each time.
    old_json := (SELECT jsonb_object_agg(k, old_json -> k) FROM unnest(changed) AS k);
    new_json := (SELECT jsonb_object_agg(k, new_json -> k) FROM unnest(changed) AS k);
  END IF;

  INSERT INTO public.audit_log (
    table_name, record_id, action, actor_id, actor_type,
    changed_columns, old_values, new_values
  )
  VALUES (
    TG_TABLE_NAME,
    record_id,
    TG_OP,
    actor,
    CASE WHEN actor IS NULL THEN 'system' ELSE 'user' END::public.actor_type,
    COALESCE(changed, '{}'),
    old_json,
    new_json
  );

  RETURN NULL;  -- AFTER trigger; return value is ignored.
END;
$$;

DO $$
DECLARE
  t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'leads', 'opportunities', 'contacts', 'companies', 'proposals', 'lead_intelligence'
  ]
  LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS %I ON public.%I', t || '_audit', t);
    EXECUTE format(
      'CREATE TRIGGER %I AFTER INSERT OR UPDATE OR DELETE ON public.%I
         FOR EACH ROW EXECUTE FUNCTION public.write_audit_log()',
      t || '_audit', t
    );
  END LOOP;
END;
$$;

COMMENT ON TABLE public.audit_log IS
  'Append-only change history written by trigger. No write policies exist: rows arrive only '
  'via write_audit_log(), so the log cannot be edited through the API.';
