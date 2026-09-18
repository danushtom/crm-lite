"use client";

import type { EmailOtpType } from "@supabase/supabase-js";
import { AuthLink, AuthShell } from "@/components/auth/auth-shell";
import { safeNext } from "@/lib/auth";
import { createClient } from "@/lib/supabase/client";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

/**
 * The one landing page for every emailed auth link: signup confirmation, password reset and
 * team invites. Supabase can deliver the session three different ways depending on how the
 * link was minted, and all three are handled here so no email template has to change:
 *
 * - `?token_hash=&type=` -- a customised "token hash" email template; verified here.
 * - `#access_token=&refresh_token=` -- the implicit flow. Admin-sent invites always arrive this
 *   way: they are minted server-side, so there is no browser PKCE verifier to pair with.
 * - `?code=` -- the PKCE flow, used by signup and reset (started in this browser). The
 *   Supabase client usually exchanges it on its own as it initialises; the explicit exchange
 *   below is the fallback for when it has not.
 */
export default function ConfirmInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    // Strict mode runs effects twice in development; a code or token is single-use.
    if (started.current) return;
    started.current = true;

    const next = safeNext(searchParams.get("next"));
    const hash = new URLSearchParams(window.location.hash.replace(/^#/, ""));

    async function establish(): Promise<string | null> {
      const linkError = searchParams.get("error_description") || hash.get("error_description");
      if (linkError) return linkError;

      const supabase = createClient();
      const tokenHash = searchParams.get("token_hash");
      const type = searchParams.get("type") as EmailOtpType | null;
      if (tokenHash && type) {
        const { error } = await supabase.auth.verifyOtp({ token_hash: tokenHash, type });
        return error?.message ?? null;
      }

      const accessToken = hash.get("access_token");
      const refreshToken = hash.get("refresh_token");
      if (accessToken && refreshToken) {
        const { error } = await supabase.auth.setSession({
          access_token: accessToken,
          refresh_token: refreshToken,
        });
        return error?.message ?? null;
      }

      const { data } = await supabase.auth.getSession();
      if (data.session) return null;

      const code = searchParams.get("code");
      if (code) {
        const { error } = await supabase.auth.exchangeCodeForSession(code);
        return error?.message ?? null;
      }
      return "This link is incomplete. Open it straight from the email, on the device you requested it from.";
    }

    establish().then((message) => {
      if (message) {
        setError(message);
        return;
      }
      // Drop the tokens from the address bar and history before moving on.
      window.history.replaceState(null, "", window.location.pathname);
      router.replace(next);
      router.refresh();
    });
  }, [router, searchParams]);

  if (!error) {
    return (
      <AuthShell title="Signing you in…" description="One moment while we verify your link.">
        <div className="h-1 w-full overflow-hidden rounded bg-muted">
          <div className="h-full w-1/3 animate-pulse rounded bg-[#0A1128] dark:bg-foreground" />
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="That link didn't work"
      description="Links expire and can only be used once."
      footer={
        <>
          <AuthLink href="/forgot-password">Send a new reset link</AuthLink> ·{" "}
          <AuthLink href="/login">Sign in</AuthLink>
        </>
      }
    >
      <p className="text-sm text-destructive">{error}</p>
      <p className="mt-3 text-sm text-muted-foreground">
        Invited to a workspace? Ask your admin to send the invite again.
      </p>
    </AuthShell>
  );
}
