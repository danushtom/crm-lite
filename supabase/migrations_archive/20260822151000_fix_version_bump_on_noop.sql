-- bump_version() compared NEW to OLD directly, but touch_updated_at() is a BEFORE UPDATE
-- trigger too and sorts earlier by name, so it had already stamped NEW.updated_at = NOW()
-- by the time this ran. NEW was therefore always distinct from OLD and the version advanced
-- on every UPDATE, including ones that changed nothing -- invalidating a client's ETag for
-- no reason and defeating the point of the check.
--
-- Compare the rows with the bookkeeping columns removed. When nothing of substance moved,
-- hold both version and updated_at steady so a no-op write is genuinely a no-op.

CREATE OR REPLACE FUNCTION public.bump_version()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
  IF (to_jsonb(NEW) - 'updated_at' - 'version')
     IS DISTINCT FROM
     (to_jsonb(OLD) - 'updated_at' - 'version')
  THEN
    NEW.version = COALESCE(OLD.version, 0) + 1;
  ELSE
    NEW.version = OLD.version;
    NEW.updated_at = OLD.updated_at;
  END IF;
  RETURN NEW;
END;
$$;

-- Ensure the version trigger runs after the timestamp trigger on every table that has both.
-- Postgres fires BEFORE triggers in name order, and "_version" already sorts after "_touch";
-- this comment records the dependency so a future rename does not silently break it.
