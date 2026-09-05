-- can_access_lead() inlined `u.role = 'admin'` as a query-plan optimization (avoiding a
-- second call to is_admin() when it had already joined users for the organization check) --
-- but that inlining is exactly what 20260905160000_dynamic_roles.sql's "every RLS policy
-- already goes through is_admin()" assumption missed. users.role no longer exists; every read
-- through can_access_lead() (opportunities, lead_intelligence, activities, proposals, and
-- leads/contacts/companies indirectly) has been failing with "column u.role does not exist"
-- since that migration landed.
CREATE OR REPLACE FUNCTION public.can_access_lead(uid UUID, lid UUID)
RETURNS BOOLEAN
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM public.leads l
    JOIN public.users u ON u.id = uid
    JOIN public.roles r ON r.id = u.role_id
    WHERE l.id = lid
      AND l.deleted_at IS NULL
      AND l.organization_id = u.organization_id
      AND (l.owner_id = uid OR r.grants_full_access)
  )
$$;
