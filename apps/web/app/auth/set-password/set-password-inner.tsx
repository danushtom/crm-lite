"use client";

import { Button, Input } from "@dracara/ui";
import { AuthLink, AuthShell, Field, authButtonClass } from "@/components/auth/auth-shell";
import { MIN_PASSWORD_LENGTH, validateNewPassword } from "@/lib/auth";
import { apiFetch } from "@/lib/api";
import { createClient } from "@/lib/supabase/client";
import { browserTimezone } from "@/lib/timezones";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

/**
 * Choose a password for the signed-in account. Reached from /auth/confirm after an invite
 * (the invitee has no password yet) or a reset link. Middleware already sends anyone without a
 * session to /login.
 */
export default function SetPasswordInner() {
  const router = useRouter();
  const invited = useSearchParams().get("mode") === "invite";
  const [email, setEmail] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    createClient()
      .auth.getUser()
      .then(({ data }) => setEmail(data.user?.email ?? null));
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const invalid = validateNewPassword(password, confirm);
    if (invalid) {
      setError(invalid);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const supabase = createClient();
      const { error: updateError } = await supabase.auth.updateUser({ password });
      if (updateError) throw updateError;
      const timezone = browserTimezone();
      if (invited && timezone) {
        // An invite is minted server-side, so it could not carry the invitee's timezone the way
        // a signup does. Best effort: the password is what matters here.
        await apiFetch("/auth/me", { method: "PATCH", body: JSON.stringify({ timezone }) }).catch(() => undefined);
      }
      router.replace("/dashboard");
      router.refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not update your password");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthShell
      title={invited ? "Welcome aboard" : "Choose a new password"}
      description={
        invited
          ? "Your teammate invited you to their workspace. Set a password so you can sign in again later."
          : "Pick something you haven't used here before."
      }
      footer={
        invited ? null : (
          <>
            Changed your mind? <AuthLink href="/dashboard">Skip for now</AuthLink>
          </>
        )
      }
    >
      <form onSubmit={onSubmit} className="space-y-4">
        {email ? (
          <p className="text-sm text-muted-foreground">
            Signed in as <span className="font-medium text-foreground">{email}</span>
          </p>
        ) : null}
        {/* Lets password managers file the new password under the right account. */}
        <input type="email" autoComplete="username" value={email ?? ""} readOnly hidden />
        <Field id="password" label="New password">
          <Input
            id="password"
            type="password"
            autoComplete="new-password"
            minLength={MIN_PASSWORD_LENGTH}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </Field>
        <Field id="confirm" label="Confirm password">
          <Input
            id="confirm"
            type="password"
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
          />
        </Field>
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        <Button type="submit" className={authButtonClass} disabled={loading}>
          {loading ? "Saving…" : invited ? "Set password and continue" : "Update password"}
        </Button>
      </form>
    </AuthShell>
  );
}
