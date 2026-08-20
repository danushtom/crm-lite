"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@dracara/ui";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

type TaskRow = Record<string, unknown>;

export default function FollowUpsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["dashboard-followups"],
    queryFn: () => apiFetch<{ today: TaskRow[]; overdue: TaskRow[]; upcoming: TaskRow[] }>("/dashboard/followups"),
  });

  if (isLoading || !data)
    return <p className="text-sm text-muted-foreground">Loading follow-up queues…</p>;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Follow-up engine</h1>
        <p className="mt-1 text-muted-foreground">Today, overdue, and upcoming tasks.</p>
      </div>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-destructive">Overdue</h2>
        <TaskList tasks={data.overdue} />
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Today</h2>
        <TaskList tasks={data.today} />
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Upcoming (14 days)</h2>
        <TaskList tasks={data.upcoming} />
      </section>
    </div>
  );
}

function TaskList({ tasks }: { tasks: TaskRow[] }) {
  if (!tasks.length) return <p className="text-sm text-muted-foreground">None.</p>;
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {tasks.map((t) => (
        <Card key={String(t.id)}>
          <CardHeader className="py-3">
            <CardTitle className="text-base">{String(t.title ?? "Task")}</CardTitle>
          </CardHeader>
          <CardContent className="py-0 pb-3 text-xs text-muted-foreground">
            Due {String(t.due_date ?? "—")} · {String(t.status ?? "")}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
