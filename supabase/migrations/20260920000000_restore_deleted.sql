-- Recently deleted: list and restore soft-deleted companies, contacts, leads and opportunities.
--
-- Deletes have always been soft (deleted_at), but the SELECT policies hide deleted rows, so
-- nobody could see or undo one without editing the database. Listing and restoring need the
-- same SECURITY DEFINER treatment the soft_delete_* functions already get (see their comment
-- in the initial schema), and each applies *exactly the rule its delete function applies*: you
-- can see and restore what you could have deleted, nothing more.

-- 1. Who deleted it. Stamped by trigger rather than by editing the four delete functions, so
--    any path that sets deleted_at (the functions, a future bulk delete) records it.
ALTER TABLE public.companies ADD COLUMN IF NOT EXISTS deleted_by UUID REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE public.contacts ADD COLUMN IF NOT EXISTS deleted_by UUID REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS deleted_by UUID REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE public.opportunities ADD COLUMN IF NOT EXISTS deleted_by UUID REFERENCES public.users(id) ON DELETE SET NULL;

CREATE OR REPLACE FUNCTION public.stamp_deleted_by()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
  IF NEW.deleted_at IS NOT NULL AND OLD.deleted_at IS NULL THEN
    NEW.deleted_by := auth.uid();
  ELSIF NEW.deleted_at IS NULL THEN
    NEW.deleted_by := NULL;
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS companies_stamp_deleted_by ON public.companies;
CREATE TRIGGER companies_stamp_deleted_by BEFORE UPDATE OF deleted_at ON public.companies
  FOR EACH ROW EXECUTE FUNCTION public.stamp_deleted_by();
DROP TRIGGER IF EXISTS contacts_stamp_deleted_by ON public.contacts;
CREATE TRIGGER contacts_stamp_deleted_by BEFORE UPDATE OF deleted_at ON public.contacts
  FOR EACH ROW EXECUTE FUNCTION public.stamp_deleted_by();
DROP TRIGGER IF EXISTS leads_stamp_deleted_by ON public.leads;
CREATE TRIGGER leads_stamp_deleted_by BEFORE UPDATE OF deleted_at ON public.leads
  FOR EACH ROW EXECUTE FUNCTION public.stamp_deleted_by();
DROP TRIGGER IF EXISTS opportunities_stamp_deleted_by ON public.opportunities;
CREATE TRIGGER opportunities_stamp_deleted_by BEFORE UPDATE OF deleted_at ON public.opportunities
  FOR EACH ROW EXECUTE FUNCTION public.stamp_deleted_by();

-- 2. The permission rule, once per kind, shared by listing and restoring. These mirror the
--    checks inside soft_delete_company/_contact/_lead/_opportunity. Opportunities cannot reuse
--    can_access_lead(): it requires the lead itself to be live, and an opportunity whose lead
--    is also deleted must still be listable (as "restore the lead first").
CREATE OR REPLACE FUNCTION public.may_manage_deleted(uid UUID, p_kind TEXT, p_id UUID)
RETURNS BOOLEAN
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public
AS $$
  SELECT CASE p_kind
    WHEN 'companies' THEN EXISTS (
      SELECT 1 FROM public.companies c
      WHERE c.id = p_id AND c.organization_id = public.current_org_id(uid)
        AND (c.created_by = uid OR public.is_admin(uid)))
    WHEN 'contacts' THEN EXISTS (
      SELECT 1 FROM public.contacts ct
      WHERE ct.id = p_id AND ct.organization_id = public.current_org_id(uid)
        AND (public.is_admin(uid) OR EXISTS (
          SELECT 1 FROM public.companies c WHERE c.id = ct.company_id AND c.created_by = uid)))
    WHEN 'leads' THEN EXISTS (
      SELECT 1 FROM public.leads l
      WHERE l.id = p_id AND l.organization_id = public.current_org_id(uid)
        AND (l.owner_id = uid OR public.is_admin(uid)))
    WHEN 'opportunities' THEN EXISTS (
      SELECT 1 FROM public.opportunities o JOIN public.leads l ON l.id = o.lead_id
      WHERE o.id = p_id AND o.organization_id = public.current_org_id(uid)
        AND (l.owner_id = uid OR public.is_admin(uid)))
    ELSE FALSE
  END
