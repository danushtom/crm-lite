"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { PhoneOutgoing } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { apiListAll } from "@/lib/api";
import { apiFetch } from "@/lib/api";
import { useApiMutation } from "@/lib/use-api-mutation";
import { EntityDrawer, SelectField, TextareaField } from "@/components/shared/entity-drawer";
import type { CallSummary, ContactRow, VoiceAgent } from "@dracara/types";

/**
 * Dial a contact with a voice agent.
 *
 * `POST /voice-agents/{id}/calls` existed with consent and compliance gating and had no caller
 * in the UI, so outbound calling was unreachable from the product. Contacts without recorded
 * AI-call consent, or without a phone number, are shown but not selectable -- the server would
 * reject them anyway (logging a `no_consent_blocked` row), and a disabled option with a reason
 * is more useful than a 403 after the fact.
 */
export function PlaceCallDrawer({ agent, trigger }: { agent: VoiceAgent; trigger: ReactNode }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [contactId, setContactId] = useState("");
  const [note, setNote] = useState("");

  useEffect(() => {
    if (open) {
      setContactId("");
      setNote("");
    }
  }, [open]);

  const { data: contacts } = useQuery({
    queryKey: ["contacts", "all"],
    queryFn: () => apiListAll<ContactRow>("/contacts"),
    enabled: open,
  });

  const callable = useMemo(
    () => (contacts ?? []).filter((c) => c.ai_call_consent && c.phone),
    [contacts]
  );

  const place = useApiMutation({
    errorTitle: "Could not place the call",
    mutationFn: () =>
      apiFetch<CallSummary>(`/voice-agents/${agent.id}/calls`, {
        method: "POST",
        body: JSON.stringify({
          contact_id: contactId,
          context_note: note.trim() || null,
        }),
      }),
    onSuccess: (call) => {
      qc.invalidateQueries({ queryKey: ["voice-agents", "calls"] });
      toast.success("Call queued", {
        description: `${agent.name} is dialling ${call.to_number}.`,
      });
      setOpen(false);
    },
  });

  const notReady = !agent.platform_assistant_id
    ? "This agent is not connected to the voice platform yet."
    : !agent.phone_number_id
      ? "Assign a phone number to this agent before calling."
      : agent.direction === "inbound"
        ? "This agent is inbound-only. Change its direction to place calls."
        : null;

  return (
    <EntityDrawer
      open={open}
      onOpenChange={setOpen}
      trigger={trigger}
      icon={PhoneOutgoing}
      title="Place a call"
      description={agent.name}
      submitLabel="Start call"
      pendingLabel="Dialling…"
      canSubmit={Boolean(contactId) && !notReady}
      isPending={place.isPending}
      onSubmit={() => place.mutate()}
    >
      {notReady ? (
        <p className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/20 dark:text-amber-200">
          {notReady}
        </p>
      ) : null}

      <SelectField
        id="place-call-contact"
        label="Contact"
        value={contactId}
        onChange={setContactId}
        placeholder={callable.length === 0 ? "No contacts have consented yet" : "Select a contact"}
        options={callable.map((c) => ({ value: c.id, label: `${c.full_name} — ${c.phone}` }))}
        required
        hint="Only contacts with a phone number and recorded AI-call consent can be dialled. Record consent on the contact's detail page."
      />

      <TextareaField
        id="place-call-note"
        label="Context for this call"
        rows={4}
        value={note}
        onChange={setNote}
        placeholder="Following up on last week's demo; they asked about pricing tiers."
        hint="Optional. Passed to the agent alongside the CRM record so it opens on the right footing."
      />

      <p className="text-xs text-muted-foreground">
        The recording disclosure always plays first, before anything in the agent&rsquo;s prompt.
      </p>
    </EntityDrawer>
  );
}
