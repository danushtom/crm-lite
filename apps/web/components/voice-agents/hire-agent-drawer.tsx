"use client";

import type { VoiceAgent, VoiceAgentTemplate } from "@dracara/types";
import { Badge, cn } from "@dracara/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { UserPlus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { apiFetch } from "@/lib/api";
import { EntityDrawer, Field, TextField } from "@/components/shared/entity-drawer";
import { AVATAR_KEYS, AgentAvatar } from "@/components/voice-agents/agent-avatar";
import { useApiMutation } from "@/lib/use-api-mutation";

/**
 * Hiring an agent: pick the job, give it a name and a face, and it starts with a real script.
 *
 * Creating from a template matters more than it looks. A blank script produces an agent that
 * improvises on a live phone call, so the first thing a client does should leave them with
 * something specific enough to be worth listening to -- and something to edit by example.
 */
export function HireAgentDrawer({ trigger }: { trigger: React.ReactNode }) {
  const qc = useQueryClient();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [templateKey, setTemplateKey] = useState<string>("");
  const [name, setName] = useState("");
  const [personaName, setPersonaName] = useState("");
  const [roleTitle, setRoleTitle] = useState("");
  const [avatarKey, setAvatarKey] = useState<string>(AVATAR_KEYS[0]);

  const { data: templates = [] } = useQuery({
    queryKey: ["voice-agents", "templates"],
    queryFn: () => apiFetch<VoiceAgentTemplate[]>("/voice-agents/templates"),
    enabled: open,
    staleTime: Infinity,
  });

  // Choosing a job fills in the persona it ships with, which the client can then overwrite.
  function choose(template: VoiceAgentTemplate) {
    setTemplateKey(template.key);
    setName((current) => current || template.name);
    setPersonaName(template.persona_name);
    setRoleTitle(template.role_title);
    setAvatarKey(template.avatar_key || AVATAR_KEYS[0]);
  }

  useEffect(() => {
    if (!open) {
      setTemplateKey("");
      setName("");
      setPersonaName("");
      setRoleTitle("");
      setAvatarKey(AVATAR_KEYS[0]);
    }
  }, [open]);

  const create = useApiMutation({
    errorTitle: "Could not create this agent",
    mutationFn: () =>
      apiFetch<VoiceAgent>("/voice-agents", {
        method: "POST",
        body: JSON.stringify({
          name: name.trim(),
          persona_name: personaName.trim(),
          role_title: roleTitle.trim(),
          avatar_key: avatarKey,
          template: templateKey || null,
        }),
      }),
    onSuccess: (agent) => {
      qc.invalidateQueries({ queryKey: ["voice-agents"] });
      toast.success(`${agent.persona_name || agent.name} joined the team`, {
        description: "Review the script, then assign a phone number.",
      });
      setOpen(false);
      router.push(`/voice-agents/${agent.id}`);
    },
  });

  return (
    <EntityDrawer
      open={open}
      onOpenChange={setOpen}
      trigger={trigger}
      icon={UserPlus}
      title="Hire an AI agent"
      description="Pick the job it does. You can change every word of the script afterwards."
      submitLabel="Add to the team"
      pendingLabel="Creating…"
      canSubmit={name.trim().length > 0 && personaName.trim().length > 0}
      isPending={create.isPending}
      onSubmit={() => create.mutate()}
    >
      <Field label="What will it do?" hint="Starts it with a written script for that call.">
        <div className="space-y-2">
          {templates.map((template) => (
            <button
              key={template.key}
              type="button"
              aria-pressed={templateKey === template.key}
              onClick={() => choose(template)}
              className={cn(
                "flex w-full items-start gap-3 rounded-lg border p-3 text-left transition hover:border-[hsl(var(--primary))]",
                templateKey === template.key
                  ? "border-[hsl(var(--primary))] bg-[hsl(var(--primary))]/5 ring-1 ring-[hsl(var(--primary))]"
                  : "border-border"
              )}
            >
              <AgentAvatar name={template.persona_name} avatarKey={template.avatar_key} size="sm" />
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-center gap-1.5">
                  <span className="text-sm font-medium">{template.name}</span>
                  <Badge variant="secondary" className="text-[10px]">
                    {template.script.questions.length} questions
                  </Badge>
                </span>
                <span className="mt-0.5 block text-xs text-muted-foreground">{template.summary}</span>
              </span>
            </button>
          ))}
          <button
            type="button"
            aria-pressed={templateKey === ""}
            onClick={() => setTemplateKey("")}
            className={cn(
              "w-full rounded-lg border p-3 text-left transition hover:border-[hsl(var(--primary))]",
              templateKey === "" ? "border-[hsl(var(--primary))] bg-[hsl(var(--primary))]/5" : "border-border"
            )}
          >
            <span className="text-sm font-medium">Start from scratch</span>
            <span className="mt-0.5 block text-xs text-muted-foreground">
              An empty script you write yourself.
            </span>
          </button>
        </div>
      </Field>

      <TextField
        id="hire-name"
        label="Internal name"
        placeholder="Inbound receptionist"
        value={name}
        onChange={setName}
        required
        hint="What your team calls it in the CRM."
      />

      <TextField
        id="hire-persona"
        label="Name it gives on calls"
        placeholder="Maya"
        value={personaName}
        onChange={setPersonaName}
        required
        hint="Callers hear this name, and the recording disclosure uses it."
      />

      <TextField
        id="hire-role"
        label="Job title"
        placeholder="Sales development representative"
        value={roleTitle}
        onChange={setRoleTitle}
        hint="How it introduces itself."
      />

      <Field label="Picture" hint="Just so your team can tell them apart at a glance.">
        <div className="flex flex-wrap gap-2">
          {AVATAR_KEYS.map((key) => (
            <button
              key={key}
              type="button"
              aria-label={`Use the ${key} picture`}
              aria-pressed={avatarKey === key}
              onClick={() => setAvatarKey(key)}
              className={cn(
                "rounded-full p-0.5 transition",
                avatarKey === key ? "ring-2 ring-[hsl(var(--primary))] ring-offset-1 ring-offset-card" : "opacity-70 hover:opacity-100"
              )}
            >
              <AgentAvatar name={personaName || "Agent"} avatarKey={key} size="sm" />
            </button>
          ))}
        </div>
      </Field>

      <div className="flex items-center gap-3 rounded-lg border border-border/60 bg-muted/30 p-3">
        <AgentAvatar name={personaName || "Agent"} avatarKey={avatarKey} size="md" status="setup" />
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold">{personaName || "Your agent"}</p>
          <p className="truncate text-xs text-muted-foreground">{roleTitle || "Job title"}</p>
        </div>
      </div>
    </EntityDrawer>
  );
}