$$;

-- 3. The list. Newest first; `blocked_by` names the deleted parent that must be restored first.
CREATE OR REPLACE FUNCTION public.recently_deleted(p_kind TEXT, p_limit INTEGER DEFAULT 50, p_offset INTEGER DEFAULT 0)
RETURNS TABLE (
  id UUID,
  label TEXT,
  detail TEXT,
  deleted_at TIMESTAMPTZ,
  deleted_by_name TEXT,
  blocked_by TEXT
)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  uid UUID := auth.uid();
  org UUID := public.current_org_id(auth.uid());
  lim INTEGER := LEAST(GREATEST(COALESCE(p_limit, 50), 1), 201);
  off INTEGER := GREATEST(COALESCE(p_offset, 0), 0);
BEGIN
  IF uid IS NULL OR org IS NULL THEN
    RAISE EXCEPTION 'not authenticated' USING ERRCODE = '42501';
  END IF;

  IF p_kind = 'companies' THEN
    RETURN QUERY
      SELECT c.id, c.name, c.website, c.deleted_at, u.full_name, NULL::TEXT
      FROM public.companies c LEFT JOIN public.users u ON u.id = c.deleted_by
      WHERE c.organization_id = org AND c.deleted_at IS NOT NULL
        AND public.may_manage_deleted(uid, 'companies', c.id)
      ORDER BY c.deleted_at DESC, c.id DESC LIMIT lim OFFSET off;
  ELSIF p_kind = 'contacts' THEN
    RETURN QUERY
      SELECT ct.id, ct.full_name,
             concat_ws(' · ', co.name, ct.email),
             ct.deleted_at, u.full_name,
             CASE WHEN co.deleted_at IS NOT NULL THEN 'company' END
      FROM public.contacts ct
      JOIN public.companies co ON co.id = ct.company_id
      LEFT JOIN public.users u ON u.id = ct.deleted_by
      WHERE ct.organization_id = org AND ct.deleted_at IS NOT NULL
        AND public.may_manage_deleted(uid, 'contacts', ct.id)
      ORDER BY ct.deleted_at DESC, ct.id DESC LIMIT lim OFFSET off;
  ELSIF p_kind = 'leads' THEN
    RETURN QUERY
      SELECT l.id, co.name,
             concat_ws(' · ', initcap(replace(l.project_type::TEXT, '_', ' ')), pc.full_name),
             l.deleted_at, u.full_name,
             CASE
               WHEN co.deleted_at IS NOT NULL THEN 'company'
               WHEN pc.deleted_at IS NOT NULL THEN 'contact'
             END
      FROM public.leads l
      JOIN public.companies co ON co.id = l.company_id
      LEFT JOIN public.contacts pc ON pc.id = l.primary_contact_id
      LEFT JOIN public.users u ON u.id = l.deleted_by
      WHERE l.organization_id = org AND l.deleted_at IS NOT NULL
        AND public.may_manage_deleted(uid, 'leads', l.id)
      ORDER BY l.deleted_at DESC, l.id DESC LIMIT lim OFFSET off;
  ELSIF p_kind = 'opportunities' THEN
    RETURN QUERY
      SELECT o.id, o.title,
             concat_ws(' · ', co.name, initcap(replace(o.stage::TEXT, '_', ' '))),
             o.deleted_at, u.full_name,
             CASE WHEN l.deleted_at IS NOT NULL THEN 'lead' END
      FROM public.opportunities o
      JOIN public.leads l ON l.id = o.lead_id
      JOIN public.companies co ON co.id = l.company_id
      LEFT JOIN public.users u ON u.id = o.deleted_by
      WHERE o.organization_id = org AND o.deleted_at IS NOT NULL
        AND public.may_manage_deleted(uid, 'opportunities', o.id)
      ORDER BY o.deleted_at DESC, o.id DESC LIMIT lim OFFSET off;
  ELSE
    RAISE EXCEPTION 'unknown kind %', p_kind USING ERRCODE = '22023';
  END IF;
