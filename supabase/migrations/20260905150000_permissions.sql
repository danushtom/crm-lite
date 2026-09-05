-- Permissions reference: what each role can actually do, made queryable.
--
-- Access today is enforced entirely by RLS policies plus a couple of API-level dependency
-- checks (require_admin, forbid_partner) -- there was no single place answering "what can an
-- agent do" other than reading every policy in 20260905140000_initial_schema.sql by hand. This
-- adds a small, descriptive reference: a `permissions` catalog (resource + action) and a
-- `role_permissions` grid, seeded to match what is *actually* enforced today.
--
-- This is documentation made queryable, not a new enforcement layer: RLS and the API
-- dependencies above remain the actual authority. If they ever diverge from this table, RLS
-- wins -- this table would just be describing them wrong, and should be corrected to match.
--
-- The one real role-specific restriction in the current schema: a partner cannot write
-- lead_intelligence (forbid_partner, apps/api/app/api/deps.py). Beyond that, `agent` and `sdr`
-- are identical in what they can access -- both are gated purely by row ownership (owner_id =
-- auth.uid()) OR admin, with no distinction between the two roles anywhere in RLS. `admin`
-- bypasses ownership entirely (within their own organization) and is the only role that can
-- manage teammates or write marketing spend data.

CREATE TYPE public.permission_action AS ENUM ('read', 'write', 'delete', 'manage');

CREATE TABLE public.permissions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  resource TEXT NOT NULL,
  action public.permission_action NOT NULL,
  description TEXT NOT NULL,
  UNIQUE (resource, action)
);

COMMENT ON TABLE public.permissions IS
  'Catalog of (resource, action) capabilities in the app. Reference data -- RLS and the API''s '
  'require_admin/forbid_partner dependencies are the actual enforcement; this describes them.';

CREATE TABLE public.role_permissions (
  role public.user_role NOT NULL,
  permission_id UUID NOT NULL REFERENCES public.permissions (id) ON DELETE CASCADE,
  PRIMARY KEY (role, permission_id)
);

COMMENT ON TABLE public.role_permissions IS
  'Which roles hold which permissions. Seeded below to match current RLS/dependency behavior.';

-- ---------------------------------------------------------------------------
-- Catalog.
-- ---------------------------------------------------------------------------
INSERT INTO public.permissions (resource, action, description) VALUES
  ('companies', 'read', 'View companies visible through an accessible lead, or one they created'),
  ('companies', 'write', 'Create or update a company'),
  ('companies', 'delete', 'Soft-delete a company (creator or admin; blocked while it has live leads)'),
  ('contacts', 'read', 'View contacts at an accessible company'),
  ('contacts', 'write', 'Create or update a contact'),
  ('contacts', 'delete', 'Soft-delete a contact (blocked while a live lead points to it)'),
  ('leads', 'read', 'View leads they own, or every lead in the organization if admin'),
  ('leads', 'write', 'Create or update a lead they own (or any, if admin)'),
  ('leads', 'delete', 'Soft-delete a lead they own (or any, if admin)'),
  ('lead_intelligence', 'read', 'View the CRM notes panel on an accessible lead'),
  ('lead_intelligence', 'write', 'Edit the CRM notes panel -- the one capability partners do not have'),
  ('opportunities', 'read', 'View pursuits on an accessible lead'),
  ('opportunities', 'write', 'Create, move (stage), or update a pursuit on an accessible lead'),
  ('opportunities', 'delete', 'Soft-delete a pursuit on an accessible lead'),
  ('proposals', 'read', 'View proposal versions on an accessible pursuit'),
  ('proposals', 'write', 'Create or update a proposal on an accessible pursuit'),
  ('proposals', 'delete', 'Delete a draft proposal (sent proposals cannot be deleted, by anyone)'),
  ('tasks', 'read', 'View follow-up tasks they own, or any if admin'),
  ('tasks', 'write', 'Create, complete, or reschedule a task they own (or any, if admin)'),
  ('tasks', 'delete', 'Delete a task they own (or any, if admin)'),
  ('meetings', 'read', 'View meetings they own, or any if admin'),
  ('meetings', 'write', 'Schedule or update a meeting they own (or any, if admin)'),
  ('meetings', 'delete', 'Delete a meeting they own (or any, if admin)'),
  ('activities', 'read', 'View the activity timeline on an accessible lead'),
  ('activities', 'write', 'Log an activity on an accessible lead (append-only -- no edit or delete, by anyone)'),
  ('agents', 'manage', 'Invite teammates, change roles, or revoke access -- admin only'),
  ('marketing_metrics', 'read', 'View CAC / channel spend snapshots for the organization'),
  ('marketing_metrics', 'write', 'Create or edit channel spend snapshots -- admin only'),
  ('organizations', 'manage', 'View/manage organization-level settings -- admin only (no settings UI exists yet)');

-- ---------------------------------------------------------------------------
-- Role grid. admin gets every permission; agent and sdr are identical (ownership-gated, no
-- role distinction in RLS); partner is the same minus lead_intelligence.write.
-- ---------------------------------------------------------------------------
INSERT INTO public.role_permissions (role, permission_id)
SELECT 'admin'::public.user_role, id FROM public.permissions;

INSERT INTO public.role_permissions (role, permission_id)
SELECT r.role, p.id
FROM public.permissions p
CROSS JOIN (VALUES ('agent'::public.user_role), ('sdr'::public.user_role)) AS r(role)
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

INSERT INTO public.role_permissions (role, permission_id)
SELECT 'partner'::public.user_role, id
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

-- ---------------------------------------------------------------------------
-- RLS: readable by any authenticated user in any organization (it's the same static catalog
-- everywhere -- not organization data), writable by no one through the API. Changing what a
-- role can do means changing RLS/dependencies and this seed together, by hand, in a migration.
-- ---------------------------------------------------------------------------
ALTER TABLE public.permissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.role_permissions ENABLE ROW LEVEL SECURITY;

CREATE POLICY permissions_select ON public.permissions FOR SELECT USING (
  (SELECT auth.uid()) IS NOT NULL
);

CREATE POLICY role_permissions_select ON public.role_permissions FOR SELECT USING (
  (SELECT auth.uid()) IS NOT NULL
);

GRANT SELECT ON public.permissions TO authenticated;
GRANT SELECT ON public.role_permissions TO authenticated;
