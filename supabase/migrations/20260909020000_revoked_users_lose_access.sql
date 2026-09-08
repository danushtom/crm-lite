-- Make `users.is_active = false` actually revoke access.
--
-- It did not. The User management screen offers "Access revoked" and tells the admin "they
-- keep everything they own; only their access is revoked", but nothing enforced it:
--
--   * current_org_id(uid) returned the organization for any user row, active or not, so every
--     `organization_id = current_org_id(auth.uid())` policy still matched.
--   * is_admin(uid) checked grants_full_access alone, so a revoked admin kept full org access.
--   * can_access_lead(uid, lid) checked ownership and full access, never is_active.
--
-- Verified against a running instance before this migration: after setting is_active = false,
-- the user's existing token still returned their leads from the API *and* from PostgREST
-- directly. Deactivation only removed them from listings and the follow-up queues.
--
-- The web app queries Supabase directly from the browser in places (the dashboard's meetings
-- widget), so fixing this in the API alone would not have been enough -- these three functions
-- are what every policy funnels through, which is why the fix belongs here.
--
-- Access still ends only when the access token expires or is revoked; this closes the standing
-- grant, not the current token's remaining lifetime. Sign the user out of Supabase as well
-- when the revocation needs to take effect immediately.

-- Returning NULL for a revoked user is what does the work: every policy compares
-- `organization_id = current_org_id(auth.uid())`, and a comparison against NULL is NULL, which
-- fails the USING clause. No policy needs to change.
CREATE OR REPLACE FUNCTION public.current_org_id(uid uuid) RETURNS uuid
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'public'
    AS $$
  SELECT organization_id FROM public.users WHERE id = uid AND is_active
$$;

COMMENT ON FUNCTION public.current_org_id(uuid) IS
    'The caller''s organization, or NULL if the user is deactivated -- which makes every organization_id comparison in an RLS policy fail closed.';

CREATE OR REPLACE FUNCTION public.is_admin(uid uuid) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'public'
    AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.users u
    JOIN public.roles r ON r.id = u.role_id
    WHERE u.id = uid AND u.is_active AND r.grants_full_access
  )
$$;

COMMENT ON FUNCTION public.is_admin(uuid) IS
    'Single chokepoint for "has full access to their organization". Requires the user to still be active -- a revoked admin is not an admin.';

-- can_access_lead inlines the full-access check rather than calling is_admin(). That inlining
-- is exactly what broke when the fixed role enum became the roles table (see
-- 20260905170000_fix_can_access_lead_role_column.sql), so it now calls the chokepoint instead
-- of growing a second copy of the is_active rule alongside the one above.
CREATE OR REPLACE FUNCTION public.can_access_lead(uid uuid, lid uuid) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'public'
    AS $$
  SELECT EXISTS (
    SELECT 1
    FROM public.leads l
    JOIN public.users u ON u.id = uid
    WHERE l.id = lid
      AND l.deleted_at IS NULL
      AND u.is_active
      AND l.organization_id = u.organization_id
      AND (l.owner_id = uid OR public.is_admin(uid))
  )
$$;

COMMENT ON FUNCTION public.can_access_lead(uuid, uuid) IS
    'Own the lead, or hold a full-access role, and be active. Defers to is_admin() rather than inlining grants_full_access -- an inlined copy here is what caused the outage fixed in 20260905170000.';
