"use client";

import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input } from "@dracara/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarCheck, CircleAlert, Link2, Loader2, Unlink } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { ApiError, apiFetch } from "@/lib/api";
import { selectClass } from "@/components/shared/entity-drawer";
import { useApiMutation } from "@/lib/use-api-mutation";

type Me = {
  id: string;
  email: string | null;
  full_name: string;
  role: string;
  timezone: string;
  calendar_connected: boolean;
};

const TIMEZONES = [
  "Asia/Kolkata",
  "Asia/Dubai",
  "Asia/Singapore",
  "Asia/Tokyo",
  "Europe/London",
  "Europe/Berlin",
  "America/New_York",
  "America/Chicago",
  "America/Los_Angeles",
  "Australia/Sydney",
];

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
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Settings</h1>
        <p className="mt-1 text-muted-foreground">Your profile and connected services.</p>
      </div>

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
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : (
            <>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <label htmlFor="me-name" className="text-xs font-bold uppercase tracking-widest text-muted-foreground">
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
                  <label htmlFor="me-tz" className="text-xs font-bold uppercase tracking-widest text-muted-foreground">
                    Timezone
                  </label>
                  <select
                    id="me-tz"
                    className={selectClass}
                    value={timezone}
                    onChange={(e) => setTimezone(e.target.value)}
                  >
                    {TIMEZONES.map((t) => (
                      <option key={t} value={t}>
                        {t.replace("_", " ")}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="flex items-center justify-between border-t border-border/50 pt-4">
                <p className="text-xs text-muted-foreground">
                  Signed in as {me?.email} · <span className="capitalize">{me?.role}</span>
                </p>
                <Button
                  size="sm"
                  disabled={!dirty || saveProfile.isPending}
                  onClick={() => saveProfile.mutate()}
                >
                  {saveProfile.isPending ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
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
              size="sm"
              className="gap-2"
              disabled={connect.isPending}
              onClick={() => connect.mutate()}
            >
              <Link2 className="h-4 w-4" />
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
