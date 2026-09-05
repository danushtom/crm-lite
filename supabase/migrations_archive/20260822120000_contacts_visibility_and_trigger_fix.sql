-- Fixes found in the frontend/backend/DB consistency review:
--   1. Contacts created against a lead-less company were invisible to their own creator.
--   2. contacts had no DELETE policy, so the UI delete action could only ever silently no-op.
--   3. Opportunity stage changes made by the worker (service role) violated activities.performed_by NOT NULL.

-- 1. Visibility: mirror the `created_by` escape hatch that companies_select already has.
--    Without this, contacts_insert allows a company owner to create a contact that
--    contacts_select then hides from them until a lead exists on that company.
DROP POLICY IF EXISTS contacts_select ON public.contacts;
CREATE POLICY contacts_select ON public.contacts FOR SELECT USING (
  public.is_admin(auth.uid())
  OR EXISTS (
    SELECT 1 FROM public.companies c
    WHERE c.id = contacts.company_id AND c.created_by = auth.uid()
  )
  OR EXISTS (
    SELECT 1 FROM public.leads l
    WHERE l.company_id = contacts.company_id AND public.can_access_lead(auth.uid(), l.id)
  )
);

-- Keep UPDATE reachable on the same terms as SELECT.
DROP POLICY IF EXISTS contacts_update ON public.contacts;
CREATE POLICY contacts_update ON public.contacts FOR UPDATE USING (
  public.is_admin(auth.uid())
  OR EXISTS (
    SELECT 1 FROM public.companies c
    WHERE c.id = contacts.company_id AND c.created_by = auth.uid()
  )
  OR EXISTS (
    SELECT 1 FROM public.leads l
    WHERE l.company_id = contacts.company_id AND public.can_access_lead(auth.uid(), l.id)
  )
);

-- 2. DELETE policy so `DELETE /contacts/{id}` can actually remove a row.
--    leads.primary_contact_id has no ON DELETE action, so a contact still referenced by a
--    lead is protected by the FK and the delete correctly fails rather than orphaning data.
DROP POLICY IF EXISTS contacts_delete ON public.contacts;
CREATE POLICY contacts_delete ON public.contacts FOR DELETE USING (
  public.is_admin(auth.uid())
  OR EXISTS (
    SELECT 1 FROM public.companies c
    WHERE c.id = contacts.company_id AND c.created_by = auth.uid()
  )
);

-- 3. auth.uid() is NULL for service-role writes (the Celery worker moves stages on
--    opportunities), but activities.performed_by is NOT NULL. Fall back to the record owner.
CREATE OR REPLACE FUNCTION public.log_opportunity_stage_change()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF TG_OP = 'UPDATE' AND OLD.stage IS DISTINCT FROM NEW.stage THEN
    INSERT INTO public.activities (lead_id, type, description, performed_by, metadata)
    VALUES (
      NEW.lead_id,
      'stage_change'::public.activity_type,
      'Opportunity stage changed from ' || OLD.stage::TEXT || ' to ' || NEW.stage::TEXT,
      COALESCE(auth.uid(), NEW.owner_id),
      jsonb_build_object(
        'opportunity_id', NEW.id::TEXT,
        'old_stage', OLD.stage::TEXT,
        'new_stage', NEW.stage::TEXT,
        'actor', CASE WHEN auth.uid() IS NULL THEN 'system' ELSE 'user' END
      )
    );
  END IF;
  RETURN NEW;
END;
$$;
