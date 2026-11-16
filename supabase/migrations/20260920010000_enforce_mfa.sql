-- Two-factor authentication, enforced by the database.
--
-- A user who has enrolled a verified factor must present an aal2 session (password + code).
-- Checking that only in the web app would protect nothing: the attacker 2FA exists to stop
-- already has the password, and can sign in to Supabase Auth directly for an aal1 token and
-- call PostgREST, an RPC or this API without ever loading the app. So, following Supabase's
-- documented pattern, the check lives where every read and write is decided -- in two layers:
--
--   1. current_org_id() returns NULL for an under-verified session. It is the chokepoint every
--      organization-scoped policy *and* every SECURITY DEFINER function (soft_delete_*,
--      restore_record, recently_deleted...) compares against, so this closes the definer
--      functions too, exactly as returning NULL closed them for revoked users (20260909020000).
--   2. A RESTRICTIVE policy on every RLS table, for the few policies that do not go through
--      the chokepoint (notifications_*_own, users_update_self).
--
-- A user without a verified factor is unaffected: mfa_satisfied() is true for them at aal1.
-- Service-role callers (the worker, webhooks) have no auth.uid() and are unaffected.

CREATE OR REPLACE FUNCTION public.mfa_satisfied()
RETURNS BOOLEAN
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public, auth
AS $$
  SELECT CASE
    WHEN EXISTS (
      SELECT 1 FROM auth.mfa_factors f
      WHERE f.user_id = auth.uid() AND f.status = 'verified'
    ) THEN coalesce(auth.jwt() ->> 'aal', '') = 'aal2'
    ELSE TRUE
  END
$$;

COMMENT ON FUNCTION public.mfa_satisfied() IS
  'False only when the session''s user has a verified MFA factor but the session is below aal2.';

-- Same body as 20260909020000, plus the MFA condition -- applied only when the function is
-- evaluated for the session's own user, which is every policy's case (current_org_id(auth.uid())).
CREATE OR REPLACE FUNCTION public.current_org_id(uid uuid) RETURNS uuid
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'public'
    AS $$
  SELECT organization_id FROM public.users
  WHERE id = uid AND is_active
    AND (uid IS DISTINCT FROM auth.uid() OR public.mfa_satisfied())
$$;

COMMENT ON FUNCTION public.current_org_id(uuid) IS
    'The caller''s organization, or NULL if the user is deactivated or has not completed a required second factor -- which makes every organization_id comparison in an RLS policy, and every definer function that checks it, fail closed.';

DO $$
DECLARE
  t RECORD;
BEGIN
  FOR t IN
    SELECT c.relname
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relrowsecurity
  LOOP
    EXECUTE format('DROP POLICY IF EXISTS mfa_required ON public.%I', t.relname);
    EXECUTE format(
      'CREATE POLICY mfa_required ON public.%I AS RESTRICTIVE FOR ALL TO authenticated '
      'USING ((SELECT public.mfa_satisfied())) WITH CHECK ((SELECT public.mfa_satisfied()))',
      t.relname
    );
  END LOOP;
END;
$$;

REVOKE ALL ON FUNCTION public.mfa_satisfied() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.mfa_satisfied() TO authenticated, service_role;