END;
$$;

-- 4. Restore. Returns a status the API maps to a response, like the soft_delete_* functions.
CREATE OR REPLACE FUNCTION public.restore_record(p_kind TEXT, p_id UUID)
RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  uid UUID := auth.uid();
  blocker TEXT;
BEGIN
  IF uid IS NULL THEN
    RAISE EXCEPTION 'not authenticated' USING ERRCODE = '42501';
  END IF;
  IF p_kind NOT IN ('companies', 'contacts', 'leads', 'opportunities') THEN
    RETURN jsonb_build_object('status', 'not_found');
  END IF;
  IF NOT public.may_manage_deleted(uid, p_kind, p_id) THEN
    -- Not distinguished from a missing id: an id from another tenant must not be confirmable.
    RETURN jsonb_build_object('status', 'not_found');
  END IF;

  IF p_kind = 'companies' THEN
    UPDATE public.companies SET deleted_at = NULL WHERE id = p_id AND deleted_at IS NOT NULL;
  ELSIF p_kind = 'contacts' THEN
    SELECT 'company' INTO blocker FROM public.contacts ct JOIN public.companies co ON co.id = ct.company_id
      WHERE ct.id = p_id AND co.deleted_at IS NOT NULL;
    IF blocker IS NOT NULL THEN
      RETURN jsonb_build_object('status', 'parent_deleted', 'parent', blocker);
    END IF;
    UPDATE public.contacts SET deleted_at = NULL WHERE id = p_id AND deleted_at IS NOT NULL;
  ELSIF p_kind = 'leads' THEN
    SELECT CASE WHEN co.deleted_at IS NOT NULL THEN 'company' WHEN pc.deleted_at IS NOT NULL THEN 'contact' END
      INTO blocker
      FROM public.leads l JOIN public.companies co ON co.id = l.company_id
      LEFT JOIN public.contacts pc ON pc.id = l.primary_contact_id
      WHERE l.id = p_id;
    IF blocker IS NOT NULL THEN
      RETURN jsonb_build_object('status', 'parent_deleted', 'parent', blocker);
    END IF;
    UPDATE public.leads SET deleted_at = NULL WHERE id = p_id AND deleted_at IS NOT NULL;
  ELSE
    SELECT 'lead' INTO blocker FROM public.opportunities o JOIN public.leads l ON l.id = o.lead_id
      WHERE o.id = p_id AND l.deleted_at IS NOT NULL;
    IF blocker IS NOT NULL THEN
      RETURN jsonb_build_object('status', 'parent_deleted', 'parent', blocker);
    END IF;
    BEGIN
      UPDATE public.opportunities SET deleted_at = NULL WHERE id = p_id AND deleted_at IS NOT NULL;
    EXCEPTION WHEN unique_violation THEN
      -- opportunities_one_active_per_lead_idx: the lead has since opened another active pursuit.
      RETURN jsonb_build_object('status', 'conflict');
    END;
  END IF;

  IF NOT FOUND THEN
    RETURN jsonb_build_object('status', 'not_found');
  END IF;
  RETURN jsonb_build_object('status', 'restored');
END;
$$;

REVOKE ALL ON FUNCTION public.may_manage_deleted(UUID, TEXT, UUID) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.recently_deleted(TEXT, INTEGER, INTEGER) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.restore_record(TEXT, UUID) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.may_manage_deleted(UUID, TEXT, UUID) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.recently_deleted(TEXT, INTEGER, INTEGER) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.restore_record(TEXT, UUID) TO authenticated, service_role;
