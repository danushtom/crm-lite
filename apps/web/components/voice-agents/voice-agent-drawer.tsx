"use client";

import { Button } from "@dracara/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { apiFetch } from "@/lib/api";
import { useApiMutation } from "@/lib/use-api-mutation";
import { EntityDrawer, SelectField, TextField, TextareaField } from "@/components/shared/entity-drawer";
import type { PhoneNumber, VoiceAgent, VoiceAgentDirection } from "@dracara/types";

const DIRECTION_OPTIONS: { value: VoiceAgentDirection; label: string }[] = [
  { value: "outbound", label: "Outbound only" },
  { value: "inbound", label: "Inbound only" },
  { value: "both", label: "Both" },
];

type FormState = {
  name: string;
  system_prompt: string;
  direction: VoiceAgentDirection;
  phone_number_id: string;
};

function emptyForm(agent?: VoiceAgent): FormState {
  return {
    name: agent?.name ?? "",
    system_prompt: agent?.system_prompt ?? "",
    direction: agent?.direction ?? "outbound",
    phone_number_id: agent?.phone_number_id ?? "",
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
            body: JSON.stringify({
              name: form.name.trim(),
              system_prompt: form.system_prompt.trim(),
              direction: form.direction,
              phone_number_id: form.phone_number_id || null,
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
      isPending={save.isPending}
      onSubmit={() => save.mutate()}
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
        hint="Register a number under Phone numbers below first."
      />
    </EntityDrawer>
  );
}
