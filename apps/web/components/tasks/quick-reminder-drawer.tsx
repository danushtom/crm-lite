"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { addDays, format } from "date-fns";
import { useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { apiFetch } from "@/lib/api";
import { compactPayload } from "@/lib/forms";
import { useApiMutation } from "@/lib/use-api-mutation";
import { EntityDrawer, TextField, TextareaField } from "@/components/shared/entity-drawer";

/** Tomorrow at 09:00 local, as `datetime-local` wants it. Most reminders are "chase this soon". */
function defaultDue(): string {
  const tomorrow = addDays(new Date(), 1);
  tomorrow.setHours(9, 0, 0, 0);
  return format(tomorrow, "yyyy-MM-dd'T'HH:mm");
}

/**
 * Set a follow-up on a lead without leaving the page you are on.
 *
 * `POST /leads/{id}/tasks` was only reachable from the lead's own reminders sub-route, so the
 * "Reminder" button on the contact detail page had nothing behind it.
 */
export function QuickReminderDrawer({
  leadId,
  trigger,
  defaultTitle,
}: {
  leadId: string;
  trigger: ReactNode;
  defaultTitle?: string;
}) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState(defaultTitle ?? "");
  const [dueAt, setDueAt] = useState(defaultDue());
  const [notes, setNotes] = useState("");

  useEffect(() => {
    if (!open) return;
    setTitle(defaultTitle ?? "");
    setDueAt(defaultDue());
    setNotes("");
  }, [open, defaultTitle]);

  const create = useApiMutation({
    errorTitle: "Could not create this reminder",
    mutationFn: () =>
      apiFetch(`/leads/${leadId}/tasks`, {
        method: "POST",
        body: JSON.stringify(
          compactPayload({
            title: title.trim(),
            // The API takes an absolute instant; the input is local wall-clock time.
            due_at: new Date(dueAt).toISOString(),
            notes: notes.trim(),
          })
        ),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tasks"] });
      qc.invalidateQueries({ queryKey: ["dashboard-followups"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success("Reminder set", { description: "It will appear in your follow-up queue." });
      setOpen(false);
    },
  });

  return (
    <EntityDrawer
      open={open}
      onOpenChange={setOpen}
      trigger={trigger}
      icon={Bell}
      title="Set a reminder"
      description="Creates a follow-up task on this lead, owned by you."
      submitLabel="Set reminder"
      pendingLabel="Saving…"
      canSubmit={title.trim().length > 0 && Boolean(dueAt)}
      isPending={create.isPending}
      onSubmit={() => create.mutate()}
    >
      <TextField
        id="reminder-title"
        label="What to do"
        value={title}
        onChange={setTitle}
        placeholder="Chase the signed SOW"
        required
      />

      <TextField
        id="reminder-due"
        label="Due"
        type="datetime-local"
        value={dueAt}
        onChange={setDueAt}
        required
        hint="Entered in your own timezone, which is also the one your queue buckets by."
      />

      <TextareaField
        id="reminder-notes"
        label="Notes"
        rows={3}
        value={notes}
        onChange={setNotes}
      />
    </EntityDrawer>
  );
}
