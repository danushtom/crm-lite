-- soft_delete_voice_agent() left phone_numbers.assigned_voice_agent_id pointing at the
-- now-deleted agent, so an inbound call to that number would still try to route to it
-- (voice_webhooks.py's _resolve_or_create_inbound_call resolves purely through that column).
-- Release the number so it shows as unassigned and inbound calls are correctly dropped as
-- unrecognized rather than silently handed to a deleted agent.
CREATE OR REPLACE FUNCTION public.soft_delete_voice_agent(
  p_id UUID, p_expected_version INTEGER DEFAULT NULL
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  uid UUID := auth.uid();
  target public.voice_agents%ROWTYPE;
BEGIN
  IF uid IS NULL THEN
    RAISE EXCEPTION 'not authenticated' USING ERRCODE = '42501';
  END IF;

  SELECT * INTO target FROM public.voice_agents WHERE id = p_id;
  IF NOT FOUND OR target.deleted_at IS NOT NULL THEN
    RETURN jsonb_build_object('status', 'not_found');
  END IF;

  IF NOT (
    target.organization_id = public.current_org_id(uid)
    AND public.is_admin(uid)
  ) THEN
    RETURN jsonb_build_object('status', 'forbidden');
  END IF;

  IF EXISTS (
    SELECT 1 FROM public.calls c
    WHERE c.voice_agent_id = p_id AND c.status IN ('queued', 'ringing', 'in_progress')
  ) THEN
    RETURN jsonb_build_object('status', 'referenced');
  END IF;

  IF p_expected_version IS NOT NULL AND target.version <> p_expected_version THEN
    RETURN jsonb_build_object('status', 'version_mismatch', 'current_version', target.version);
  END IF;

  UPDATE public.phone_numbers SET assigned_voice_agent_id = NULL WHERE assigned_voice_agent_id = p_id;
  UPDATE public.voice_agents SET deleted_at = NOW() WHERE id = p_id;
  RETURN jsonb_build_object('status', 'deleted');
END;
$$;
