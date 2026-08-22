-- Follow-up scheduling was timezone-blind.
--
-- tasks stored due_date DATE and due_time TIME as separate, zoneless columns, and the API
-- decided what was "due today" or "overdue" by comparing them to date.today() on the *server*.
-- With agents in IST and a server in UTC, those two disagree for five and a half hours every
-- day: a task due today reads as overdue, and the daily queue rolls over at 05:30 local. For
-- a product whose headline feature is a follow-up engine, that is the wrong thing to get
-- wrong.
--
-- due_at TIMESTAMPTZ becomes the single source of truth, and each user carries the timezone
-- their day boundaries are computed in. The old columns are dropped rather than kept in sync:
-- two representations of the same fact is the problem, not the fix.

-- ---------------------------------------------------------------------------
-- 1. Per-user timezone.
-- ---------------------------------------------------------------------------
ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata';

-- Reject anything Postgres cannot actually resolve, so a bad value fails on write rather
-- than silently shifting somebody's queue later. This has to be a trigger, not a CHECK:
-- validating against pg_timezone_names needs a subquery, and CHECK constraints cannot
-- contain one (the catalogue is also not immutable, so it could not be indexed anyway).
ALTER TABLE public.users DROP CONSTRAINT IF EXISTS users_timezone_valid;

CREATE OR REPLACE FUNCTION public.validate_user_timezone()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
  IF NEW.timezone IS NULL OR NOT EXISTS (
    SELECT 1 FROM pg_timezone_names WHERE name = NEW.timezone
  ) THEN
    RAISE EXCEPTION 'Unknown IANA timezone: %', NEW.timezone
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS users_timezone_check ON public.users;
CREATE TRIGGER users_timezone_check
  BEFORE INSERT OR UPDATE OF timezone ON public.users
  FOR EACH ROW EXECUTE FUNCTION public.validate_user_timezone();

COMMENT ON COLUMN public.users.timezone IS
  'IANA zone used to derive this user''s day boundaries for follow-up queues.';

-- ---------------------------------------------------------------------------
-- 2. tasks.due_at
-- ---------------------------------------------------------------------------
ALTER TABLE public.tasks ADD COLUMN IF NOT EXISTS due_at TIMESTAMPTZ;

-- Backfill in the owner's zone. A task with no due_time was implicitly "sometime that day";
-- 09:00 local is the least surprising interpretation for a follow-up reminder.
UPDATE public.tasks t
SET due_at = (
  (t.due_date + COALESCE(t.due_time, TIME '09:00')) AT TIME ZONE COALESCE(u.timezone, 'Asia/Kolkata')
)
FROM public.users u
WHERE u.id = t.owner_id
  AND t.due_at IS NULL;

-- Any task whose owner has since been removed.
UPDATE public.tasks
SET due_at = ((due_date + COALESCE(due_time, TIME '09:00')) AT TIME ZONE 'Asia/Kolkata')
WHERE due_at IS NULL;

ALTER TABLE public.tasks ALTER COLUMN due_at SET NOT NULL;

DROP INDEX IF EXISTS tasks_owner_due_idx;
DROP INDEX IF EXISTS tasks_status_due_idx;
DROP INDEX IF EXISTS tasks_pending_due_partial_idx;

CREATE INDEX tasks_owner_due_at_idx ON public.tasks (owner_id, due_at);
CREATE INDEX tasks_status_due_at_idx ON public.tasks (status, due_at);
CREATE INDEX tasks_pending_due_at_idx ON public.tasks (due_at)
  WHERE status = 'pending'::public.task_status;

ALTER TABLE public.tasks DROP COLUMN IF EXISTS due_date;
ALTER TABLE public.tasks DROP COLUMN IF EXISTS due_time;

COMMENT ON COLUMN public.tasks.due_at IS
  'When the follow-up is due, as an absolute instant. Render it in the owner''s timezone.';

-- ---------------------------------------------------------------------------
-- 3. snoozed_until follows the same reasoning.
-- ---------------------------------------------------------------------------
ALTER TABLE public.tasks ADD COLUMN IF NOT EXISTS snoozed_to TIMESTAMPTZ;

UPDATE public.tasks t
SET snoozed_to = (t.snoozed_until + TIME '09:00') AT TIME ZONE COALESCE(u.timezone, 'Asia/Kolkata')
FROM public.users u
WHERE u.id = t.owner_id
  AND t.snoozed_until IS NOT NULL
  AND t.snoozed_to IS NULL;

ALTER TABLE public.tasks DROP COLUMN IF EXISTS snoozed_until;
