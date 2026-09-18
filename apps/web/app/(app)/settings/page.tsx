"use client";

import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Skeleton,
  fieldLabel,
  primaryButton,
} from "@dracara/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarCheck, CircleAlert, Link2, Loader2, Unlink } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { ApiError, apiFetch } from "@/lib/api";
import { selectClass } from "@/components/shared/entity-drawer";
import { CaptureKeysCard } from "@/components/settings/capture-keys-card";
import { BillingSummaryCard } from "@/components/billing/billing-summary-card";
import { useApiMutation } from "@/lib/use-api-mutation";
import { browserTimezone, timezoneLabel, timezoneOptions } from "@/lib/timezones";

type Me = {
  id: string;
  email: string | null;
  full_name: string;
  role: string;
  timezone: string;
  calendar_connected: boolean;
  permissions?: string[];
  is_admin?: boolean;
};

type Organization = {
  id: string;
  name: string;
  slug: string | null;
};

export default function SettingsPage() {
  const qc = useQueryClient();

  const { data: me, isLoading } = useQuery({
    queryKey: ["me"],
    queryFn: () => apiFetch<Me>("/auth/me"),
  });

  const [fullName, setFullName] = useState("");
  const [timezone, setTimezone] = useState("Asia/Kolkata");

  useEffect(() => {
    if (!me) return;
    setFullName(me.full_name ?? "");
    setTimezone(me.timezone ?? "Asia/Kolkata");
  }, [me]);

  const saveProfile = useApiMutation({
    errorTitle: "Could not save your profile",
    mutationFn: () =>
      apiFetch<Me>("/auth/me", {
        method: "PATCH",
        body: JSON.stringify({ full_name: fullName.trim(), timezone }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["me"] });
      // The follow-up queues are computed against this zone, so they are now stale.
      qc.invalidateQueries({ queryKey: ["dashboard-followups"] });
      toast.success("Profile saved");
    },
  });

  const connect = useApiMutation({
    errorTitle: "Could not start the Google connection",
    mutationFn: () => apiFetch<{ authorize_url: string }>("/auth/google/authorize-url"),
    onSuccess: ({ authorize_url }) => {
      window.location.href = authorize_url;
    },
    onError: (error: Error) => {
      // A server without Google configured is the common case; say so plainly.
      const detail = error instanceof ApiError ? error.message : "Unexpected error";
      toast.error("Google Calendar is not available", { description: detail });
    },
  });

  const disconnect = useApiMutation({
    errorTitle: "Could not disconnect Google Calendar",
    mutationFn: () => apiFetch("/auth/google", { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["me"] });
      toast.success("Google Calendar disconnected", {
        description: "Meetings already synced are kept.",
      });
    },
  });

  const dirty = Boolean(me) && (fullName !== (me?.full_name ?? "") || timezone !== me?.timezone);

  return (
    <div className="max-w-3xl space-y-6">
      <p className="text-sm text-muted-foreground">
        Your profile, your workspace, and connected services.
      </p>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Profile</CardTitle>
          <CardDescription>
            Your timezone decides when the follow-up queue rolls over to the next day — a task
            due today is judged against your midnight, not the server&rsquo;s.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {isLoading ? (
            <div className="grid gap-4 sm:grid-cols-2">
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          ) : (
            <>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <label htmlFor="me-name" className={fieldLabel}>
                    Full name
                  </label>
                  <Input
                    id="me-name"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder="Your name"
                  />
                </div>
                <div className="space-y-2">
                  <label htmlFor="me-tz" className={fieldLabel}>
                    Timezone
                  </label>
                  <select
                    id="me-tz"
                    className={selectClass}
                    value={timezone}
                    onChange={(e) => setTimezone(e.target.value)}
                  >
                    {timezoneOptions(me?.timezone).map((t) => (
                      <option key={t} value={t}>
                        {timezoneLabel(t)}
                      </option>
                    ))}
                  </select>
                  <BrowserTimezoneHint current={timezone} onUse={setTimezone} />
                </div>
              </div>

              <div className="flex items-center justify-between border-t border-border/50 pt-4">
                <p className="text-xs text-muted-foreground">
                  Signed in as {me?.email} · <span className="capitalize">{me?.role}</span>
                </p>
                <Button
                  className={primaryButton}
                  disabled={!dirty || saveProfile.isPending}
                  onClick={() => saveProfile.mutate()}
                >
                  {saveProfile.isPending ? (
                    <>
                      <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
                      Saving…
                    </>
                  ) : (
                    "Save changes"
                  )}
                </Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <WorkspaceCard />

      <BillingSummaryCard />

      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-4">
          <div>
            <CardTitle className="text-base">Recently deleted</CardTitle>
            <CardDescription>Restore leads, opportunities, contacts and companies that were deleted.</CardDescription>
          </div>
          <Button asChild variant="outline" size="sm">
            <Link href="/recently-deleted">Open</Link>
          </Button>
        </CardHeader>
      </Card>

      <CaptureKeysCard />

      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-4">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              Google Calendar
              {me?.calendar_connected ? (
                <Badge className="bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200">
                  Connected
                </Badge>
              ) : (
                <Badge variant="outline">Not connected</Badge>
              )}
            </CardTitle>
            <CardDescription>
              Pulls your upcoming events in as meetings, so a call booked in Calendar shows up
              against the deal without being entered twice.
            </CardDescription>
          </div>
          <CalendarCheck className="h-8 w-8 shrink-0 text-muted-foreground/40" />
        </CardHeader>
        <CardContent className="space-y-4">
          {me?.calendar_connected ? (
            <Button
              variant="outline"
              size="sm"
              className="gap-2"
              disabled={disconnect.isPending}
              onClick={() => disconnect.mutate()}
            >
              <Unlink className="h-4 w-4" />
              Disconnect
            </Button>
          ) : (
            <Button
              className={primaryButton}
              disabled={connect.isPending}
              onClick={() => connect.mutate()}
            >
              <Link2 className="h-3.5 w-3.5" />
              {connect.isPending ? "Opening Google…" : "Connect Google Calendar"}
            </Button>
          )}

          <div className="flex gap-2 rounded-lg border border-border/60 bg-muted/20 p-3 text-xs text-muted-foreground">
            <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" />
            <p>
              Requires <code className="rounded bg-muted px-1">GOOGLE_CLIENT_ID</code>,{" "}
              <code className="rounded bg-muted px-1">GOOGLE_CLIENT_SECRET</code> and{" "}
              <code className="rounded bg-muted px-1">GOOGLE_REDIRECT_URI</code> on the API.
              Without them this button reports that the server has no Google configuration
              rather than failing silently.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

/**
 * The workspace name.
 *
 * It was set once at signup and there was no way to see or change it afterwards — the
 * organization row had no read or update endpoint at all. It matters beyond cosmetics: every
 * AI voice agent's recording disclosure names the organization, so a placeholder here is what
 * a prospect hears on the phone.
 */
function WorkspaceCard() {
  const qc = useQueryClient();
  const [name, setName] = useState("");

  const { data: org, isLoading, error } = useQuery({
    queryKey: ["organization"],
    queryFn: () => apiFetch<Organization>("/organizations/me"),
    retry: false,
  });

  useEffect(() => {
    if (org) setName(org.name);
  }, [org]);

  const save = useApiMutation({
    errorTitle: "Could not rename this workspace",
    mutationFn: () =>
      apiFetch<Organization>("/organizations/me", {
        method: "PATCH",
        body: JSON.stringify({ name: name.trim() }),
      }),
    onSuccess: (saved) => {
      qc.invalidateQueries({ queryKey: ["organization"] });
      toast.success("Workspace renamed", { description: saved.name });
    },
  });

  const dirty = Boolean(org) && name.trim() !== org?.name && name.trim().length > 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Workspace</CardTitle>
        <CardDescription>
          The name your team and your AI voice agents identify themselves by. Only a full-access
          role may change it.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading ? (
          <Skeleton className="h-16 w-full max-w-sm" />
        ) : error ? (
          <p className="text-sm text-destructive">{(error as Error).message}</p>
        ) : (
          <>
            <div className="max-w-sm space-y-2">
              <label htmlFor="org-name" className={fieldLabel}>
                Workspace name
              </label>
              <Input
                id="org-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Acme Inc"
              />
            </div>
            <div className="flex justify-end border-t border-border/50 pt-4">
              <Button
                className={primaryButton}
                disabled={!dirty || save.isPending}
                onClick={() => save.mutate()}
              >
                {save.isPending ? "Saving…" : "Save changes"}
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

/** Offers the browser's zone when it differs from the selected one -- one click to fix it. */
function BrowserTimezoneHint({ current, onUse }: { current: string; onUse: (zone: string) => void }) {
  const [detected, setDetected] = useState<string | undefined>();
  useEffect(() => setDetected(browserTimezone()), []);
  if (!detected || detected === current) return null;
  return (
    <button
      type="button"
      className="text-xs text-muted-foreground underline underline-offset-4 hover:text-foreground"
      onClick={() => onUse(detected)}
    >
      Use this device&rsquo;s timezone ({timezoneLabel(detected)})
    </button>
  );
}
