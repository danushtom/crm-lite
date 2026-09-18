"use client";

import { Button, Input } from "@dracara/ui";
import { AuthLink, AuthShell, Field, MissingEnvNotice, authButtonClass } from "@/components/auth/auth-shell";
import { hasSupabaseEnv, safeNext } from "@/lib/auth";
import { createClient } from "@/lib/supabase/client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

const NOTICES: Record<string, string> = {
  "password-updated": "Your password has been updated. Sign in with it below.",
  "link-expired": "That link has expired or was already used. Request a new one below.",
};

export default function LoginInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = safeNext(searchParams.get("next"));
  const notice = NOTICES[searchParams.get("notice") ?? ""];
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!hasSupabaseEnv()) return;
    setLoading(true);
    setError(null);
    try {
      const supabase = createClient();
      const { error: signError } = await supabase.auth.signInWithPassword({ email, password });
      if (signError) throw signError;
      router.push(next);
      router.refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Sign in failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthShell
      title="Sign in"
      description="Welcome back. Sign in to your workspace."
      footer={
        <>
          New to Dracara? <AuthLink href="/signup">Start a free 14-day trial</AuthLink>
        </>
      }
    >
      {!hasSupabaseEnv() ? (
        <MissingEnvNotice />
      ) : (
        <form onSubmit={onSubmit} className="space-y-4">
          {notice ? (
            <p className="rounded-lg border border-border bg-muted/50 px-3 py-2 text-sm">{notice}</p>
          ) : null}
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
          <Field
            id="password"
            label="Password"
            hint={
              <Link
                href="/forgot-password"
                className="text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
              >
                Forgot password?
              </Link>
            }
          >
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </Field>
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
          <Button type="submit" className={authButtonClass} disabled={loading}>
            {loading ? "Signing in…" : "Sign in"}
          </Button>
        </form>
      )}
    </AuthShell>
  );
}
