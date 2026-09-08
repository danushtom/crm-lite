-- Separate a proposal's document version number from its optimistic-concurrency counter.
--
-- `proposals.version` was doing both jobs at once. It is the user-facing version number --
-- "Proposal v2" -- allocated by next_version() when a version is created, and constrained
-- UNIQUE (opportunity_id, version). But the proposals_version trigger also ran bump_version()
-- on it, which increments `version` on every UPDATE.
--
-- So editing a proposal renumbered it. Retitle "Proposal v1" and it silently becomes v2; if a
-- real v2 already existed the write failed against the unique constraint instead, and marking
-- a proposal sent (an UPDATE) did the same. Either way the version history -- the thing this
-- table exists to keep -- could not be trusted.
--
-- The fix is a separate `row_version` column for concurrency, leaving `version` to mean only
-- what the UI says it means.

-- 1. The concurrency counter, as its own column.
ALTER TABLE public.proposals
    ADD COLUMN IF NOT EXISTS row_version integer NOT NULL DEFAULT 1;

COMMENT ON COLUMN public.proposals.row_version IS
    'Optimistic-concurrency counter, returned as an ETag and checked via If-Match. Distinct from `version`, which is the proposal document number shown to users (v1, v2, ...).';

COMMENT ON COLUMN public.proposals.version IS
    'User-facing proposal version number within an opportunity, allocated on create. Never bumped by an update -- see row_version.';

-- 2. bump_version() writes NEW.version, which is the wrong column for this table.
DROP TRIGGER IF EXISTS proposals_version ON public.proposals;

CREATE OR REPLACE FUNCTION public.bump_proposal_row_version() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'public'
    AS $$
BEGIN
  -- Same shape as bump_version(), but excluding and writing row_version instead of version,
  -- so a proposal's document number is left exactly as the caller set it.
  IF (to_jsonb(NEW) - 'updated_at' - 'row_version')
     IS DISTINCT FROM
     (to_jsonb(OLD) - 'updated_at' - 'row_version')
  THEN
    NEW.row_version = COALESCE(OLD.row_version, 0) + 1;
  ELSE
    NEW.row_version = OLD.row_version;
    NEW.updated_at = OLD.updated_at;
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER proposals_row_version BEFORE UPDATE ON public.proposals
    FOR EACH ROW EXECUTE FUNCTION public.bump_proposal_row_version();

-- 3. Repair rows whose document number was already inflated by an edit.
--
-- The original number is unrecoverable -- the increments left no trace -- so renumber each
-- opportunity's proposals from 1 in creation order, which is what the numbers were always
-- meant to represent. Done in two passes because the target values collide with the current
-- ones under the UNIQUE constraint.
DO $$
DECLARE
    affected integer;
BEGIN
    WITH renumbered AS (
        SELECT id,
               row_number() OVER (PARTITION BY opportunity_id ORDER BY created_at, id) AS correct_version,
               version AS current_version
        FROM public.proposals
    )
    SELECT count(*) INTO affected
    FROM renumbered
    WHERE correct_version <> current_version;

    IF affected = 0 THEN
        RAISE NOTICE 'proposals: no version numbers needed repair';
        RETURN;
    END IF;

    RAISE NOTICE 'proposals: repairing % inflated version number(s)', affected;

    -- Park every row in a range nothing can collide with, then write the real numbers.
    UPDATE public.proposals SET version = version + 1000000;

    WITH renumbered AS (
        SELECT id,
               row_number() OVER (PARTITION BY opportunity_id ORDER BY created_at, id) AS correct_version
        FROM public.proposals
    )
    UPDATE public.proposals p
    SET version = r.correct_version
    FROM renumbered r
    WHERE p.id = r.id;
END $$;
