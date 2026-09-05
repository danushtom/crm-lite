-- Fix: creating a lead was impossible for every user, including admins.
--
-- `leads_select` was defined as `USING (public.can_access_lead(auth.uid(), id))`, and
-- `can_access_lead` is a STABLE function that re-queries `public.leads`:
--
--     SELECT EXISTS (SELECT 1 FROM public.leads l WHERE l.id = lid AND ...)
--
-- On `INSERT ... RETURNING` (what PostgREST issues for `Prefer: return=representation`,
-- and therefore what every API create call uses) the new row is not yet part of the
-- statement snapshot the STABLE function reads. The lookup finds nothing, the SELECT
-- policy denies the RETURNING clause, and Postgres reports 42501. The row insert itself
-- passed WITH CHECK -- `Prefer: return=minimal` succeeded -- which is what made this look
-- like an INSERT permission problem rather than a SELECT one.
--
-- The fix is to evaluate the policy against the row's own columns instead of looking the
-- row back up. This is semantically identical to the previous definition for existing
-- rows, works for RETURNING, and removes a correlated subquery per row from every lead
-- list query.
--
-- Other tables (`activities`, `opportunities`, `lead_intelligence`, `proposals`) also call
-- `can_access_lead`, but they pass a `lead_id` pointing at a *different*, already-committed
-- row, so they are unaffected. `can_access_lead` stays in place for them.

DROP POLICY IF EXISTS leads_select ON public.leads;
CREATE POLICY leads_select ON public.leads FOR SELECT USING (
  owner_id = auth.uid() OR public.is_admin(auth.uid())
);

-- Same self-reference in the update policy. It happened to work, because on UPDATE the
-- pre-existing row is visible to the lookup -- but a policy with no explicit WITH CHECK
-- reuses its USING expression to validate the new row, so reassigning `owner_id` was
-- validated against the *old* owner. Both clauses are now explicit.
DROP POLICY IF EXISTS leads_update ON public.leads;
CREATE POLICY leads_update ON public.leads
  FOR UPDATE
  USING (owner_id = auth.uid() OR public.is_admin(auth.uid()))
  WITH CHECK (owner_id = auth.uid() OR public.is_admin(auth.uid()));

COMMENT ON POLICY leads_select ON public.leads IS
  'Owner or admin. Evaluated on the row itself so INSERT ... RETURNING works.';
COMMENT ON POLICY leads_update ON public.leads IS
  'Owner or admin, checked on both the existing and the resulting row.';
