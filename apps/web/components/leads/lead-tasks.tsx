"use client";

import type { TaskRow } from "@dracara/types";
import { Button, Card, CardContent, CardHeader, CardTitle, Input, cn } from "@dracara/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { format, parseISO } from "date-fns";
import { Check } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { apiFetch, apiList } from "@/lib/api";

export function LeadTasks({ leadId }: { leadId: string }) {
  const qc = useQueryClient();
  const { data: tasks = [], isLoading } = useQuery({
    queryKey: ["tasks", leadId],
    queryFn: () => apiList<TaskRow>(`/leads/${leadId}/tasks`),
  });

  const [title, setTitle] = useState("");
  const [due, setDue] = useState("");

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["tasks", leadId] });
    qc.invalidateQueries({ queryKey: ["dashboard-followups"] });
  };

  const create = useMutation({
    mutationFn: () =>
      apiFetch(`/leads/${leadId}/tasks`, {
        method: "POST",
        // <input type="date"> gives a local calendar date; the API stores an instant, so
        // anchor it at 09:00 local rather than implying midnight UTC.
        body: JSON.stringify({ title, due_at: new Date(`${due}T09:00`).toISOString() }),
      }),
    onSuccess: () => {
      invalidate();
      setTitle("");
      setDue("");
    },
    onError: (e: Error) => toast.error(e.message || "Could not create task"),
  });

  const complete = useMutation({
    mutationFn: (taskId: string) =>
      apiFetch(`/tasks/${taskId}`, {
        method: "PATCH",
        body: JSON.stringify({ status: "completed" }),
      }),
    onSuccess: () => {
      toast.success("Task completed");
      invalidate();
    },
    onError: (e: Error) => toast.error(e.message || "Could not complete task"),
  });

  return (
    <Card className="rounded-xl border border-border/70 shadow-[0_1px_3px_rgba(15,23,42,0.06)]">
      <CardHeader className="border-b border-border/50 pb-3">
        <CardTitle className="text-base font-semibold">Follow-up tasks</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-2">
          <Input
            placeholder="Task title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="max-w-xs"
          />
          <Input type="date" value={due} onChange={(e) => setDue(e.target.value)} className="w-40" />
          <Button size="sm" disabled={!title || !due || create.isPending} onClick={() => create.mutate()}>
            Add task
          </Button>
        </div>
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading tasks…</p>
        ) : tasks.length === 0 ? (
          <p className="text-sm text-muted-foreground">No tasks yet.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {tasks.map((t) => {
              const done = t.status === "completed";
              return (
                <li
                  key={t.id}
                  className="flex items-center justify-between gap-2 rounded-md border border-border/60 px-3 py-2"
                >
                  <span className={cn(done && "text-muted-foreground line-through")}>{t.title}</span>
                  <span className="flex shrink-0 items-center gap-2">
                    <span className="text-muted-foreground">{t.due_at ? format(parseISO(t.due_at), "MMM d, HH:mm") : ""}</span>
                    {!done ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7 gap-1 px-2 text-xs"
                        disabled={complete.isPending}
                        onClick={() => complete.mutate(t.id)}
                      >
                        <Check className="h-3.5 w-3.5" />
                        Done
                      </Button>
                    ) : null}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
