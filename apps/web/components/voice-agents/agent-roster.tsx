"use client";

import type { CallSummary, PhoneNumber, VoiceAgent } from "@dracara/types";
import { Badge, Button, Card, CardContent, Skeleton, cn, primaryButton } from "@dracara/ui";
import { useQuery } from "@tanstack/react-query";
import { PhoneCall, PhoneOutgoing, Sparkles, UserPlus } from "lucide-react";
import Link from "next/link";
import { apiFetch, apiPage } from "@/lib/api";
import { AgentAvatar } from "@/components/voice-agents/agent-avatar";
import { HireAgentDrawer } from "@/components/voice-agents/hire-agent-drawer";
import { PlaceCallDrawer } from "@/components/voice-agents/place-call-drawer";
import { agentStatus, goalLabel, scriptCompleteness } from "@/lib/voice-agents";

/**
 * The AI team.
 *
 * Cards rather than table rows on purpose: an organization hires several of these, gives them
 * names its customers hear, and needs to see at a glance which one is working, which one is
 * half-configured and which one has nothing to say. A row of prompt text could not carry that.
 */

function AgentCard({
  agent,
  activeCalls,
  number,
}: {
  agent: VoiceAgent;
  activeCalls: number;
  number?: PhoneNumber;
}) {
  const status = agentStatus(agent, activeCalls);
  const script = scriptCompleteness(agent);
  const thin = script.filled <= 2;

  return (
    <Card className="group relative overflow-hidden transition hover:border-[hsl(var(--primary))]/50 hover:shadow-md">
      <CardContent className="space-y-3 py-5">
        <div className="flex items-start gap-3">
          <AgentAvatar
            name={agent.persona_name || agent.name}
            avatarKey={agent.avatar_key}
            size="lg"
            status={status.tone}
          />
          <div className="min-w-0 flex-1">
            <Link
              href={`/voice-agents/${agent.id}`}
              className="block truncate text-base font-semibold underline-offset-2 hover:underline"
            >
              {agent.persona_name || agent.name}
            </Link>
            <p className="truncate text-xs text-muted-foreground">{agent.role_title || "Voice agent"}</p>
            <Badge
              variant={status.tone === "ready" ? "secondary" : "outline"}
              className={cn(
                "mt-1.5 text-[10px]",
                status.tone === "calling" && "border-sky-500/50 text-sky-700 dark:text-sky-300",
                status.tone === "setup" && "border-amber-500/50 text-amber-700 dark:text-amber-400"
              )}
            >
              {status.label}
            </Badge>
          </div>
        </div>

        <dl className="space-y-1 text-xs">
          <div className="flex gap-2">
            <dt className="w-16 shrink-0 text-muted-foreground">Job</dt>
            <dd className="min-w-0 flex-1 truncate font-medium">{goalLabel(agent.script?.goal ?? "custom")}</dd>
          </div>
          <div className="flex gap-2">
            <dt className="w-16 shrink-0 text-muted-foreground">Number</dt>
            <dd className="min-w-0 flex-1 truncate tabular-nums">
              {number ? number.e164_number : <span className="text-muted-foreground">Not assigned</span>}
            </dd>
          </div>
          <div className="flex gap-2">
            <dt className="w-16 shrink-0 text-muted-foreground">Handles</dt>
            <dd className="min-w-0 flex-1 truncate capitalize">
              {agent.direction === "both" ? "Inbound and outbound" : `${agent.direction} only`}
            </dd>
          </div>
        </dl>

        {thin ? (
          <p className="rounded-md border border-amber-500/40 bg-amber-50/60 px-2.5 py-1.5 text-[11px] text-amber-900 dark:bg-amber-950/20 dark:text-amber-200">
            Thin script — still needs {script.missing.slice(0, 2).join(" and ")}.
          </p>
        ) : (
          <div className="flex items-center gap-2">
            <div className="h-1 flex-1 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-emerald-500"
                style={{ width: `${(script.filled / script.total) * 100}%` }}
              />
            </div>
            <span className="text-[11px] tabular-nums text-muted-foreground">
              {script.filled}/{script.total}
            </span>
          </div>
        )}

        <div className="flex gap-2 pt-1">
          <Button asChild variant="outline" size="sm" className="flex-1">
            <Link href={`/voice-agents/${agent.id}`}>Edit script</Link>
          </Button>
          {agent.phone_number_id && agent.is_active ? (
            <PlaceCallDrawer
              agent={agent}
              trigger={
                <Button variant="outline" size="sm" aria-label={`Place a call with ${agent.persona_name || agent.name}`}>
                  <PhoneOutgoing className="h-3.5 w-3.5" />
                </Button>
              }
            />
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

export function AgentRoster() {
  const { data: agents, isLoading, error } = useQuery({
    queryKey: ["voice-agents"],
    queryFn: () => apiFetch<VoiceAgent[]>("/voice-agents"),
    retry: false,
  });

  const { data: numbers = [] } = useQuery({
    queryKey: ["voice-agents", "phone-numbers"],
    queryFn: () => apiFetch<PhoneNumber[]>("/voice-agents/phone-numbers"),
  });

  // Who is on a call right now. One small query, refreshed on a timer, so a card can say "On a
  // call" rather than only ever showing configuration.
  const { data: live } = useQuery({
    queryKey: ["voice-agents", "calls", "live"],
    queryFn: () => apiPage<CallSummary>("/voice-agents/calls?status=in_progress&limit=50"),
    refetchInterval: 20_000,
    retry: false,
  });

  const activeByAgent = new Map<string, number>();
  for (const call of live?.items ?? []) {
    activeByAgent.set(call.voice_agent_id, (activeByAgent.get(call.voice_agent_id) ?? 0) + 1);
  }

  if (isLoading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-64 w-full" />
        ))}
      </div>
    );
  }

  if (error) {
    return <p className="text-sm text-destructive">{(error as Error).message}</p>;
  }

  if (!agents?.length) {
    return (
      <Card className="border-dashed">
        <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
          <span className="flex h-12 w-12 items-center justify-center rounded-full bg-[hsl(var(--primary))]/10">
            <Sparkles className="h-6 w-6 text-[hsl(var(--primary))]" aria-hidden />
          </span>
          <div className="space-y-1">
            <p className="font-semibold">Your AI team is empty</p>
            <p className="mx-auto max-w-sm text-sm text-muted-foreground">
              Hire an agent to qualify new leads, chase proposals or answer your main line. Each one
              starts with a written script you can edit.
            </p>
          </div>
          <HireAgentDrawer
            trigger={
              <Button className={primaryButton}>
                <UserPlus className="h-4 w-4" />
                Hire your first agent
              </Button>
            }
          />
        </CardContent>
      </Card>
    );
  }

  const ready = agents.filter((a) => agentStatus(a).tone === "ready").length;
  const onCall = [...activeByAgent.values()].reduce((sum, n) => sum + n, 0);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <span>
            <span className="font-semibold text-foreground tabular-nums">{agents.length}</span> on the team
          </span>
          <span aria-hidden>·</span>
          <span>
            <span className="font-semibold text-foreground tabular-nums">{ready}</span> ready
          </span>
          {onCall > 0 ? (
            <>
              <span aria-hidden>·</span>
              <span className="flex items-center gap-1 font-medium text-sky-700 dark:text-sky-300">
                <PhoneCall className="h-3.5 w-3.5" />
                {onCall} on a call now
              </span>
            </>
          ) : null}
        </div>
        <HireAgentDrawer
          trigger={
            <Button className={primaryButton} size="sm">
              <UserPlus className="h-4 w-4" />
              Hire an agent
            </Button>
          }
        />
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {agents.map((agent) => (
          <AgentCard
            key={agent.id}
            agent={agent}
            activeCalls={activeByAgent.get(agent.id) ?? 0}
            number={numbers.find((n) => n.id === agent.phone_number_id)}
          />
        ))}
      </div>
    </div>
  );
}
