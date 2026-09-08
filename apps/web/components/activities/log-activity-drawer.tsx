"use client";

import { useQueryClient } from "@tanstack/react-query";
import { NotebookPen } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { apiFetch } from "@/lib/api";
import { compactPayload } from "@/lib/forms";
import { useApiMutation } from "@/lib/use-api-mutation";
import { EntityDrawer, TextField, TextareaField } from "@/components/shared/entity-drawer";
import type { ActivityType } from "@dracara/types";

/**
 * Write a note, or log a call or an email, against a lead's timeline.
 *
 * `POST /leads/{id}/activities` has existed since the API was built. The contact detail page
 * carried "Note" and "Log call" buttons with no handler at all, and the only other way to add
 * to a timeline was a stage change, so the timeline recorded what the system did and nothing
 * a person did.
 */
export function LogActivityDrawer({
  leadId,
  type,
  title,
  trigger,
  onLogged,
}: {
  leadId: string;
  type: ActivityType;
  title: string;
  trigger: ReactNode;
  onLogged?: () => void;
}) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [description, setDescription] = useState("");
  const [outcome, setOutcome] = useState("");

  useEffect(() => {
    if (!open) return;
    setDescription("");
    setOutcome("");
  }, [open]);

  const log = useApiMutation({
    errorTitle: `Could not log this ${type}`,
    mutationFn: () =>
      apiFetch(`/leads/${leadId}/activities`, {
        method: "POST",
        body: JSON.stringify(
          compactPayload({ type, description: description.trim(), outcome: outcome.trim() })
        ),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["activities", leadId] });
      qc.invalidateQueries({ queryKey: ["leads", leadId] });
      qc.invalidateQueries({ queryKey: ["lead-detail", leadId] });
      toast.success(`${title} logged`);
      onLogged?.();
      setOpen(false);
    },
  });

  return (
    <EntityDrawer
      open={open}
      onOpenChange={setOpen}
      trigger={trigger}
      icon={NotebookPen}
      title={title}
      description="Goes onto this lead's timeline, attributed to you."
      submitLabel={`Log ${type}`}
      pendingLabel="Logging…"
      canSubmit={description.trim().length > 0}
      isPending={log.isPending}
      onSubmit={() => log.mutate()}
    >
      <TextareaField
        id="activity-description"
        label={type === "note" ? "Note" : "What happened"}
        rows={5}
        value={description}
        onChange={setDescription}
        placeholder={
          type === "call"
            ? "Spoke to Priya about the integration scope; she wants a revised estimate."
            : type === "email"
              ? "Sent the revised statement of work."
              : "Anything worth remembering about this deal."
        }
        required
      />

      <TextField
        id="activity-outcome"
        label="Outcome"
        value={outcome}
        onChange={setOutcome}
        placeholder="Optional — e.g. 'wants a revised quote'"
        hint="A short result, so the timeline can be skimmed without opening each entry."
      />
    </EntityDrawer>
  );
}
