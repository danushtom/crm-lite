"use client";

import { Button, Card, CardContent, CardHeader, CardTitle, Input } from "@dracara/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiFetch } from "@/lib/api";

export function LeadTasks({ leadId }: { leadId: string }) {
  const qc = useQueryClient();
  const { data: tasks = [], isLoading } = useQuery({
    queryKey: ["tasks", leadId],
    queryFn: () => apiFetch<Record<string, unknown>[]>(`/leads/${leadId}/tasks`),
  });

  const [title, setTitle] = useState("");
  const [due, setDue] = useState("");

  const create = useMutation({
    mutationFn: () =>
      apiFetch(`/leads/${leadId}/tasks`, {
        method: "POST",
        body: JSON.stringify({ title, due_date: due }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tasks", leadId] });
      setTitle("");
      setDue("");
    },
  });

  return (
    <Card className="rounded-xl border border-border/70 shadow-[0_1px_3px_rgba(15,23,42,0.06)]">
      <CardHeader className="border-b border-border/50 pb-3">
        <CardTitle className="text-base font-semibold">Follow-up tasks</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-2">
          <Input placeholder="Task title" value={title} onChange={(e) => setTitle(e.target.value)} className="max-w-xs" />
          <Input type="date" value={due} onChange={(e) => setDue(e.target.value)} className="w-40" />
          <Button size="sm" disabled={!title || !due || create.isPending} onClick={() => create.mutate()}>
            Add task
          </Button>
        </div>
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading tasks…</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {(tasks as Record<string, unknown>[]).map((t) => (
              <li key={String(t.id)} className="flex justify-between gap-2 rounded-md border border-border/60 px-3 py-2">
                <span>{String(t.title)}</span>
                <span className="text-muted-foreground">{String(t.due_date ?? "")}</span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
