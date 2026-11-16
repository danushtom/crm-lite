"use client";

import { Button, Input } from "@dracara/ui";
import { AuthShell, Field, authButtonClass } from "@/components/auth/auth-shell";
import { safeNext } from "@/lib/auth";
import { normalizeTotp } from "@/lib/mfa";
import { createClient } from "@/lib/supabase/client";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

export default function VerifyPage() {
  return (
    <Suspense fallback={<div className="flex min-h-screen items-center justify-center">Loading…</div>}>
      <VerifyInner />
    </Suspense>
  );
}

/** The second step of sign-in for users who have turned on two-factor authentication. */
function VerifyInner() {
  const router = useRouter();
  const next = safeNext(useSearchParams().get("next"));
  const [factorId, setFactorId] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const supabase = createClient();
    supabase.auth.mfa.listFactors().then(({ data }) => {
      const factor = data?.totp.find((f) => f.status === "verified");
      if (!factor) {
        // No second factor (or no session): nothing to verify here.
        router.replace(next);
        return;
      }
      setFactorId(factor.id);
    });
  }, [next, router]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const digits = normalizeTotp(code);
    if (!factorId || !digits) {
      setError("Enter the 6-digit code from your authenticator app.");
      return;
    }
    setLoading(true);
    setError(null);
    const { error: verifyError } = await createClient().auth.mfa.challengeAndVerify({ factorId, code: digits });
    setLoading(false);
    if (verifyError) {
      setError("That code did not work. Codes change every 30 seconds; try the current one.");
      setCode("");
      return;
    }
    router.replace(next);
    router.refresh();
  }

  async function signOut() {
    await createClient().auth.signOut();
    router.replace("/login");
    router.refresh();
  }

  return (
    <AuthShell
      title="Two-step verification"
      description="Enter the 6-digit code from your authenticator app."
      footer={
        <button type="button" onClick={signOut} className="underline underline-offset-4 hover:text-foreground">
          Sign in as someone else
        </button>
      }
    >
      <form onSubmit={onSubmit} className="space-y-4">
        <Field id="code" label="Authentication code">
          <Input
            id="code"
            inputMode="numeric"
            autoComplete="one-time-code"
            autoFocus
            maxLength={7}
            placeholder="123456"
            className="text-center text-lg tracking-[0.4em]"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            required
          />
        </Field>
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        <Button type="submit" className={authButtonClass} disabled={loading || !factorId}>
          {loading ? "Verifying…" : "Verify"}
        </Button>
        <p className="text-center text-xs text-muted-foreground">
          Lost your device? Ask a workspace admin to contact support to reset your second factor.
        </p>
      </form>
    </AuthShell>
  );
}
