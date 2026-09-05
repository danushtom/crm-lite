-- Dynamic, admin-configurable roles.
--
-- public.user_role was a fixed Postgres enum: admin/agent/sdr/partner, identical across every
-- organization, editable by no one. This replaces it with `roles`, an organization-owned
-- table an admin can create, rename, delete, and grant permissions to, and repoints
-- `role_permissions` at it instead of the enum.
--
-- Row-level *visibility* is unchanged: every existing RLS policy already gates through the
-- single is_admin(uid) chokepoint rather than inlining `role = 'admin'`, so redefining that one
-- function's body is what keeps all of them correct -- see §7. What roles now control is
-- *feature* permissions (the role_permissions grid), not who can see which rows.
--
-- Every organization keeps its four familiar roles on this migration (Admin/Agent/SDR/Partner,
-- carrying exactly the grants seeded in 20260905150000_permissions.sql) so nothing breaks for
-- existing users; admins can edit, delete or add to them from here on. The one hard rule
-- carried forward: an organization can never end up with zero active users holding a role
-- marked "full access" (generalizes the old "can't remove the last admin").

-- ---------------------------------------------------------------------------
-- 1. The old enum-keyed role_permissions is superseded outright -- seed_default_roles() below
-- hardcodes the same grants directly (it has to: it's called for every org from here on, long
-- after this migration's transient state is gone, so it cannot depend on a table this
-- migration only keeps around temporarily).
-- ---------------------------------------------------------------------------
DROP TABLE public.role_permissions;

-- ---------------------------------------------------------------------------
-- 2. New tables.
-- ---------------------------------------------------------------------------
CREATE TABLE public.roles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES public.organizations (id),
  name TEXT NOT NULL,
  grants_full_access BOOLEAN NOT NULL DEFAULT FALSE,
  is_system BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  version INTEGER NOT NULL DEFAULT 1,
  UNIQUE (organization_id, name)
);

COMMENT ON TABLE public.roles IS
  'Organization-owned roles. grants_full_access is the one thing that cannot be delegated '
  'piecemeal -- a role either bypasses ownership entirely within its org (is_admin() below) '
  'or it does not; everything else is feature permissions via role_permissions. is_system '
  'marks the four seeded defaults for the UI only -- it carries no other restriction.';

CREATE TABLE public.role_permissions (
  role_id UUID NOT NULL REFERENCES public.roles (id) ON DELETE CASCADE,
  permission_id UUID NOT NULL REFERENCES public.permissions (id) ON DELETE CASCADE,
  PRIMARY KEY (role_id, permission_id)
);

-- organization_id is always derived, never client-supplied -- same reasoning as every other
-- set_*_organization() trigger this session: an authenticated caller gets their own org
-- unconditionally; a service-role caller (the seed function below, or this migration's own
-- backfill) is trusted to state it directly since it has already bypassed RLS.
CREATE OR REPLACE FUNCTION public.set_role_organization()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF auth.uid() IS NOT NULL THEN
    NEW.organization_id := public.current_org_id(auth.uid());
  END IF;
  IF NEW.organization_id IS NULL THEN
    RAISE EXCEPTION 'Cannot determine organization for this role' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER roles_set_org BEFORE INSERT ON public.roles
  FOR EACH ROW EXECUTE FUNCTION public.set_role_organization();

CREATE TRIGGER roles_touch BEFORE UPDATE ON public.roles
  FOR EACH ROW EXECUTE FUNCTION public.touch_updated_at();

CREATE TRIGGER roles_version BEFORE UPDATE ON public.roles
  FOR EACH ROW EXECUTE FUNCTION public.bump_version();

-- ---------------------------------------------------------------------------
-- 3. Seed the four default roles (+ their permission grants) for one organization. Used by
-- the backfill below and by handle_new_user() for every brand-new organization from here on.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.seed_default_roles(org_id UUID)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  admin_role_id UUID;
  agent_role_id UUID;
  sdr_role_id UUID;
  partner_role_id UUID;
