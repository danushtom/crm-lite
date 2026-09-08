"use client";

import { Button } from "@dracara/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckSquare, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { apiFetch, apiList } from "@/lib/api";
import { compactPayload } from "@/lib/forms";
import { useApiMutation } from "@/lib/use-api-mutation";
import {
  EntityDrawer,
  SelectField,
  TextField,
  TextareaField,
} from "@/components/shared/entity-drawer";
import type { TaskRow, TaskStatus, UserRow } from "@dracara/types";

const STATUS_OPTIONS: { value: TaskStatus; label: string }[] = [
  { value: "pending", label: "Pending" },
  { value: "snoozed", label: "Snoozed" },
  { value: "completed", label: "Completed" },
  { value: "cancelled", label: "Cancelled" },
];

/** `datetime-local` wants "YYYY-MM-DDTHH:mm" in local time, not the ISO instant the API returns. */
function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

/**
 * Edit a follow-up: retitle it, move its due date, write notes, or hand it to a teammate.
 *
 * The follow-up queues previously offered exactly three actions -- complete, snooze one day,
 * delete. A task with the wrong date or the wrong owner could only be deleted and recreated,
 * and `PATCH /tasks/{id}`'s title/notes/due_at/owner_id fields had no caller at all. Owner
 * reassignment matters most: the queues are owner-scoped, so a task left on a deactivated
 * teammate is invisible in every queue in the product.
 */
export function TaskDrawer({
  task,
  onChanged,
  trigger,
}: {
  task: TaskRow;
  onChanged?: () => void;
  trigger: React.ReactNode;
}) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    title: task.title,
    notes: task.notes ?? "",
    due_at: toLocalInput(task.due_at),
    status: task.status as string,
    owner_id: task.owner_id,
  });

  useEffect(() => {
    if (!open) return;
    setForm({
      title: task.title,
      notes: task.notes ?? "",
      due_at: toLocalInput(task.due_at),
      status: task.status,
      owner_id: task.owner_id,
    });
  }, [open, task]);

  const { data: teammates } = useQuery({
    queryKey: ["agents"],
    queryFn: () => apiList<UserRow>("/agents"),
    enabled: open,
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["dashboard-followups"] });
    qc.invalidateQueries({ queryKey: ["tasks"] });
    qc.invalidateQueries({ queryKey: ["dashboard"] });
    onChanged?.();
  };

  const save = useApiMutation({
    errorTitle: "Could not update this task",
    mutationFn: () => {
      const dueAt = form.due_at ? new Date(form.due_at).toISOString() : undefined;
      return apiFetch<TaskRow>(`/tasks/${task.id}`, {
        method: "PATCH",
        headers: { "If-Match": `"${task.version}"` },
        body: JSON.stringify(
          compactPayload({
            title: form.title.trim(),
            notes: form.notes.trim(),
            due_at: dueAt,
            status: form.status,
            owner_id: form.owner_id,
            // The API rejects status 'snoozed' without a date to snooze until; reuse the due
            // date, which is what the one-click Snooze action on the queue does too.
            ...(form.status === "snoozed" ? { snoozed_to: dueAt } : {}),
          })
        ),
      });
    },
    onSuccess: () => {
      invalidate();
      toast.success("Task updated");
      setOpen(false);
    },
  });

  const remove = useApiMutation({
    errorTitle: "Could not delete this task",
    mutationFn: () => apiFetch(`/tasks/${task.id}`, { method: "DELETE" }),
    onSuccess: () => {
      invalidate();
      toast.success("Task deleted");
      setOpen(false);
    },
  });

  return (
    <EntityDrawer
      open={open}
      onOpenChange={setOpen}
      trigger={trigger}
      icon={CheckSquare}
      title="Follow-up"
      description="Reschedule, retitle, or hand this to a teammate."
      submitLabel="Save changes"
      canSubmit={form.title.trim().length > 0 && Boolean(form.due_at)}
      isPending={save.isPending || remove.isPending}
      onSubmit={() => save.mutate()}
      destructiveAction={
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
      }
    >
      <TextField
        id="task-title"
        label="Title"
        value={form.title}
        onChange={(v) => setForm((p) => ({ ...p, title: v }))}
        required
      />

      <TextField
        id="task-due"
        label="Due"
        type="datetime-local"
        value={form.due_at}
        onChange={(v) => setForm((p) => ({ ...p, due_at: v }))}
        required
        hint="Shown and entered in your own timezone; stored as an absolute instant."
      />

      <SelectField
        id="task-status"
        label="Status"
        value={form.status}
        onChange={(v) => setForm((p) => ({ ...p, status: v }))}
        options={STATUS_OPTIONS}
      />

      <SelectField
        id="task-owner"
        label="Owner"
        value={form.owner_id}
        onChange={(v) => setForm((p) => ({ ...p, owner_id: v }))}
        options={(teammates ?? []).map((u) => ({
          value: u.id,
          label: u.full_name || u.email,
        }))}
        hint="Follow-up queues are owner-scoped, so reassigning moves this out of your queue and into theirs."
      />

      <TextareaField
        id="task-notes"
        label="Notes"
        rows={4}
        value={form.notes}
        onChange={(v) => setForm((p) => ({ ...p, notes: v }))}
      />
    </EntityDrawer>
  );
}
