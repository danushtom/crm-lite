"use client";

import type { PhoneNumber, VoiceAgent, VoiceAgentDataAccess, VoiceScript } from "@dracara/types";
import { Badge, Button, Card, CardContent, Skeleton, cn, primaryButton } from "@dracara/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Database, FileText, Loader2, Pause, Phone, PhoneCall, Play, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { apiFetch } from "@/lib/api";
import { selectClass } from "@/components/shared/entity-drawer";
import { AgentAvatar } from "@/components/voice-agents/agent-avatar";
import { AgentDocuments } from "@/components/voice-agents/agent-documents";
import { AgentCallLog } from "@/components/voice-agents/agent-call-log";
import { DataAccessEditor } from "@/components/voice-agents/data-access-editor";
import { PlaceCallDrawer } from "@/components/voice-agents/place-call-drawer";
import { EMPTY_SCRIPT, ScriptBuilder } from "@/components/voice-agents/script-builder";
import { ScriptPreviewPanel } from "@/components/voice-agents/script-preview";
import { agentStatus, goalLabel } from "@/lib/voice-agents";
import { useApiMutation } from "@/lib/use-api-mutation";

type Tab = "script" | "data" | "knowledge" | "calls";

const TABS: { key: Tab; label: string; icon: typeof FileText }[] = [
  { key: "script", label: "Script", icon: FileText },
  { key: "data", label: "Data access", icon: Database },
  { key: "knowledge", label: "Knowledge", icon: FileText },
  { key: "calls", label: "Calls", icon: PhoneCall },
];

export default function AgentPage() {
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <AgentDetail />
    </Suspense>
  );
}