BEGIN
  INSERT INTO public.roles (organization_id, name, grants_full_access, is_system)
    VALUES (org_id, 'Admin', TRUE, TRUE) RETURNING id INTO admin_role_id;
  INSERT INTO public.roles (organization_id, name, grants_full_access, is_system)
    VALUES (org_id, 'Agent', FALSE, TRUE) RETURNING id INTO agent_role_id;
  INSERT INTO public.roles (organization_id, name, grants_full_access, is_system)
    VALUES (org_id, 'SDR', FALSE, TRUE) RETURNING id INTO sdr_role_id;
  INSERT INTO public.roles (organization_id, name, grants_full_access, is_system)
    VALUES (org_id, 'Partner', FALSE, TRUE) RETURNING id INTO partner_role_id;

  -- Admin: every permission in the catalog.
  INSERT INTO public.role_permissions (role_id, permission_id)
  SELECT admin_role_id, id FROM public.permissions;

  -- Agent and SDR are identical: ownership decides what they see, not the role. These are the
  -- feature gates both hold -- the same set 20260905150000_permissions.sql originally seeded.
  INSERT INTO public.role_permissions (role_id, permission_id)
  SELECT r.rid, p.id
  FROM public.permissions p
  CROSS JOIN (VALUES (agent_role_id), (sdr_role_id)) AS r(rid)
  WHERE (p.resource, p.action) IN (
    ('companies', 'read'), ('companies', 'write'),
    ('contacts', 'read'), ('contacts', 'write'), ('contacts', 'delete'),
    ('leads', 'read'), ('leads', 'write'), ('leads', 'delete'),
    ('lead_intelligence', 'read'), ('lead_intelligence', 'write'),
    ('opportunities', 'read'), ('opportunities', 'write'), ('opportunities', 'delete'),
    ('proposals', 'read'), ('proposals', 'write'), ('proposals', 'delete'),
    ('tasks', 'read'), ('tasks', 'write'), ('tasks', 'delete'),
    ('meetings', 'read'), ('meetings', 'write'), ('meetings', 'delete'),
    ('activities', 'read'), ('activities', 'write'),
    ('marketing_metrics', 'read')
  );

  -- Partner: the same set minus lead_intelligence.write -- the one role-specific restriction
  -- that actually existed before this migration (forbid_partner).
  INSERT INTO public.role_permissions (role_id, permission_id)
  SELECT partner_role_id, p.id
  FROM public.permissions p
  WHERE (p.resource, p.action) IN (
    ('companies', 'read'), ('companies', 'write'),
    ('contacts', 'read'), ('contacts', 'write'), ('contacts', 'delete'),
    ('leads', 'read'), ('leads', 'write'), ('leads', 'delete'),
    ('lead_intelligence', 'read'),
    ('opportunities', 'read'), ('opportunities', 'write'), ('opportunities', 'delete'),
    ('proposals', 'read'), ('proposals', 'write'), ('proposals', 'delete'),
    ('tasks', 'read'), ('tasks', 'write'), ('tasks', 'delete'),
    ('meetings', 'read'), ('meetings', 'write'), ('meetings', 'delete'),
    ('activities', 'read'), ('activities', 'write'),
    ('marketing_metrics', 'read')
  );

  RETURN admin_role_id;
END;
$$;

-- ---------------------------------------------------------------------------
-- 4. Backfill: every existing organization gets its four roles; every existing user/invite
-- gets pointed at the matching one for its (still-present) enum value.
-- ---------------------------------------------------------------------------
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS role_id UUID;
ALTER TABLE public.org_invites ADD COLUMN IF NOT EXISTS role_id UUID;

DO $$
DECLARE
  org RECORD;
  admin_role_id UUID;
  agent_role_id UUID;
  sdr_role_id UUID;
  partner_role_id UUID;
BEGIN
  FOR org IN SELECT id FROM public.organizations LOOP
    admin_role_id := public.seed_default_roles(org.id);
    SELECT id INTO agent_role_id FROM public.roles WHERE organization_id = org.id AND name = 'Agent';
    SELECT id INTO sdr_role_id FROM public.roles WHERE organization_id = org.id AND name = 'SDR';
    SELECT id INTO partner_role_id FROM public.roles WHERE organization_id = org.id AND name = 'Partner';

    UPDATE public.users SET role_id = admin_role_id
      WHERE organization_id = org.id AND role = 'admin'::public.user_role;
    UPDATE public.users SET role_id = agent_role_id
      WHERE organization_id = org.id AND role = 'agent'::public.user_role;
    UPDATE public.users SET role_id = sdr_role_id
      WHERE organization_id = org.id AND role = 'sdr'::public.user_role;
    UPDATE public.users SET role_id = partner_role_id
      WHERE organization_id = org.id AND role = 'partner'::public.user_role;

    UPDATE public.org_invites SET role_id = admin_role_id
      WHERE organization_id = org.id AND role = 'admin'::public.user_role;
    UPDATE public.org_invites SET role_id = agent_role_id
      WHERE organization_id = org.id AND role = 'agent'::public.user_role;
    UPDATE public.org_invites SET role_id = sdr_role_id
      WHERE organization_id = org.id AND role = 'sdr'::public.user_role;
    UPDATE public.org_invites SET role_id = partner_role_id
      WHERE organization_id = org.id AND role = 'partner'::public.user_role;
  END LOOP;
