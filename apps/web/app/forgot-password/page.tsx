"use client";

import { Button, Input } from "@dracara/ui";
import { AuthLink, AuthShell, Field, MissingEnvNotice, authButtonClass } from "@/components/auth/auth-shell";
import { confirmUrl, hasSupabaseEnv } from "@/lib/auth";
import { createClient } from "@/lib/supabase/client";
import { useState } from "react";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const supabase = createClient();
      const { error: resetError } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: confirmUrl("/auth/set-password?mode=reset"),
      });
      // Rate limiting is worth surfacing; "no such user" is not (Supabase does not reveal it,
      // and the confirmation below is deliberately identical either way).
      if (resetError && resetError.status === 429) throw resetError;
      setSent(true);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not send the reset email");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthShell
      title={sent ? "Check your email" : "Reset your password"}
      description={
        sent
          ? "If an account exists for that address, a link to choose a new password is on its way."
          : "Enter your email and we'll send you a link to choose a new password."
      }
      footer={
        <>
          Remembered it? <AuthLink href="/login">Back to sign in</AuthLink>
        </>
      }
    >
      {!hasSupabaseEnv() ? (
        <MissingEnvNotice />
      ) : sent ? (
        <p className="text-sm text-muted-foreground">
          Open the link on this device. It expires after an hour.
        </p>
      ) : (
        <form onSubmit={onSubmit} className="space-y-4">
          <Field id="email" label="Email">
            <Input
              id="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </Field>
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
          <Button type="submit" className={authButtonClass} disabled={loading}>
            {loading ? "Sending…" : "Send reset link"}
          </Button>
        </form>
      )}
    </AuthShell>
  );
}
