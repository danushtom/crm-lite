"use client";

import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input } from "@dracara/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { formatDistanceToNow, parseISO } from "date-fns";
import { Phone, Plus, ShieldAlert } from "lucide-react";
import { useState } from "react";
import { apiFetch, apiList } from "@/lib/api";
import { useApiMutation } from "@/lib/use-api-mutation";
import { VoiceAgentDrawer } from "@/components/voice-agents/voice-agent-drawer";
import type { CallSummary, PhoneNumber, VoiceAgent } from "@dracara/types";

function ComplianceGate({ children }: { children: React.ReactNode }) {
  const qc = useQueryClient();
  const { data: status, isLoading } = useQuery({
    queryKey: ["voice-agents", "compliance-status"],
    queryFn: () => apiFetch<{ acknowledged: boolean }>("/voice-agents/compliance-status"),
  });

  const ack = useApiMutation({
    errorTitle: "Could not save the acknowledgment",
    mutationFn: () => apiFetch("/voice-agents/compliance-ack", { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["voice-agents", "compliance-status"] }),
  });

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading…</p>;

  if (!status?.acknowledged) {
    return (
      <Card className="border-amber-300 bg-amber-50 dark:border-amber-900 dark:bg-amber-950/20">
        <CardContent className="space-y-3 pt-6">
          <div className="flex items-start gap-3">
            <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
            <div className="space-y-1">
              <p className="text-sm font-semibold">Before you enable AI calling</p>
              <p className="text-sm text-muted-foreground">
                Outbound AI calls are subject to consent and recording-disclosure laws that vary
                by state and country. By continuing, you confirm your organization has a lawful
                basis to record and place AI-assisted calls, and will only enable outbound
                calling for contacts who have consented.
              </p>
            </div>
          </div>
          <Button size="sm" disabled={ack.isPending} onClick={() => ack.mutate()}>
            I acknowledge — enable AI calling
          </Button>
        </CardContent>
      </Card>
    );
  }

  return <>{children}</>;
}

