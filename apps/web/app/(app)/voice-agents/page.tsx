"use client";

import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Input,
  Skeleton,
  cn,
  primaryButton,
  toolbarButton,
} from "@dracara/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Phone, PhoneOutgoing, Plus, ShieldAlert, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { apiFetch, apiPage } from "@/lib/api";
import { CALL_STATUS_LABEL, CALL_STATUS_TONE } from "@/lib/calls";
import { formatDateTime, formatDuration } from "@/lib/format";
import { useApiMutation } from "@/lib/use-api-mutation";
import { DataTable, type Column } from "@/components/shared/data-table";
import { ListToolbar } from "@/components/shared/list-toolbar";
import { PageSection } from "@/components/shared/page-section";
import { TablePagination } from "@/components/shared/table-pagination";
import { SelectField } from "@/components/shared/entity-drawer";
import { CallDetailDrawer } from "@/components/voice-agents/call-detail-drawer";
import { PlaceCallDrawer } from "@/components/voice-agents/place-call-drawer";
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

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

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
          <Button className={primaryButton} disabled={ack.isPending} onClick={() => ack.mutate()}>
            {ack.isPending ? "Saving…" : "I acknowledge — enable AI calling"}
          </Button>
        </CardContent>
      </Card>
    );
  }

  return <>{children}</>;
}

