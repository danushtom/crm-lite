"use client";

import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Skeleton } from "@dracara/ui";
import { ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { normalizeTotp } from "@/lib/mfa";
import { createClient } from "@/lib/supabase/client";

type Enrollment = { factorId: string; qrCode: string; secret: string };

/**
 * Turn two-factor authentication (an authenticator app, TOTP) on or off for your own account.
 * Once on, every sign-in needs a code, and the database refuses a session that has not used one
 * (20260920010000_enforce_mfa.sql).
 */
export function TwoFactorCard() {
  const [loading, setLoading] = useState(true);
  const [verifiedId, setVerifiedId] = useState<string | null>(null);
  const [enrollment, setEnrollment] = useState<Enrollment | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const { data } = await createClient().auth.mfa.listFactors();
    setVerifiedId(data?.totp.find((f) => f.status === "verified")?.id ?? null);
    setLoading(false);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function start() {
    setBusy(true);
    setError(null);
    const supabase = createClient();
    // An abandoned earlier attempt leaves an unverified factor behind; clear it first, or
    // enrolling again fails on the duplicate.
    const { data: existing } = await supabase.auth.mfa.listFactors();
    for (const factor of existing?.all ?? []) {
      if (factor.status !== "verified") await supabase.auth.mfa.unenroll({ factorId: factor.id });
    }
    const { data, error: enrollError } = await supabase.auth.mfa.enroll({
      factorType: "totp",
      friendlyName: `Authenticator ${new Date().toISOString().slice(0, 10)}`,
    });
    setBusy(false);
    if (enrollError || !data) {
      setError(enrollError?.message ?? "Could not start setup");
      return;
    }
    setEnrollment({ factorId: data.id, qrCode: data.totp.qr_code, secret: data.totp.secret });
  }

  async function confirm(e: React.FormEvent) {
    e.preventDefault();
    const digits = normalizeTotp(code);
    if (!enrollment || !digits) {
      setError("Enter the 6-digit code your app shows.");
      return;
    }
    setBusy(true);
    setError(null);
    const { error: verifyError } = await createClient().auth.mfa.challengeAndVerify({
      factorId: enrollment.factorId,
      code: digits,
    });
    setBusy(false);
    if (verifyError) {
      setError("That code did not match. Check your phone's clock is set automatically, then try the current code.");
      return;
    }
    setEnrollment(null);
    setCode("");
    toast.success("Two-factor authentication is on", { description: "You'll be asked for a code each time you sign in." });
    await refresh();
  }

  async function disable() {
    if (!verifiedId) return;
    setBusy(true);
    const { error: unenrollError } = await createClient().auth.mfa.unenroll({ factorId: verifiedId });
    setBusy(false);
    if (unenrollError) {
      toast.error("Could not turn off two-factor authentication", { description: unenrollError.message });
      return;
    }
    toast.success("Two-factor authentication is off");
    await refresh();
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div>
          <CardTitle className="flex items-center gap-2 text-base">
            Two-factor authentication
            {verifiedId ? <Badge variant="secondary">On</Badge> : null}
          </CardTitle>
          <CardDescription>
            Ask for a code from an authenticator app (Google Authenticator, 1Password, Authy) each time you sign in.
          </CardDescription>
        </div>
        <ShieldCheck className="h-5 w-5 text-muted-foreground" aria-hidden />
      </CardHeader>
      <CardContent className="space-y-4">
        {loading ? (
          <Skeleton className="h-9 w-40" />
        ) : verifiedId ? (
          <Button variant="outline" onClick={disable} disabled={busy}>
            Turn off
          </Button>
        ) : enrollment ? (
          <form onSubmit={confirm} className="grid gap-4 sm:grid-cols-[auto,1fr] sm:items-start">
            {/* Supabase returns the QR code as an SVG data URL. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={enrollment.qrCode} alt="QR code to add this account to your authenticator app" className="h-40 w-40 rounded-lg border border-border bg-white p-2" />
            <div className="space-y-3 text-sm">
              <p>1. Scan the code with your authenticator app.</p>
              <p className="text-muted-foreground">
                Can&apos;t scan? Enter this key instead:{" "}
                <code className="break-all rounded bg-muted px-1 py-0.5 text-xs">{enrollment.secret}</code>
              </p>
              <label htmlFor="totp-confirm" className="block">
                2. Enter the 6-digit code it shows.
              </label>
              <div className="flex gap-2">
                <Input
                  id="totp-confirm"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={7}
                  placeholder="123456"
                  className="w-32 tracking-widest"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                />
                <Button type="submit" disabled={busy}>
                  Turn on
                </Button>
                <Button type="button" variant="ghost" onClick={() => setEnrollment(null)} disabled={busy}>
                  Cancel
                </Button>
              </div>
            </div>
          </form>
        ) : (
          <Button onClick={start} disabled={busy}>
            Set up two-factor authentication
          </Button>
        )}
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
      </CardContent>
    </Card>
  );
}