END;
$$;

-- ---------------------------------------------------------------------------
-- 5. Lock the new columns down and remove the old ones.
-- ---------------------------------------------------------------------------
ALTER TABLE public.users ALTER COLUMN role_id SET NOT NULL;
ALTER TABLE public.users
  ADD CONSTRAINT users_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.roles (id);
CREATE INDEX users_role_id_idx ON public.users (role_id);

ALTER TABLE public.org_invites ALTER COLUMN role_id SET NOT NULL;
ALTER TABLE public.org_invites
  ADD CONSTRAINT org_invites_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.roles (id);

ALTER TABLE public.users DROP COLUMN role;
ALTER TABLE public.org_invites DROP COLUMN role;
DROP TYPE public.user_role;

-- ---------------------------------------------------------------------------
-- 6. is_admin(): the one function every RLS policy already calls instead of inlining a role
-- check. Redefining its body is what keeps every one of those policies correct unchanged.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.is_admin(uid UUID)
RETURNS BOOLEAN
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.users u
    JOIN public.roles r ON r.id = u.role_id
    WHERE u.id = uid AND r.grants_full_access
  )
$$;

-- ---------------------------------------------------------------------------
-- 7. Signup: resolve a role_id instead of a role/organization_id pair. A redeemed invite
-- carries its role_id directly; an un-invited signup gets a fresh org and its new Admin role.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  invite_token TEXT := NULLIF(NEW.raw_user_meta_data->>'invite_token', '');
  invite public.org_invites%ROWTYPE;
  invite_found BOOLEAN := FALSE;
  resolved_role_id UUID;
  resolved_org UUID;
  org_name TEXT;
BEGIN
  IF invite_token IS NOT NULL
     AND invite_token ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
  THEN
    SELECT * INTO invite
    FROM public.org_invites
    WHERE id = invite_token::UUID
      AND consumed_at IS NULL
      AND expires_at > NOW()
      AND lower(email) = lower(NEW.email)
    FOR UPDATE;
    invite_found := FOUND;
  END IF;

  IF invite_found THEN
    resolved_org := invite.organization_id;
    resolved_role_id := invite.role_id;
    UPDATE public.org_invites SET consumed_at = NOW() WHERE id = invite.id;
  ELSE
    org_name := COALESCE(
      NULLIF(NEW.raw_user_meta_data->>'organization_name', ''),
      NULLIF(NEW.raw_user_meta_data->>'full_name', '') || '''s workspace',
      NULLIF(split_part(NEW.email, '@', 1), '') || '''s workspace',
      'New workspace'
    );
    INSERT INTO public.organizations (name) VALUES (org_name) RETURNING id INTO resolved_org;
    resolved_role_id := public.seed_default_roles(resolved_org);
  END IF;

  INSERT INTO public.users (id, email, full_name, role_id, organization_id)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(
      NULLIF(NEW.raw_user_meta_data->>'full_name', ''),
      NULLIF(split_part(NEW.email, '@', 1), ''),
      'User'
    ),
    resolved_role_id,
    resolved_org
  )
  ON CONFLICT (id) DO NOTHING;

  RETURN NEW;
END;
$$;

-- ---------------------------------------------------------------------------
-- 8. "Last full-access user" replaces "last admin" -- same invariant, generalized past a
-- fixed role name. Renamed (guard_role_escalation -> guard_user_role_change) since it now
-- guards a role_id change, not an enum value.
-- ---------------------------------------------------------------------------
DROP TRIGGER IF EXISTS users_guard_role ON public.users;
DROP FUNCTION IF EXISTS public.guard_role_escalation();

CREATE OR REPLACE FUNCTION public.guard_user_role_change()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  old_grants_full BOOLEAN;
  new_grants_full BOOLEAN;
  full_access_count INTEGER;
BEGIN
  IF NEW.role_id IS DISTINCT FROM OLD.role_id AND NOT public.is_admin(auth.uid()) THEN
    RAISE EXCEPTION 'Only an admin may change a role' USING ERRCODE = '42501';
  END IF;

  IF NEW.organization_id IS DISTINCT FROM OLD.organization_id THEN
    RAISE EXCEPTION 'organization_id cannot be changed' USING ERRCODE = '42501';
  END IF;

  SELECT grants_full_access INTO old_grants_full FROM public.roles WHERE id = OLD.role_id;
  SELECT grants_full_access INTO new_grants_full FROM public.roles WHERE id = NEW.role_id;

  IF (old_grants_full AND NOT new_grants_full)
     OR (OLD.is_active AND NOT NEW.is_active AND old_grants_full) THEN
    SELECT COUNT(*) INTO full_access_count
    FROM public.users u
    JOIN public.roles r ON r.id = u.role_id
    WHERE r.organization_id = OLD.organization_id AND r.grants_full_access AND u.is_active;

    IF full_access_count <= 1 THEN
      IF old_grants_full AND NOT new_grants_full THEN
        RAISE EXCEPTION 'Cannot remove the last full-access user' USING ERRCODE = 'check_violation';
      ELSE
        RAISE EXCEPTION 'Cannot deactivate the last full-access user' USING ERRCODE = 'check_violation';
      END IF;
    END IF;
  END IF;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS users_guard_role ON public.users;