function AgentDetail() {
  const { id } = useParams<{ id: string }>();
  const params = useSearchParams();
  const router = useRouter();
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>((TABS.find((t) => t.key === params.get("tab"))?.key ?? "script") as Tab);

  const { data: agent, isLoading, isError } = useQuery({
    queryKey: ["voice-agents", id],
    queryFn: () => apiFetch<VoiceAgent>(`/voice-agents/${id}`),
  });

  const { data: numbers = [] } = useQuery({
    queryKey: ["voice-agents", "phone-numbers"],
    queryFn: () => apiFetch<PhoneNumber[]>("/voice-agents/phone-numbers"),
  });

  const [draft, setDraft] = useState<{
    persona_name: string;
    role_title: string;
    script: VoiceScript;
    data_access: VoiceAgentDataAccess;
  } | null>(null);

  /** The agent exactly as stored, in the shape the editor works in. */
  const saved = useMemo(
    () =>
      agent
        ? {
            persona_name: agent.persona_name ?? "",
            role_title: agent.role_title ?? "",
            script: { ...EMPTY_SCRIPT, ...(agent.script ?? {}) },
            data_access: {
              tools: agent.data_access?.tools ?? {},
              lead_fields: agent.data_access?.lead_fields ?? [],
            },
          }
        : null,
    [agent]
  );

  // Re-seeded whenever the stored agent changes, including right after a save, so the
  // unsaved-changes bar below always means exactly that.
  useEffect(() => {
    if (saved) setDraft(saved);
  }, [saved]);

  const dirty = useMemo(
    () => Boolean(saved && draft) && JSON.stringify(draft) !== JSON.stringify(saved),
    [saved, draft]
  );

  const save = useApiMutation({
    errorTitle: "Could not save this script",
    mutationFn: () =>
      apiFetch<VoiceAgent>(`/voice-agents/${id}`, {
        method: "PATCH",
        headers: { "If-Match": `"${agent!.version}"` },
        body: JSON.stringify(draft),
      }),
    onSuccess: (saved) => {
      qc.setQueryData(["voice-agents", id], saved);
      qc.invalidateQueries({ queryKey: ["voice-agents"] });
      toast.success("Script saved", { description: `${saved.persona_name || saved.name} is briefed.` });
    },
  });

  const patchAgent = useApiMutation({
    errorTitle: "Could not update this agent",
    mutationFn: (changes: Partial<VoiceAgent>) =>
      apiFetch<VoiceAgent>(`/voice-agents/${id}`, {
        method: "PATCH",
        headers: { "If-Match": `"${agent!.version}"` },
        body: JSON.stringify(changes),
      }),
    onSuccess: (saved) => {
      qc.setQueryData(["voice-agents", id], saved);
      qc.invalidateQueries({ queryKey: ["voice-agents"] });
    },
  });

  const remove = useApiMutation({
    errorTitle: "Could not remove this agent",
    mutationFn: () =>
      apiFetch(`/voice-agents/${id}`, { method: "DELETE", headers: { "If-Match": `"${agent!.version}"` } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["voice-agents"] });
      toast.success("Agent removed", { description: "Its number is free to assign again." });
      router.push("/voice-agents");
    },
  });

  if (isLoading || !draft) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }
  if (isError || !agent) {
    return <p className="text-sm text-destructive">Could not load this agent.</p>;
  }

  const status = agentStatus(agent);
  const assignedNumber = numbers.find((n) => n.id === agent.phone_number_id);

  return (
    <div className="space-y-5 pb-24">
      <Link
        href="/voice-agents"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" /> AI team
      </Link>

      {/* --- Who this is ------------------------------------------------------------------ */}
      <Card>
        <CardContent className="flex flex-wrap items-start gap-4 py-5">
          <AgentAvatar
            name={agent.persona_name || agent.name}
            avatarKey={agent.avatar_key}
            size="xl"
            status={status.tone}
          />
          <div className="min-w-0 flex-1 space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-xl font-semibold tracking-tight">{agent.persona_name || agent.name}</h1>
              <Badge variant={status.tone === "ready" ? "secondary" : "outline"}>{status.label}</Badge>
            </div>
            <p className="text-sm text-muted-foreground">
              {agent.role_title || "Voice agent"} · {goalLabel(agent.script?.goal ?? "custom")}
            </p>
            <p className="text-xs text-muted-foreground">
              Known internally as {agent.name} · {status.hint}
            </p>
            <p className="pt-1 text-xs text-muted-foreground">
              Opens every call with: <span className="italic">&ldquo;{agent.disclosure_script}&rdquo;</span>
            </p>
          </div>
          <div className="flex flex-col items-stretch gap-2">
            {agent.phone_number_id && agent.is_active ? (
              <PlaceCallDrawer
                agent={agent}
                trigger={
                  <Button className={primaryButton} size="sm">
                    <PhoneCall className="h-3.5 w-3.5" />
                    Place a call
                  </Button>
                }
              />
            ) : null}
            <Button
              variant="outline"
              size="sm"
              disabled={patchAgent.isPending}
              onClick={() => patchAgent.mutate({ is_active: !agent.is_active })}
            >
              {agent.is_active ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
              {agent.is_active ? "Pause" : "Resume"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* --- Phone number --------------------------------------------------------------- */}
      <Card>
        <CardContent className="flex flex-wrap items-center gap-3 py-4">
          <Phone className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium">Phone number</p>
            <p className="text-xs text-muted-foreground">
              {assignedNumber
                ? `Calls go out from ${assignedNumber.e164_number}, and calls to it reach this agent.`
                : "Without a number this agent cannot place or take calls."}
            </p>
          </div>
          <select
            aria-label="Phone number"
            className={cn(selectClass, "w-56")}
            value={agent.phone_number_id ?? ""}
            disabled={patchAgent.isPending}
            onChange={(e) => patchAgent.mutate({ phone_number_id: e.target.value || null })}
          >
            <option value="">No number assigned</option>
            {numbers
              .filter((n) => !n.assigned_voice_agent_id || n.assigned_voice_agent_id === agent.id)
              .map((n) => (
                <option key={n.id} value={n.id}>
                  {n.e164_number}
                </option>
              ))}
          </select>
        </CardContent>
      </Card>

      {/* --- Tabs ----------------------------------------------------------------------- */}
      <div role="tablist" aria-label="Agent configuration" className="flex flex-wrap gap-1 border-b border-border">
        {TABS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            onClick={() => {
              setTab(key);
              router.replace(`/voice-agents/${id}?tab=${key}`);
            }}
            className={cn(
              "-mb-px flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium",
              tab === key
                ? "border-[hsl(var(--primary))] text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
          </button>
        ))}
      </div>

      {tab === "script" ? (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
          <Card>
            <CardContent className="py-5">
              <ScriptBuilder script={draft.script} onChange={(script) => setDraft({ ...draft, script })} />
            </CardContent>
          </Card>
          <div className="lg:sticky lg:top-20 lg:self-start">
            <Card>
              <CardContent className="py-5">
                <ScriptPreviewPanel
                  name={agent.name}
                  personaName={draft.persona_name}
                  roleTitle={draft.role_title}
                  script={draft.script}
                  dataAccess={draft.data_access}
                />
              </CardContent>
            </Card>
          </div>
        </div>
      ) : null}

      {tab === "data" ? (
        <Card>
          <CardContent className="py-5">
            <DataAccessEditor
              value={draft.data_access}
              onChange={(data_access) => setDraft({ ...draft, data_access })}
            />
          </CardContent>
        </Card>
      ) : null}

      {tab === "knowledge" ? (
        <Card>
          <CardContent className="space-y-3 py-5">
            <div>
              <h3 className="text-sm font-semibold">Documents it can quote from</h3>
              <p className="text-xs text-muted-foreground">
                Pricing sheets, packages, FAQs. The agent searches these mid-call instead of
                guessing — and says it will follow up when they do not cover the question.
              </p>
            </div>
            {draft.data_access.tools?.search_knowledge_base ? null : (
              <p className="rounded-lg border border-amber-500/40 bg-amber-50/60 p-3 text-xs text-amber-900 dark:bg-amber-950/20 dark:text-amber-200">
                Document search is switched off for this agent, so it will not read these. Turn it
                on under <span className="font-medium">Data access</span>.
              </p>
            )}
            <AgentDocuments voiceAgentId={agent.id} />
          </CardContent>
        </Card>
      ) : null}

      {tab === "calls" ? <AgentCallLog agentId={agent.id} /> : null}

      {/* --- Save bar ------------------------------------------------------------------- */}
      {dirty ? (
        <div className="sticky bottom-4 z-20 mx-auto flex w-fit max-w-full flex-wrap items-center gap-3 rounded-xl border border-border bg-card px-4 py-2.5 shadow-lg">
          <span className="text-sm">Unsaved changes to this agent&apos;s script.</span>
          <Button variant="ghost" size="sm" onClick={() => setDraft(saved)} disabled={save.isPending}>
            Discard
          </Button>
          <Button className={primaryButton} size="sm" disabled={save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
            Save and re-brief
          </Button>
        </div>
      ) : null}

      <div className="border-t border-border/60 pt-4">
        <Button
          variant="ghost"
          size="sm"
          className="gap-1.5 text-destructive hover:bg-destructive/10 hover:text-destructive"
          disabled={remove.isPending}
          onClick={() => remove.mutate()}
        >
          <Trash2 className="h-3.5 w-3.5" />
          Remove from the team
        </Button>
      </div>
    </div>
  );
}
