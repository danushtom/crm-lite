/** Shared helpers for the sign-in, sign-up, password-reset and invite flows. */

/** Supabase's own floor is configurable per project; the app asks for at least this much. */
export const MIN_PASSWORD_LENGTH = 8;

export const hasSupabaseEnv = () =>
  Boolean(process.env.NEXT_PUBLIC_SUPABASE_URL?.trim() && process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim());

/**
 * A `?next=` value is attacker-controllable (it arrives in a link), so only same-origin paths
 * are honoured. "//evil.test" and "/\evil.test" are protocol-relative to a browser, not paths.
 */
export function safeNext(next: string | null | undefined, fallback = "/dashboard"): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) {
    return fallback;
  }
  return next;
}

/** Where emailed auth links land: the confirm page establishes the session, then goes to `next`. */
export function confirmUrl(next: string): string {
  return `${window.location.origin}/auth/confirm?next=${encodeURIComponent(next)}`;
}

/** Returns an error message, or null when the pair is acceptable. */
export function validateNewPassword(password: string, confirm: string): string | null {
  if (password.length < MIN_PASSWORD_LENGTH) {
    return `Use at least ${MIN_PASSWORD_LENGTH} characters.`;
  }
  if (password !== confirm) return "The two passwords do not match.";
  return null;
}
