"use client";

import { Button } from "@dracara/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { apiFetch } from "@/lib/api";
import { useApiMutation } from "@/lib/use-api-mutation";
import { EntityDrawer, Field, SelectField, TextField, TextareaField } from "@/components/shared/entity-drawer";
import { AgentDocuments } from "@/components/voice-agents/agent-documents";
import type { PhoneNumber, VoiceAgent, VoiceAgentDirection } from "@dracara/types";

const DIRECTION_OPTIONS: { value: VoiceAgentDirection; label: string }[] = [
  { value: "outbound", label: "Outbound only" },
  { value: "inbound", label: "Inbound only" },
  { value: "both", label: "Both" },
];

const STATUS_OPTIONS = [
  { value: "true", label: "Active" },
  { value: "false", label: "Paused" },
];

type FormState = {
  name: string;
  system_prompt: string;
  direction: VoiceAgentDirection;
  phone_number_id: string;
  is_active: string;
};

function emptyForm(agent?: VoiceAgent): FormState {
  return {
    name: agent?.name ?? "",
    system_prompt: agent?.system_prompt ?? "",
    direction: agent?.direction ?? "outbound",
    phone_number_id: agent?.phone_number_id ?? "",
    is_active: String(agent?.is_active ?? true),
  };
}

/**
 * Create or edit a voice agent. The disclosure/recording preamble is not editable here --
 * it's generated server-side from a fixed template so every call opens with it regardless of
 * what's written in the prompt (see the backend's create_voice_agent()).
 */
export function VoiceAgentDrawer({ agent, trigger }: { agent?: VoiceAgent; trigger: React.ReactNode }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<FormState>(emptyForm(agent));
  const isEdit = Boolean(agent);

  useEffect(() => {
    if (open) setForm(emptyForm(agent));
  }, [open, agent]);

  const { data: phoneNumbers } = useQuery({
    queryKey: ["voice-agents", "phone-numbers"],
    queryFn: () => apiFetch<PhoneNumber[]>("/voice-agents/phone-numbers"),
    enabled: open,
  });

  const save = useApiMutation({
    errorTitle: isEdit ? "Could not update this voice agent" : "Could not create this voice agent",
    mutationFn: () =>
      isEdit
        ? apiFetch<VoiceAgent>(`/voice-agents/${agent!.id}`, {
            method: "PATCH",
            // The API guards this with If-Match; without the header the edit is rejected as a
            // precondition failure rather than silently overwriting a concurrent change.
            headers: { "If-Match": `"${agent!.version}"` },
            body: JSON.stringify({
              name: form.name.trim(),
              system_prompt: form.system_prompt.trim(),
              direction: form.direction,
              phone_number_id: form.phone_number_id || null,
              is_active: form.is_active === "true",
            }),
          })
        : apiFetch<VoiceAgent>("/voice-agents", {
            method: "POST",
            body: JSON.stringify({
              name: form.name.trim(),
              system_prompt: form.system_prompt.trim(),
              direction: form.direction,
              phone_number_id: form.phone_number_id || null,
            }),
          }),
    onSuccess: (saved) => {
      qc.invalidateQueries({ queryKey: ["voice-agents"] });
      toast.success(isEdit ? "Voice agent updated" : "Voice agent created", { description: saved.name });
      setOpen(false);
    },
  });

  const remove = useApiMutation({
    errorTitle: "Could not delete this voice agent",
    mutationFn: () =>
      apiFetch(`/voice-agents/${agent!.id}`, {
        method: "DELETE",
        headers: { "If-Match": `"${agent!.version}"` },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["voice-agents"] });
      qc.invalidateQueries({ queryKey: ["voice-agents", "phone-numbers"] });
      toast.success("Voice agent deleted", {
        description: "Its number is now free to assign to another agent.",
      });
      setOpen(false);
    },
  });

  return (
    <EntityDrawer
      open={open}
      onOpenChange={setOpen}
      trigger={trigger}
      icon={Bot}
      title={isEdit ? "Edit voice agent" : "Create voice agent"}
      description={isEdit ? agent!.name : "Configure what this AI agent says and does on a call."}
      submitLabel={isEdit ? "Save changes" : "Create agent"}
      canSubmit={form.name.trim().length > 0 && form.system_prompt.trim().length > 0}
      isPending={save.isPending || remove.isPending}
      onSubmit={() => save.mutate()}
      destructiveAction={
        isEdit ? (
          <Button
            type="button"
            variant="ghost"
            className="gap-1.5 text-destructive hover:bg-destructive/10 hover:text-destructive"
            disabled={remove.isPending}
            onClick={() => remove.mutate()}
          >
            <Trash2 className="h-4 w-4" />
            Delete agent
          </Button>
        ) : undefined
      }
    >
      <TextField
        id="voice-agent-name"
        label="Name"
        placeholder="Sales Follow-up Bot"
        value={form.name}
        onChange={(v) => setForm((p) => ({ ...p, name: v }))}
        required
      />

      <TextareaField
        id="voice-agent-prompt"
        label="System prompt"
        placeholder="You are a friendly sales rep following up on a demo request..."
        value={form.system_prompt}
        onChange={(v) => setForm((p) => ({ ...p, system_prompt: v }))}
        hint="What the agent knows and how it should behave. The recording disclosure is added automatically and always plays first -- do not write your own opener."
        required
      />

      <SelectField
        id="voice-agent-direction"
        label="Direction"
        value={form.direction}
        onChange={(v) => setForm((p) => ({ ...p, direction: v as VoiceAgentDirection }))}
        options={DIRECTION_OPTIONS}
      />

      <SelectField
        id="voice-agent-phone"
        label="Phone number"
        value={form.phone_number_id}
        onChange={(v) => setForm((p) => ({ ...p, phone_number_id: v }))}
        placeholder="No number assigned yet"
        options={(phoneNumbers ?? []).map((n) => ({ value: n.id, label: n.e164_number }))}
        hint="Register a number under Phone numbers first."
      />

      {isEdit ? (
        <>
          <SelectField
            id="voice-agent-status"
            label="Status"
            value={form.is_active}
            onChange={(v) => setForm((p) => ({ ...p, is_active: v }))}
            options={STATUS_OPTIONS}
            hint="A paused agent keeps its configuration and history but takes no calls."
          />

          <Field
            label="Knowledge base"
            hint="Documents the agent can quote from mid-call, alongside live CRM data."
          >
            <AgentDocuments voiceAgentId={agent!.id} />
          </Field>
        </>
      ) : (
        <p className="text-xs text-muted-foreground">
          Knowledge-base documents can be uploaded once the agent is created.
        </p>
      )}
    </EntityDrawer>
  );
}
