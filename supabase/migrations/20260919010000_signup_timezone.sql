-- New users get the timezone their browser reported at signup instead of a hard-coded
-- 'Asia/Kolkata'. Timezone drives each user's follow-up day boundaries, so a user abroad on the
-- default saw "due today" roll over at the wrong midnight until they found the setting.
--
-- Same function as 20260905160000_dynamic_roles.sql section 7, plus one thing: the optional
-- `timezone` signup metadata. It is client-supplied, so it is validated here -- an unknown zone
-- would otherwise make users_timezone_check raise and fail the whole signup -- and falls back to
-- the column's previous default.

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
  requested_tz TEXT := NULLIF(NEW.raw_user_meta_data->>'timezone', '');
BEGIN
  IF requested_tz IS NOT NULL
     AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_timezone_names WHERE name = requested_tz)
  THEN
    requested_tz := NULL;
  END IF;

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

  INSERT INTO public.users (id, email, full_name, role_id, organization_id, timezone)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(
      NULLIF(NEW.raw_user_meta_data->>'full_name', ''),
      NULLIF(split_part(NEW.email, '@', 1), ''),
      'User'
    ),
    resolved_role_id,
    resolved_org,
    COALESCE(requested_tz, 'Asia/Kolkata')
  )
  ON CONFLICT (id) DO NOTHING;

  RETURN NEW;
END;
$$;
