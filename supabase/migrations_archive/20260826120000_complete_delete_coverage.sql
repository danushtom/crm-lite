-- Deletion was only ever implemented for contacts and leads.
--
-- Everything else had no DELETE policy at all, which means a delete through PostgREST would
-- have removed zero rows and reported success -- the silent no-op this codebase has already
-- been bitten by once. Rather than leave those endpoints unbuilt and the policies absent,
-- both are added together, with the destructiveness matched to what the record is.
--
--   companies, opportunities  soft -- commercial history, recoverable
--   tasks, meetings           hard -- operational records; losing one costs nothing
--   notifications             hard -- an inbox item the user dismissed
--   proposals                 hard, drafts only -- a sent proposal is part of the deal record
--
-- activities deliberately gets nothing. The timeline is append-only; an audit trail you can
-- edit is not an audit trail.

-- ---------------------------------------------------------------------------
-- 1. Soft delete for the two that carry commercial history.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.soft_delete_company(
  p_id UUID,
  p_expected_version INTEGER DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  uid UUID := auth.uid();
  target public.companies%ROWTYPE;
BEGIN
  IF uid IS NULL THEN
    RAISE EXCEPTION 'not authenticated' USING ERRCODE = '42501';
  END IF;

  SELECT * INTO target FROM public.companies WHERE id = p_id;
  IF NOT FOUND OR target.deleted_at IS NOT NULL THEN
    RETURN jsonb_build_object('status', 'not_found');
  END IF;

  IF NOT (target.created_by = uid OR public.is_admin(uid)) THEN
    RETURN jsonb_build_object('status', 'forbidden');
  END IF;

  -- A company with live leads is still in play; removing it would strand them.
  IF EXISTS (
    SELECT 1 FROM public.leads l WHERE l.company_id = p_id AND l.deleted_at IS NULL
  ) THEN
    RETURN jsonb_build_object('status', 'referenced');
  END IF;

  IF p_expected_version IS NOT NULL AND target.version <> p_expected_version THEN
    RETURN jsonb_build_object('status', 'version_mismatch', 'current_version', target.version);
  END IF;

  UPDATE public.companies SET deleted_at = NOW() WHERE id = p_id;
  RETURN jsonb_build_object('status', 'deleted');
END;
$$;

CREATE OR REPLACE FUNCTION public.soft_delete_opportunity(
  p_id UUID,
  p_expected_version INTEGER DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  uid UUID := auth.uid();
  target public.opportunities%ROWTYPE;
BEGIN
  IF uid IS NULL THEN
    RAISE EXCEPTION 'not authenticated' USING ERRCODE = '42501';
  END IF;

  SELECT * INTO target FROM public.opportunities WHERE id = p_id;
  IF NOT FOUND OR target.deleted_at IS NOT NULL THEN
    RETURN jsonb_build_object('status', 'not_found');
  END IF;

  IF NOT public.can_access_lead(uid, target.lead_id) THEN
    RETURN jsonb_build_object('status', 'forbidden');
  END IF;

  IF p_expected_version IS NOT NULL AND target.version <> p_expected_version THEN
    RETURN jsonb_build_object('status', 'version_mismatch', 'current_version', target.version);
  END IF;

  UPDATE public.opportunities SET deleted_at = NOW() WHERE id = p_id;
  RETURN jsonb_build_object('status', 'deleted');
END;
$$;

GRANT EXECUTE ON FUNCTION public.soft_delete_company(UUID, INTEGER) TO authenticated;
GRANT EXECUTE ON FUNCTION public.soft_delete_opportunity(UUID, INTEGER) TO authenticated;

-- ---------------------------------------------------------------------------
-- 2. Hard delete policies for the operational records.
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS tasks_delete ON public.tasks;
CREATE POLICY tasks_delete ON public.tasks FOR DELETE USING (
  owner_id = (SELECT auth.uid()) OR (SELECT public.is_admin(auth.uid()))
);

DROP POLICY IF EXISTS meetings_delete ON public.meetings;
CREATE POLICY meetings_delete ON public.meetings FOR DELETE USING (
  owner_id = (SELECT auth.uid()) OR (SELECT public.is_admin(auth.uid()))
);

DROP POLICY IF EXISTS notifications_delete_own ON public.notifications;
CREATE POLICY notifications_delete_own ON public.notifications FOR DELETE USING (
  user_id = (SELECT auth.uid())
);

-- Only a draft may be removed. Once a proposal has been sent it is part of what happened on
-- the deal, and deleting it would leave the version history with a hole in it.
DROP POLICY IF EXISTS prop_delete ON public.proposals;
CREATE POLICY prop_delete ON public.proposals FOR DELETE USING (
  status = 'draft'::public.proposal_status
  AND EXISTS (
    SELECT 1 FROM public.opportunities o
    WHERE o.id = proposals.opportunity_id
      AND (SELECT public.can_access_lead(auth.uid(), o.lead_id))
  )
);

-- ---------------------------------------------------------------------------
-- 3. Agents: admins could invite people but never change or revoke them.
--
-- users_update_self allowed a user to edit their own row and nothing else, so there was no
-- way to promote an agent, correct a name, or switch off access for someone who had left --
-- short of editing the table by hand. Note the self-update policy deliberately does not let
-- a user change their own role.
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS users_update_self ON public.users;
CREATE POLICY users_update_self ON public.users FOR UPDATE
  USING (id = (SELECT auth.uid()))
  WITH CHECK (id = (SELECT auth.uid()));

DROP POLICY IF EXISTS users_update_admin ON public.users;
CREATE POLICY users_update_admin ON public.users FOR UPDATE
  USING ((SELECT public.is_admin(auth.uid())))
  WITH CHECK ((SELECT public.is_admin(auth.uid())));

CREATE OR REPLACE FUNCTION public.guard_role_escalation()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  -- Row-level security cannot express "you may edit this row but not this column", so the
  -- restriction that a non-admin cannot change their own role lives here.
  IF NEW.role IS DISTINCT FROM OLD.role AND NOT public.is_admin(auth.uid()) THEN
    RAISE EXCEPTION 'Only an admin may change a role' USING ERRCODE = '42501';
  END IF;

  -- An organisation that can lock itself out of administration is a support ticket.
  IF OLD.role = 'admin' AND NEW.role <> 'admin' THEN
    IF (SELECT COUNT(*) FROM public.users WHERE role = 'admin' AND is_active) <= 1 THEN
      RAISE EXCEPTION 'Cannot remove the last active admin' USING ERRCODE = 'check_violation';
    END IF;
  END IF;

  IF OLD.is_active AND NOT NEW.is_active AND OLD.role = 'admin' THEN
    IF (SELECT COUNT(*) FROM public.users WHERE role = 'admin' AND is_active) <= 1 THEN
      RAISE EXCEPTION 'Cannot deactivate the last active admin' USING ERRCODE = 'check_violation';
    END IF;
  END IF;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS users_guard_role ON public.users;
CREATE TRIGGER users_guard_role
  BEFORE UPDATE ON public.users
  FOR EACH ROW EXECUTE FUNCTION public.guard_role_escalation();

COMMENT ON POLICY prop_delete ON public.proposals IS
  'Drafts only. A sent proposal is part of the deal record.';
