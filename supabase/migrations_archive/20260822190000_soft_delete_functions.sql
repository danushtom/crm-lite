-- Soft delete has to go through a function, not a PATCH.
--
-- The SELECT policies hide rows with deleted_at set. PostgREST builds every write as
--
--     WITH pgrst_update AS (UPDATE ... RETURNING 1) SELECT count(*) FROM pgrst_update
--
-- so a RETURNING clause is always present, even for Prefer: return=minimal. Row-level
-- security applies the SELECT policy to that returned row -- and the row a soft delete
-- produces is, by construction, one the policy now hides. The write therefore fails with
-- 42501 "new row violates row-level security policy" no matter who the caller is.
--
-- Filtering deletion in RLS and writing through PostgREST are simply incompatible. Rather
-- than drop the filter and rely on every query remembering `deleted_at is null` -- exactly
-- the kind of thing RLS exists to stop being optional -- deletion becomes an explicit
-- operation with its permission check written out.

CREATE OR REPLACE FUNCTION public.soft_delete_lead(
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
  target public.leads%ROWTYPE;
BEGIN
  IF uid IS NULL THEN
    RAISE EXCEPTION 'not authenticated' USING ERRCODE = '42501';
  END IF;

  SELECT * INTO target FROM public.leads WHERE id = p_id;

  IF NOT FOUND OR target.deleted_at IS NOT NULL THEN
    RETURN jsonb_build_object('status', 'not_found');
  END IF;

  -- The same rule leads_update enforces, written explicitly because this function runs as
  -- its definer and therefore bypasses the policy.
  IF NOT (target.owner_id = uid OR public.is_admin(uid)) THEN
    RETURN jsonb_build_object('status', 'forbidden');
  END IF;

  IF p_expected_version IS NOT NULL AND target.version <> p_expected_version THEN
    RETURN jsonb_build_object(
      'status', 'version_mismatch',
      'current_version', target.version
    );
  END IF;

  UPDATE public.leads SET deleted_at = NOW() WHERE id = p_id;
  RETURN jsonb_build_object('status', 'deleted');
END;
$$;

CREATE OR REPLACE FUNCTION public.soft_delete_contact(
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
  target public.contacts%ROWTYPE;
  permitted BOOLEAN;
BEGIN
  IF uid IS NULL THEN
    RAISE EXCEPTION 'not authenticated' USING ERRCODE = '42501';
  END IF;

  SELECT * INTO target FROM public.contacts WHERE id = p_id;

  IF NOT FOUND OR target.deleted_at IS NOT NULL THEN
    RETURN jsonb_build_object('status', 'not_found');
  END IF;

  -- Mirrors contacts_delete.
  SELECT public.is_admin(uid) OR EXISTS (
    SELECT 1 FROM public.companies c
    WHERE c.id = target.company_id AND c.created_by = uid
  ) INTO permitted;

  IF NOT permitted THEN
    RETURN jsonb_build_object('status', 'forbidden');
  END IF;

  IF EXISTS (
    SELECT 1 FROM public.leads l
    WHERE l.primary_contact_id = p_id AND l.deleted_at IS NULL
  ) THEN
    RETURN jsonb_build_object('status', 'referenced');
  END IF;

  IF p_expected_version IS NOT NULL AND target.version <> p_expected_version THEN
    RETURN jsonb_build_object(
      'status', 'version_mismatch',
      'current_version', target.version
    );
  END IF;

  UPDATE public.contacts SET deleted_at = NOW() WHERE id = p_id;
  RETURN jsonb_build_object('status', 'deleted');
END;
$$;

GRANT EXECUTE ON FUNCTION public.soft_delete_lead(UUID, INTEGER) TO authenticated;
GRANT EXECUTE ON FUNCTION public.soft_delete_contact(UUID, INTEGER) TO authenticated;

COMMENT ON FUNCTION public.soft_delete_lead IS
  'Marks a lead deleted. SECURITY DEFINER because the resulting row is hidden by the SELECT '
  'policy, which PostgREST cannot satisfy; the ownership check is therefore explicit here.';
