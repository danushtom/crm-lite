/**
 * Two-factor helpers. The *enforcement* is in the database (20260920010000_enforce_mfa.sql);
 * these only route the user to the code prompt so they meet it as a step, not as empty screens.
 */

import type { SupabaseClient } from "@supabase/supabase-js";

/** True when this session's user has a verified factor but has not used it this session. */
export async function needsSecondFactor(supabase: SupabaseClient): Promise<boolean> {
  const { data, error } = await supabase.auth.mfa.getAuthenticatorAssuranceLevel();
  if (error || !data) return false;
  return data.nextLevel === "aal2" && data.currentLevel !== "aal2";
}

/** A 6-digit TOTP code, tolerating the spaces authenticator apps display ("123 456"). */
export function normalizeTotp(input: string): string | null {
  const digits = input.replace(/\s+/g, "");
  return /^\d{6}$/.test(digits) ? digits : null;
}
