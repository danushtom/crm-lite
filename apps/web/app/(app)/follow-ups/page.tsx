"use client";

import type { TaskRow } from "@dracara/types";
import { Button, Card, CardContent, CardHeader, CardTitle, cn } from "@dracara/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { addDays, format, parseISO } from "date-fns";
import { Check, Clock } from "lucide-react";
import { toast } from "sonner";
import { apiFetch } from "@/lib/api";

type FollowUpQueues = { today: TaskRow[]; overdue: TaskRow[]; upcoming: TaskRow[] };

function safeDate(value: string | null | undefined): string {
  if (!value) return "—";
  try {
    return format(parseISO(value), "MMM d, yyyy");
  } catch {
    return value;
  }
}

export default function FollowUpsPage() {
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["dashboard-followups"],
    queryFn: () => apiFetch<FollowUpQueues>("/dashboard/follow-ups"),
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["dashboard-followups"] });
    qc.invalidateQueries({ queryKey: ["dashboard"] });
    qc.invalidateQueries({ queryKey: ["tasks"] });
  };

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

  const snooze = useMutation({
    mutationFn: ({ taskId, days }: { taskId: string; days: number }) => {
      const until = format(addDays(new Date(), days), "yyyy-MM-dd");
      return apiFetch(`/tasks/${taskId}`, {
        method: "PATCH",
        body: JSON.stringify({ status: "snoozed", snoozed_until: until, due_date: until }),
      });
    },
    onSuccess: () => {
      toast.success("Task snoozed");
      invalidate();
    },
    onError: (e: Error) => toast.error(e.message || "Could not snooze task"),
  });

  const pending = complete.isPending || snooze.isPending;

  if (isLoading || !data) return <p className="text-sm text-muted-foreground">Loading follow-up queues…</p>;

  const sections: { key: keyof FollowUpQueues; title: string; tone?: string }[] = [
    { key: "overdue", title: "Overdue", tone: "text-destructive" },
    { key: "today", title: "Today" },
    { key: "upcoming", title: "Upcoming (14 days)" },
  ];

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Follow-up engine</h1>
        <p className="mt-1 text-muted-foreground">Today, overdue, and upcoming tasks.</p>
      </div>

      {sections.map(({ key, title, tone }) => (
        <section key={key} className="space-y-3">
          <h2 className={cn("text-lg font-semibold", tone)}>
            {title}
            <span className="ml-2 text-sm font-normal text-muted-foreground">({data[key].length})</span>
          </h2>
          <TaskList
            tasks={data[key]}
            disabled={pending}
            onComplete={(id) => complete.mutate(id)}
            onSnooze={(id) => snooze.mutate({ taskId: id, days: 1 })}
          />
        </section>
      ))}
    </div>
  );
}

function TaskList({
  tasks,
  disabled,
  onComplete,
  onSnooze,
}: {
  tasks: TaskRow[];
  disabled: boolean;
  onComplete: (taskId: string) => void;
  onSnooze: (taskId: string) => void;
}) {
  if (!tasks.length) return <p className="text-sm text-muted-foreground">None.</p>;

  return (
    <div className="grid gap-3 md:grid-cols-2">
      {tasks.map((t) => {
        const done = t.status === "completed";
        return (
          <Card key={t.id}>
            <CardHeader className="py-3">
              <CardTitle className={cn("text-base", done && "text-muted-foreground line-through")}>
                {t.title || "Task"}
              </CardTitle>
            </CardHeader>
            <CardContent className="flex items-center justify-between gap-3 py-0 pb-3">
              <p className="text-xs text-muted-foreground">
                Due {safeDate(t.due_date)} · {t.status}
              </p>
              {!done ? (
                <div className="flex shrink-0 items-center gap-1.5">
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-8 gap-1.5 text-xs"
                    disabled={disabled}
                    onClick={() => onSnooze(t.id)}
                  >
                    <Clock className="h-3.5 w-3.5" />
                    Snooze 1d
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-8 gap-1.5 text-xs"
                    disabled={disabled}
                    onClick={() => onComplete(t.id)}
                  >
                    <Check className="h-3.5 w-3.5" />
                    Complete
                  </Button>
                </div>
              ) : null}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