CREATE TRIGGER users_guard_role
  BEFORE UPDATE ON public.users
  FOR EACH ROW EXECUTE FUNCTION public.guard_user_role_change();

-- ---------------------------------------------------------------------------
-- 9. The same invariant from the role side: can't delete a role, or strip its full-access
-- flag, if that would leave the organization with zero active full-access users. (Deleting a
-- role that still has users assigned already fails on its own via the plain FK constraint --
-- role_id is NOT NULL with no ON DELETE action, so that path needs no extra guard here.)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.guard_role_deletion_or_demotion()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  remaining_full_access INTEGER;
BEGIN
  IF TG_OP = 'DELETE' AND OLD.grants_full_access THEN
    SELECT COUNT(*) INTO remaining_full_access
    FROM public.users u
    JOIN public.roles r ON r.id = u.role_id
    WHERE r.organization_id = OLD.organization_id AND r.grants_full_access
      AND r.id <> OLD.id AND u.is_active;
    IF remaining_full_access = 0 THEN
      RAISE EXCEPTION 'Cannot delete the organization''s last full-access role'
        USING ERRCODE = 'check_violation';
    END IF;
    RETURN OLD;
  END IF;

  IF TG_OP = 'UPDATE' AND OLD.grants_full_access AND NOT NEW.grants_full_access THEN
    SELECT COUNT(*) INTO remaining_full_access
    FROM public.users u
    JOIN public.roles r ON r.id = u.role_id
    WHERE r.organization_id = OLD.organization_id AND r.grants_full_access
      AND r.id <> OLD.id AND u.is_active;
    IF remaining_full_access = 0 THEN
      RAISE EXCEPTION 'Cannot remove full access from the organization''s last full-access role'
        USING ERRCODE = 'check_violation';
    END IF;
  END IF;

  RETURN NEW;
END;
$$;

CREATE TRIGGER roles_guard_deletion_or_demotion
  BEFORE UPDATE OR DELETE ON public.roles
  FOR EACH ROW EXECUTE FUNCTION public.guard_role_deletion_or_demotion();

-- ---------------------------------------------------------------------------
-- 10. RLS.
-- ---------------------------------------------------------------------------
ALTER TABLE public.roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.role_permissions ENABLE ROW LEVEL SECURITY;

CREATE POLICY roles_select ON public.roles FOR SELECT USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
);

CREATE POLICY roles_insert ON public.roles FOR INSERT WITH CHECK (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (SELECT public.is_admin(auth.uid()))
);

CREATE POLICY roles_update ON public.roles FOR UPDATE
  USING (
    organization_id = (SELECT public.current_org_id(auth.uid()))
    AND (SELECT public.is_admin(auth.uid()))
  )
  WITH CHECK (
    organization_id = (SELECT public.current_org_id(auth.uid()))
    AND (SELECT public.is_admin(auth.uid()))
  );

CREATE POLICY roles_delete ON public.roles FOR DELETE USING (
  organization_id = (SELECT public.current_org_id(auth.uid()))
  AND (SELECT public.is_admin(auth.uid()))
);

-- Read: same static-catalog reasoning as `permissions` itself. Write: only an admin, only on
-- their own org's roles (checked by joining to roles, since this table carries no
-- organization_id of its own).
CREATE POLICY role_permissions_select ON public.role_permissions FOR SELECT USING (
  (SELECT auth.uid()) IS NOT NULL
);

CREATE POLICY role_permissions_insert ON public.role_permissions FOR INSERT WITH CHECK (
  EXISTS (
    SELECT 1 FROM public.roles r
    WHERE r.id = role_permissions.role_id
      AND r.organization_id = (SELECT public.current_org_id(auth.uid()))
      AND (SELECT public.is_admin(auth.uid()))
  )
);

CREATE POLICY role_permissions_delete ON public.role_permissions FOR DELETE USING (
  EXISTS (
    SELECT 1 FROM public.roles r
    WHERE r.id = role_permissions.role_id
      AND r.organization_id = (SELECT public.current_org_id(auth.uid()))
      AND (SELECT public.is_admin(auth.uid()))
  )
);
