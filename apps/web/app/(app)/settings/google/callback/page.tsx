"use client";

import { Button, Card, CardContent } from "@dracara/ui";
import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef } from "react";
import { apiFetch } from "@/lib/api";
import { describeError } from "@/lib/use-api-mutation";

/**
 * Where Google sends the browser back after consent.
 *
 * The redirect lands here rather than on the API because the code has to be exchanged as the
 * signed-in user, and a browser redirect carries no bearer token. This page holds the session,
 * so it posts the code to the API and lets the server do the exchange with the client secret.
 */
function CallbackInner() {
  const params = useSearchParams();
  const code = params.get("code");
  const oauthError = params.get("error");

  // React runs effects twice in development; without this the code is exchanged twice and
  // the second attempt fails, because an authorization code is single-use.
  const exchanged = useRef(false);

  const exchange = useMutation({
    mutationFn: (authCode: string) =>
      apiFetch<{ connected: boolean; scope?: string }>("/auth/google/callback", {
        method: "POST",
        body: JSON.stringify({ code: authCode }),
      }),
  });

  useEffect(() => {
    if (!code || exchanged.current) return;
    exchanged.current = true;
    exchange.mutate(code);
  }, [code, exchange]);

  const done = <Link href="/settings" className="underline underline-offset-4">Back to settings</Link>;

  if (oauthError) {
    return (
      <State
        icon={<XCircle className="h-8 w-8 text-destructive" />}
        title="Google declined the connection"
        detail={
          oauthError === "access_denied"
            ? "You cancelled the consent screen. Nothing was changed."
            : oauthError
        }
        action={done}
      />
    );
  }

  if (!code) {
    return (
      <State
        icon={<XCircle className="h-8 w-8 text-destructive" />}
        title="No authorization code"
        detail="This page is the destination Google redirects to; opening it directly does nothing."
        action={done}
      />
    );
  }

  if (exchange.isPending) {
    return (
      <State
        icon={<Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />}
        title="Connecting Google Calendar…"
        detail="Exchanging the authorization code."
      />
    );
  }

  if (exchange.isError) {
    return (
      <State
        icon={<XCircle className="h-8 w-8 text-destructive" />}
        title="Could not complete the connection"
        detail={describeError(exchange.error)}
        action={done}
      />
    );
  }

  return (
    <State
      icon={<CheckCircle2 className="h-8 w-8 text-emerald-500" />}
      title="Google Calendar connected"
      detail="Your upcoming events will start appearing as meetings within the next sync."
      action={
        <Button asChild size="sm">
          <Link href="/calendar">View the calendar</Link>
        </Button>
      }
    />
  );
}

function State({
  icon,
  title,
  detail,
  action,
}: {
  icon: React.ReactNode;
  title: string;
  detail: string;
  action?: React.ReactNode;
}) {
  return (
    <Card className="mx-auto mt-16 max-w-md">
      <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
        {icon}
        <h1 className="text-lg font-semibold">{title}</h1>
        <p className="text-sm text-muted-foreground">{detail}</p>
        {action ? <div className="mt-2">{action}</div> : null}
      </CardContent>
    </Card>
  );
}

export default function GoogleCallbackPage() {
  return (
    <Suspense fallback={<p className="p-8 text-sm text-muted-foreground">Loading…</p>}>
      <CallbackInner />
    </Suspense>
  );
}
