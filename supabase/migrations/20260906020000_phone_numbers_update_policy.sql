-- phone_numbers had SELECT/INSERT/DELETE policies but no UPDATE policy. RLS defaults to deny
-- when no policy matches the command, so voice_agents.py's assignment sync
-- (UPDATE phone_numbers SET assigned_voice_agent_id = ...) was silently affecting zero rows --
-- no error, no exception, just a write that never happened. Same class of gap as the missing
-- organizations UPDATE policy hit earlier in this feature.
CREATE POLICY phone_numbers_update ON public.phone_numbers FOR UPDATE
  USING (
    organization_id = (SELECT public.current_org_id(auth.uid()))
    AND (SELECT public.is_admin(auth.uid()))
  )
  WITH CHECK (
    organization_id = (SELECT public.current_org_id(auth.uid()))
    AND (SELECT public.is_admin(auth.uid()))
  );
