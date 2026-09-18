"use client";

import { Button, Input } from "@dracara/ui";
import { AuthLink, AuthShell, Field, MissingEnvNotice, authButtonClass } from "@/components/auth/auth-shell";
import { MIN_PASSWORD_LENGTH, confirmUrl, hasSupabaseEnv } from "@/lib/auth";
import { createClient } from "@/lib/supabase/client";
import { browserTimezone } from "@/lib/timezones";
import { useRouter } from "next/navigation";
import { useState } from "react";

/**
 * Self-serve signup. A signup with no invite creates a brand-new organization (named from
 * `organization_name`) with the signer as its Admin, and a 14-day trial -- all server-side, in
 * handle_new_user() and the billing migration's trigger. Joining an existing organization only
 * happens through an emailed invite, never from anything typed here.
 */
export default function SignupPage() {
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [organizationName, setOrganizationName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sentTo, setSentTo] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Use at least ${MIN_PASSWORD_LENGTH} characters for your password.`);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const supabase = createClient();
      const { data, error: signError } = await supabase.auth.signUp({
        email,
        password,
        options: {
          data: {
            full_name: fullName.trim(),
            organization_name: organizationName.trim(),
            // Validated server-side in handle_new_user(); an unknown zone falls back.
            timezone: browserTimezone(),
          },
          emailRedirectTo: confirmUrl("/dashboard"),
        },
      });
      if (signError) throw signError;
      if (data.session) {
        // Email confirmation is off for this project: the account is live already.
        router.push("/dashboard");
        router.refresh();
        return;
      }
      setSentTo(email);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Sign up failed");
    } finally {
      setLoading(false);
    }
  }

  if (sentTo) {
    return (
      <AuthShell
        title="Check your email"
        description={
          <>
            We sent a confirmation link to <span className="font-medium text-foreground">{sentTo}</span>. Open
            it on this device to finish creating your workspace.
          </>
        }
        footer={
          <>
            Wrong address? <button className="font-medium text-foreground underline underline-offset-4" onClick={() => setSentTo(null)}>Start again</button>
          </>
        }
      >
        <p className="text-sm text-muted-foreground">
          Nothing after a few minutes? Check your spam folder.
        </p>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Start your free trial"
      description="14 days, every feature, no card required."
      footer={
        <>
          Already have an account? <AuthLink href="/login">Sign in</AuthLink>
        </>
      }
    >
      {!hasSupabaseEnv() ? (
        <MissingEnvNotice />
      ) : (
        <form onSubmit={onSubmit} className="space-y-4">
          <Field id="full_name" label="Your name">
            <Input
              id="full_name"
              autoComplete="name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              required
            />
          </Field>
          <Field id="organization_name" label="Company / agency name">
            <Input
              id="organization_name"
              autoComplete="organization"
              value={organizationName}
              onChange={(e) => setOrganizationName(e.target.value)}
              required
            />
          </Field>
          <Field id="email" label="Work email">
            <Input
              id="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </Field>
          <Field id="password" label="Password">
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
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
          <Button type="submit" className={authButtonClass} disabled={loading}>
            {loading ? "Creating your workspace…" : "Create workspace"}
          </Button>
          <p className="text-center text-xs text-muted-foreground">
            Joining a teammate&apos;s workspace? Use the invite link in your email instead.
          </p>
        </form>
      )}
    </AuthShell>
  );
}
