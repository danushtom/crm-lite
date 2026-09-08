"use client";

import type { TaskRow } from "@dracara/types";
import {
  Badge,
  Button,
  Card,
  CardContent,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  Skeleton,
  cn,
} from "@dracara/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { addDays, format, parseISO } from "date-fns";
import { Check, ChevronDown, Clock, Pencil } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";
import { apiFetch } from "@/lib/api";
import { humanizeEnum } from "@/lib/forms";
import { useApiMutation } from "@/lib/use-api-mutation";
import { PageSection } from "@/components/shared/page-section";
import { TaskDrawer } from "@/components/tasks/task-drawer";

type FollowUpQueues = { today: TaskRow[]; overdue: TaskRow[]; upcoming: TaskRow[] };

/** Renders an instant in the viewer's local zone, which is what the API intends. */
function safeDate(value: string | null | undefined): string {
  if (!value) return "—";
  try {
    return format(parseISO(value), "MMM d, yyyy · HH:mm");
  } catch {
    return value;
  }
}

/** How long each one-click snooze pushes a task out. */
const SNOOZE_OPTIONS = [
  { days: 1, label: "Tomorrow" },
  { days: 3, label: "In 3 days" },
  { days: 7, label: "Next week" },
];

export default function FollowUpsPage() {
  const qc = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ["dashboard-followups"],
    queryFn: () => apiFetch<FollowUpQueues>("/dashboard/follow-ups"),
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["dashboard-followups"] });
    qc.invalidateQueries({ queryKey: ["dashboard"] });
    qc.invalidateQueries({ queryKey: ["tasks"] });
  };

  const complete = useMutation({
    mutationFn: (task: TaskRow) =>
      apiFetch(`/tasks/${task.id}`, {
        method: "PATCH",
        // Send the version we rendered: two people working the same queue would otherwise
        // silently overwrite each other's outcome.
        headers: { "If-Match": `"${task.version}"` },
        body: JSON.stringify({ status: "completed" }),
      }),
    onSuccess: () => {
      toast.success("Task completed");
      invalidate();
    },
    onError: (e: Error) => toast.error(e.message || "Could not complete task"),
  });

  const snooze = useMutation({
    mutationFn: ({ task, days }: { task: TaskRow; days: number }) => {
      // due_at is an absolute instant, so preserve the original time of day rather than
      // collapsing the task to midnight.
      const until = addDays(new Date(), days).toISOString();
      return apiFetch(`/tasks/${task.id}`, {
        method: "PATCH",
        headers: { "If-Match": `"${task.version}"` },
        body: JSON.stringify({ status: "snoozed", snoozed_to: until, due_at: until }),
      });
    },
    onSuccess: () => {
      toast.success("Task snoozed");
      invalidate();
    },
    onError: (e: Error) => toast.error(e.message || "Could not snooze task"),
  });

  const pending = complete.isPending || snooze.isPending;

  const sections: { key: keyof FollowUpQueues; title: string; description: string; tone?: string }[] = [
    {
      key: "overdue",
      title: "Overdue",
      description: "Past their due date and still open. Work these first.",
      tone: "text-destructive",
    },
    { key: "today", title: "Today", description: "Due before the end of your day." },
    { key: "upcoming", title: "Upcoming", description: "Due within the next 14 days." },
  ];

  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground">
        Your follow-up queues, scoped to the tasks you own and bucketed by your own timezone.
      </p>

      {error ? (
        <p className="text-sm text-destructive">{(error as Error).message}</p>
      ) : isLoading || !data ? (
        <div className="space-y-6">
          {sections.map((s) => (
            <div key={s.key} className="space-y-3">
              <Skeleton className="h-5 w-32" />
              <div className="grid gap-3 md:grid-cols-2">
                <Skeleton className="h-24 w-full" />
                <Skeleton className="h-24 w-full" />
              </div>
            </div>
          ))}
        </div>
      ) : (
        sections.map(({ key, title, description, tone }) => (
          <PageSection
            key={key}
            title={title}
            description={description}
            action={
              <Badge
                variant="secondary"
                className={cn("h-5 rounded-md px-2 text-[10px] font-semibold tabular-nums", tone)}
              >
                {data[key].length}
              </Badge>
            }
          >
            <TaskList
              tasks={data[key]}
              disabled={pending}
              onComplete={(task) => complete.mutate(task)}
              onSnooze={(task, days) => snooze.mutate({ task, days })}
            />
          </PageSection>
        ))
      )}
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
  onComplete: (task: TaskRow) => void;
  onSnooze: (task: TaskRow, days: number) => void;
}) {
  if (!tasks.length) {
    return (
      <Card>
        <CardContent className="py-6">
          <p className="text-sm text-muted-foreground">Nothing in this queue.</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="grid gap-3 md:grid-cols-2">
      {tasks.map((t) => {
        const done = t.status === "completed";
        return (
          <Card key={t.id} className="transition-colors hover:border-border">
            <CardContent className="space-y-2.5 py-3">
              <div className="flex items-start justify-between gap-2">
                <p
                  className={cn(
                    "text-sm font-semibold leading-snug",
                    done && "text-muted-foreground line-through"
                  )}
                >
                  {t.title || "Task"}
                </p>
                <Badge variant="outline" className="shrink-0 text-[10px]">
                  {humanizeEnum(t.status)}
                </Badge>
              </div>

              {t.notes ? (
                <p className="line-clamp-2 text-xs text-muted-foreground">{t.notes}</p>
              ) : null}

              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="text-xs text-muted-foreground">
                  Due {safeDate(t.due_at)}
                  {/* The queues never linked anywhere, so a task told you what to do but not
                      who it was about. */}
                  {t.lead_id ? (
                    <>
                      {" · "}
                      <Link
                        href={`/leads/${t.lead_id}`}
                        className="font-medium text-[#0B7FB3] hover:underline"
                      >
                        Open lead
                      </Link>
                    </>
                  ) : null}
                </div>

                <div className="flex shrink-0 items-center gap-1">
                  <TaskDrawer
                    task={t}
                    trigger={
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-8 w-8"
                        aria-label={`Edit ${t.title}`}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                    }
                  />

                  {!done ? (
                    <>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            size="sm"
                            variant="ghost"
                            className="h-8 gap-1 text-xs"
                            disabled={disabled}
                          >
                            <Clock className="h-3.5 w-3.5" />
                            Snooze
                            <ChevronDown className="h-3 w-3" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          {SNOOZE_OPTIONS.map((option) => (
                            <DropdownMenuItem
                              key={option.days}
                              onClick={() => onSnooze(t, option.days)}
                            >
                              {option.label}
                            </DropdownMenuItem>
                          ))}
                        </DropdownMenuContent>
                      </DropdownMenu>

                      <Button
                        size="sm"
                        variant="outline"
                        className="h-8 gap-1.5 text-xs"
                        disabled={disabled}
                        onClick={() => onComplete(t)}
                      >
                        <Check className="h-3.5 w-3.5" />
                        Complete
                      </Button>
                    </>
                  ) : null}
                </div>
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