function PhoneNumbersCard() {
  const qc = useQueryClient();
  const { data: numbers } = useQuery({
    queryKey: ["voice-agents", "phone-numbers"],
    queryFn: () => apiFetch<PhoneNumber[]>("/voice-agents/phone-numbers"),
  });
  const [number, setNumber] = useState("");

  const register = useApiMutation({
    errorTitle: "Could not register this number",
    mutationFn: () =>
      apiFetch("/voice-agents/phone-numbers", {
        method: "POST",
        body: JSON.stringify({ e164_number: number.trim() }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["voice-agents", "phone-numbers"] });
      setNumber("");
    },
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Phone numbers</CardTitle>
        <p className="text-sm text-muted-foreground">
          Attach a number you already own in Twilio. Buying a new number isn&rsquo;t built yet.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-2">
          <Input
            placeholder="+14155550100"
            value={number}
            onChange={(e) => setNumber(e.target.value)}
            className="max-w-xs"
          />
          <Button disabled={!number.trim() || register.isPending} onClick={() => register.mutate()}>
            Register
          </Button>
        </div>
        {(numbers ?? []).length > 0 ? (
          <ul className="space-y-1 text-sm">
            {numbers!.map((n) => (
              <li key={n.id} className="flex items-center gap-2">
                <Phone className="h-3.5 w-3.5 text-muted-foreground" />
                {n.e164_number}
                {n.assigned_voice_agent_id ? (
                  <Badge variant="secondary" className="text-[10px]">Assigned</Badge>
                ) : (
                  <Badge variant="outline" className="text-[10px]">Unassigned</Badge>
                )}
              </li>
            ))}
          </ul>
        ) : null}
      </CardContent>
    </Card>
  );
}

function relative(iso: string | null): string {
  if (!iso) return "—";
  try {
    return formatDistanceToNow(parseISO(iso), { addSuffix: true });
  } catch {
    return "—";
  }
}

const STATUS_LABEL: Record<string, string> = {
  queued: "Queued",
  ringing: "Ringing",
  in_progress: "In progress",
  completed: "Completed",
  failed: "Failed",
  no_consent_blocked: "Blocked (no consent)",
};

function CallLogCard() {
  const { data: calls } = useQuery({
    queryKey: ["voice-agents", "calls"],
    queryFn: () => apiList<CallSummary>("/voice-agents/calls?limit=20"),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent calls</CardTitle>
      </CardHeader>
      <CardContent className="overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead className="bg-muted/50">
            <tr>
              <th className="px-3 py-2 text-left">Direction</th>
              <th className="px-3 py-2 text-left">Number</th>
              <th className="px-3 py-2 text-left">Status</th>
              <th className="px-3 py-2 text-left">Duration</th>
              <th className="px-3 py-2 text-left">Outcome</th>
              <th className="px-3 py-2 text-left">When</th>
            </tr>
          </thead>
          <tbody>
            {(calls ?? []).length === 0 ? (
              <tr>
                <td colSpan={6} className="px-3 py-6 text-center text-muted-foreground">
                  No calls yet.
                </td>
              </tr>
            ) : (
              calls!.map((c) => (
                <tr key={c.id} className="border-t border-border/80">
                  <td className="px-3 py-2 capitalize">{c.direction}</td>
                  <td className="px-3 py-2">{c.direction === "outbound" ? c.to_number : c.from_number}</td>
                  <td className="px-3 py-2">
                    <Badge
                      variant={c.status === "completed" ? "secondary" : c.status === "no_consent_blocked" ? "destructive" : "outline"}
                      className="text-[10px]"
                    >
                      {STATUS_LABEL[c.status] ?? c.status}
                    </Badge>
                  </td>
                  <td className="px-3 py-2">{c.duration_seconds ? `${c.duration_seconds}s` : "—"}</td>
                  <td className="px-3 py-2 text-muted-foreground">{c.outcome ?? "—"}</td>
                  <td className="px-3 py-2 text-muted-foreground">{relative(c.created_at)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

export default function VoiceAgentsPage() {
  const { data: agents, isLoading, error } = useQuery({
    queryKey: ["voice-agents"],
    queryFn: () => apiFetch<VoiceAgent[]>("/voice-agents"),
    retry: false,
  });

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">AI Agents</h1>
        <p className="mt-1 text-muted-foreground">
          AI voice agents that place and receive phone calls. Not to be confused with{" "}
          <span className="font-medium">Agents</span> under User management, which are your team.
        </p>
      </div>

      <ComplianceGate>
        <div className="grid gap-6 lg:grid-cols-2">
          <PhoneNumbersCard />

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0">
              <CardTitle>Voice agents</CardTitle>
              <VoiceAgentDrawer
                trigger={
                  <Button size="sm">
                    <Plus className="mr-1.5 h-4 w-4" />
                    New agent
                  </Button>
                }
              />
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <p className="text-sm text-muted-foreground">Loading…</p>
              ) : error ? (
                <p className="text-sm text-destructive">{(error as Error).message}</p>
              ) : (agents ?? []).length === 0 ? (
                <p className="text-sm text-muted-foreground">No voice agents yet.</p>
              ) : (
                <ul className="space-y-2">
                  {agents!.map((a) => (
                    <li
                      key={a.id}
                      className="flex items-center justify-between rounded-lg border border-border/60 px-3 py-2"
                    >
                      <div>
                        <p className="text-sm font-medium">{a.name}</p>
                        <p className="text-xs text-muted-foreground">
                          <span className="capitalize">{a.direction}</span>
                          {a.platform_assistant_id ? "" : " · not yet connected to the voice platform"}
                        </p>
                      </div>
                      <VoiceAgentDrawer
                        agent={a}
                        trigger={
                          <Button variant="ghost" size="sm">
                            Edit
                          </Button>
                        }
                      />
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="mt-6">
          <CallLogCard />
        </div>
      </ComplianceGate>
    </div>
  );
}
