"use client";

import type { MeetingRow } from "@dracara/types";
import { Button } from "@dracara/ui";
import { useQueryClient } from "@tanstack/react-query";
import { CalendarClock, Pencil, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { apiFetch } from "@/lib/api";
import { compactPayload } from "@/lib/forms";
import { useApiMutation } from "@/lib/use-api-mutation";
import { EntityDrawer, SelectField, TextField } from "@/components/shared/entity-drawer";

const STATUS_OPTIONS = [
  { value: "scheduled", label: "Scheduled" },
  { value: "completed", label: "Completed" },
  { value: "cancelled", label: "Cancelled" },
  { value: "rescheduled", label: "Rescheduled" },
];

const OUTCOME_OPTIONS = [
  { value: "", label: "Not recorded yet" },
  { value: "interested", label: "Interested" },
  { value: "needs_proposal", label: "Needs a proposal" },
  { value: "budget_issue", label: "Budget issue" },
  { value: "not_interested", label: "Not interested" },
  { value: "followup_later", label: "Follow up later" },
];

/** `datetime-local` wants a local wall-clock string; the API stores an instant. */
function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

const EMPTY = {
  title: "Discovery call",
  scheduled_at: "",
  duration_minutes: "30",
  status: "scheduled",
  outcome: "",
  outcome_notes: "",
};

type Form = typeof EMPTY;

/**
 * Schedule, reschedule or remove a meeting, and record what came of it.
 *
 * Recording an outcome goes through its own endpoint rather than a plain update, because
 * outcomes of "needs proposal" or "follow up later" schedule a follow-up task two days out.
 * Saving both at once would be two requests, so the drawer sends the outcome only when it
 * has actually changed.
 */
export function MeetingDrawer({
  leadId,
  meeting,
  trigger,
}: {
  leadId: string;
  meeting?: MeetingRow;
  trigger?: React.ReactNode;
}) {
  const editing = Boolean(meeting);
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<Form>(EMPTY);

  useEffect(() => {
    if (!open) return;
    setForm(
      meeting
        ? {
            title: meeting.title ?? "",
            scheduled_at: toLocalInput(meeting.scheduled_at),
            duration_minutes: String(meeting.duration_minutes ?? 30),
            status: meeting.status ?? "scheduled",
            outcome: meeting.outcome ?? "",
            outcome_notes: meeting.outcome_notes ?? "",
          }
        : EMPTY
    );
  }, [open, meeting]);

  const set = <K extends keyof Form>(key: K, value: string) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["meetings"] });
    qc.invalidateQueries({ queryKey: ["tasks"] });
    qc.invalidateQueries({ queryKey: ["dashboard-followups"] });
  };

  const save = useApiMutation({
    errorTitle: editing ? "Could not save meeting" : "Could not schedule meeting",
    mutationFn: async () => {
      const scheduledAt = new Date(form.scheduled_at).toISOString();

      if (!editing) {
        return apiFetch(`/leads/${leadId}/meetings`, {
          method: "POST",
          body: JSON.stringify({
            title: form.title.trim(),
            scheduled_at: scheduledAt,
            duration_minutes: Number(form.duration_minutes) || 30,
          }),
        });
      }

      const updated = await apiFetch<MeetingRow>(`/meetings/${meeting!.id}`, {
        method: "PATCH",
        headers: { "If-Match": `"${meeting!.version}"` },
        body: JSON.stringify(
          compactPayload({
            title: form.title.trim(),
            scheduled_at: scheduledAt,
            duration_minutes: Number(form.duration_minutes) || 30,
            status: form.status,
          })
        ),
      });

      // Only when it actually changed: this endpoint can create a follow-up task.
      if (form.outcome && form.outcome !== (meeting!.outcome ?? "")) {
        return apiFetch(`/meetings/${meeting!.id}/outcome`, {
          method: "PATCH",
          body: JSON.stringify(
            compactPayload({
              outcome: form.outcome,
              outcome_notes: form.outcome_notes,
              status: "completed",
            })
          ),
        });
      }
      return updated;
    },
    onSuccess: () => {
      invalidate();
      toast.success(editing ? "Meeting updated" : "Meeting scheduled");
      setOpen(false);
    },
  });

  const remove = useApiMutation({
    errorTitle: "Could not delete meeting",
    mutationFn: () => apiFetch(`/meetings/${meeting!.id}`, { method: "DELETE" }),
    onSuccess: () => {
      invalidate();
      toast.success("Meeting deleted");
      setOpen(false);
    },
  });

  const defaultTrigger = (
    <Button size="sm" className="gap-2">
      <Plus className="h-4 w-4" />
      New meeting
    </Button>
  );

  return (
    <EntityDrawer
      open={open}
      onOpenChange={setOpen}
      trigger={trigger ?? defaultTrigger}
      icon={editing ? Pencil : CalendarClock}
      title={editing ? "Edit meeting" : "Schedule a meeting"}
      description={
        editing
          ? "Recording an outcome of 'needs a proposal' or 'follow up later' schedules a follow-up task two days out."
          : "Times are entered and shown in your own timezone."
      }
      submitLabel={editing ? "Save changes" : "Schedule"}
      pendingLabel={editing ? "Saving…" : "Scheduling…"}
      canSubmit={Boolean(form.title.trim() && form.scheduled_at)}
      isPending={save.isPending || remove.isPending}
      onSubmit={() => save.mutate()}
      destructiveAction={
        editing ? (
          <Button
            type="button"
            variant="ghost"
            className="gap-1.5 text-destructive hover:bg-destructive/10 hover:text-destructive"
            disabled={remove.isPending}
            onClick={() => remove.mutate()}
          >
            <Trash2 className="h-4 w-4" />
            Delete
          </Button>
        ) : undefined
      }
    >
      <TextField
        id="meeting-title"
        label="Title"
        required
        placeholder="Requirements sync"
        value={form.title}
        onChange={(v) => set("title", v)}
      />

      <div className="grid grid-cols-2 gap-4">
        <TextField
          id="meeting-when"
          label="Date and time"
          required
          type="datetime-local"
          value={form.scheduled_at}
          onChange={(v) => set("scheduled_at", v)}
        />
        <TextField
          id="meeting-duration"
          label="Duration (min)"
          type="number"
          min={5}
          max={480}
          inputMode="numeric"
          value={form.duration_minutes}
          onChange={(v) => set("duration_minutes", v)}
        />
      </div>

      {editing ? (
        <>
          <SelectField
            id="meeting-status"
            label="Status"
            value={form.status}
            onChange={(v) => set("status", v)}
            options={STATUS_OPTIONS}
          />
          <SelectField
            id="meeting-outcome"
            label="Outcome"
            value={form.outcome}
            onChange={(v) => set("outcome", v)}
            options={OUTCOME_OPTIONS}
            hint="Setting this marks the meeting completed and may schedule a follow-up."
          />
          {form.outcome ? (
            <TextField
              id="meeting-outcome-notes"
              label="Outcome notes"
              placeholder="Wants the integration scoped separately"
              value={form.outcome_notes}
              onChange={(v) => set("outcome_notes", v)}
            />
          ) : null}
        </>
      ) : null}
    </EntityDrawer>
  );
}