function PhoneNumbersCard() {
  const qc = useQueryClient();
  const { data: numbers, isLoading } = useQuery({
    queryKey: ["voice-agents", "phone-numbers"],
    queryFn: () => apiFetch<PhoneNumber[]>("/voice-agents/phone-numbers"),
  });
  const [number, setNumber] = useState("");

  const invalidate = () => qc.invalidateQueries({ queryKey: ["voice-agents", "phone-numbers"] });

  const register = useApiMutation({
    errorTitle: "Could not register this number",
    mutationFn: () =>
      apiFetch("/voice-agents/phone-numbers", {
        method: "POST",
        body: JSON.stringify({ e164_number: number.trim() }),
      }),
    onSuccess: () => {
      invalidate();
      setNumber("");
      toast.success("Number registered");
    },
  });

  const release = useApiMutation({
    errorTitle: "Could not remove this number",
    mutationFn: (id: string) =>
      apiFetch(`/voice-agents/phone-numbers/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      invalidate();
      toast.success("Number removed");
    },
  });

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Phone numbers</CardTitle>
        <p className="text-sm text-muted-foreground">
          Attach a number you already own in Twilio. Buying a new number isn&rsquo;t built yet.
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <Input
            placeholder="+14155550100"
            value={number}
            onChange={(e) => setNumber(e.target.value)}
            className="h-8 max-w-[200px] rounded-md border-border/70 text-xs"
          />
          <Button
            variant="outline"
            className={cn(toolbarButton, "font-semibold")}
            disabled={!number.trim() || register.isPending}
            onClick={() => register.mutate()}
          >
            {register.isPending ? "Registering…" : "Register"}
          </Button>
        </div>

        {isLoading ? (
          <Skeleton className="h-8 w-full" />
        ) : (numbers ?? []).length === 0 ? (
          <p className="text-xs text-muted-foreground">No numbers registered yet.</p>
        ) : (
          <ul className="space-y-1">
            {numbers!.map((n) => (
              <li
                key={n.id}
                className="flex items-center gap-2 rounded-md border border-border/60 px-2.5 py-1.5 text-sm"
              >
                <Phone className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                <span className="flex-1 font-medium tabular-nums">{n.e164_number}</span>
                {n.assigned_voice_agent_id ? (
                  <Badge variant="secondary" className="text-[10px]">
                    Assigned
                  </Badge>
                ) : (
                  <Badge variant="outline" className="text-[10px]">
                    Unassigned
                  </Badge>
                )}
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 text-muted-foreground hover:text-destructive"
                  aria-label={`Remove ${n.e164_number}`}
                  // The API returns 409 while a number is still assigned; disabling here says
                  // so up front instead of surfacing it as an error toast.
                  disabled={Boolean(n.assigned_voice_agent_id) || release.isPending}
                  title={
                    n.assigned_voice_agent_id
                      ? "Unassign this number from its agent first."
                      : undefined
                  }
                  onClick={() => release.mutate(n.id)}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

const STATUS_FILTER_OPTIONS = [
  { value: "completed", label: "Completed" },
  { value: "in_progress", label: "In progress" },
  { value: "queued", label: "Queued" },
  { value: "ringing", label: "Ringing" },
  { value: "failed", label: "Failed" },
  { value: "no_consent_blocked", label: "Blocked — no consent" },
];

function CallLog({ agents }: { agents: VoiceAgent[] }) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [agentFilter, setAgentFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const query = new URLSearchParams({
    limit: String(pageSize),
    offset: String((page - 1) * pageSize),
  });
  if (agentFilter) query.set("voice_agent_id", agentFilter);
  if (statusFilter) query.set("status", statusFilter);

  const { data, isLoading, error } = useQuery({
    queryKey: ["voice-agents", "calls", page, pageSize, agentFilter, statusFilter],
    queryFn: () => apiPage<CallSummary>(`/voice-agents/calls?${query.toString()}`),
    retry: false,
  });

  const agentName = (id: string) => agents.find((a) => a.id === id)?.name ?? "—";

  const columns: Column<CallSummary>[] = [
    {
      key: "when",
      header: "When",
      skeletonWidth: "w-32",
      cell: (c) => <span className="text-muted-foreground">{formatDateTime(c.created_at)}</span>,
    },
    {
      key: "agent",
      header: "Agent",
      skeletonWidth: "w-28",
      cell: (c) => agentName(c.voice_agent_id),
    },
    {
      key: "direction",
      header: "Direction",
      skeletonWidth: "w-16",
      cell: (c) => <span className="capitalize">{c.direction}</span>,
    },
    {
      key: "number",
      header: "Number",
      skeletonWidth: "w-28",
      cell: (c) => (
        <span className="tabular-nums">
          {c.direction === "outbound" ? c.to_number : c.from_number}
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      skeletonWidth: "w-20",
      cell: (c) => (
        <Badge
          className={cn("h-5 rounded-md px-2 text-[10px] font-semibold", CALL_STATUS_TONE[c.status])}
        >
          {CALL_STATUS_LABEL[c.status] ?? c.status}
        </Badge>
      ),
    },
    {
      key: "duration",
      header: "Duration",
      skeletonWidth: "w-16",
      cell: (c) => <span className="tabular-nums">{formatDuration(c.duration_seconds)}</span>,
    },
    {
      key: "outcome",
      header: "Outcome",
      cell: (c) => <span className="text-muted-foreground">{c.outcome ?? "—"}</span>,
    },
    {
      key: "actions",
      header: <span className="sr-only">Open</span>,
      className: "text-right",
      skeletonWidth: "w-12",
      cell: (c) => (
        <CallDetailDrawer
          callId={c.id}
          trigger={
            <Button variant="ghost" size="sm" className="h-8 text-xs">
              Open
            </Button>
          }
        />
      ),
    },
  ];

  // `total` is null when the server could not count cheaply; fall back to what we can prove is
  // there so the footer never claims "of 0" while rows are on screen.
  const total = data?.page?.total ?? (data?.items.length ?? 0) + (page - 1) * pageSize;

  return (
    <PageSection title="Call history" description="Every call placed or received by an agent.">
      <div className="space-y-2.5">
        <ListToolbar
          left={
            <>
              <div className="w-48">
                <SelectField
                  id="call-filter-agent"
                  label="Agent"
                  value={agentFilter}
                  onChange={(v) => {
                    setAgentFilter(v);
                    setPage(1);
                  }}
                  placeholder="All agents"
                  options={agents.map((a) => ({ value: a.id, label: a.name }))}
                />
              </div>
              <div className="w-48">
                <SelectField
                  id="call-filter-status"
                  label="Status"
                  value={statusFilter}
                  onChange={(v) => {
                    setStatusFilter(v);
                    setPage(1);
                  }}
                  placeholder="All statuses"
                  options={STATUS_FILTER_OPTIONS}
                />
              </div>
            </>
          }
        />
        <DataTable
          rows={data?.items ?? []}
          columns={columns}
          isLoading={isLoading}
          error={(error as Error) ?? null}
          emptyMessage={
            agentFilter || statusFilter
              ? "No calls match these filters."
              : "No calls yet. Place one from an agent above."
          }
          minWidth="min-w-[880px]"
        />
        <TablePagination
          page={page}
          pageCount={Math.max(1, Math.ceil(total / pageSize))}
          pageSize={pageSize}
          total={total}
          onPageChange={setPage}
          onPageSizeChange={(size) => {
            setPageSize(size);
            setPage(1);
          }}
        />
      </div>
    </PageSection>
  );
}

export default function VoiceAgentsPage() {
  const { data: agents, isLoading, error } = useQuery({
    queryKey: ["voice-agents"],
    queryFn: () => apiFetch<VoiceAgent[]>("/voice-agents"),
    retry: false,
  });

  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground">
        AI voice agents that place and receive phone calls. Not to be confused with{" "}
        <span className="font-medium text-foreground">User management</span>, which is your team.
      </p>

      <ComplianceGate>
        <div className="space-y-6">
          <div className="grid gap-4 lg:grid-cols-2">
            <PhoneNumbersCard />

            <Card>
              <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-3">
                <div>
                  <CardTitle className="text-base">Voice agents</CardTitle>
                  <p className="text-sm text-muted-foreground">
                    What each agent says, which number it uses, and what it can read.
                  </p>
                </div>
                <VoiceAgentDrawer
                  trigger={
                    <Button variant="outline" className={cn(toolbarButton, "font-semibold")}>
                      <Plus className="h-3.5 w-3.5" />
                      New agent
                    </Button>
                  }
                />
              </CardHeader>
              <CardContent>
                {isLoading ? (
                  <div className="space-y-2">
                    <Skeleton className="h-12 w-full" />
                    <Skeleton className="h-12 w-full" />
                  </div>
                ) : error ? (
                  <p className="text-sm text-destructive">{(error as Error).message}</p>
                ) : (agents ?? []).length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    No voice agents yet. Register a number, then create your first agent.
                  </p>
                ) : (
                  <ul className="space-y-2">
                    {agents!.map((a) => (
                      <li
                        key={a.id}
                        className="flex items-center justify-between gap-2 rounded-lg border border-border/60 px-3 py-2"
                      >
                        <div className="min-w-0">
                          <p className="flex items-center gap-1.5 text-sm font-medium">
                            <span className="truncate">{a.name}</span>
                            {a.is_active ? null : (
                              <Badge variant="secondary" className="text-[10px]">
                                Paused
                              </Badge>
                            )}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            <span className="capitalize">{a.direction}</span>
                            {a.platform_assistant_id
                              ? ""
                              : " · not yet connected to the voice platform"}
                          </p>
                        </div>
                        <div className="flex shrink-0 items-center gap-1">
                          <PlaceCallDrawer
                            agent={a}
                            trigger={
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-8 w-8"
                                aria-label={`Place a call with ${a.name}`}
                              >
                                <PhoneOutgoing className="h-3.5 w-3.5" />
                              </Button>
                            }
                          />
                          <VoiceAgentDrawer
                            agent={a}
                            trigger={
                              <Button variant="ghost" size="sm" className="h-8 text-xs">
                                Edit
                              </Button>
                            }
                          />
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </div>

          <CallLog agents={agents ?? []} />
        </div>
      </ComplianceGate>
    </div>
  );
}
