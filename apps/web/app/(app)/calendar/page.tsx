"use client";

import type { MeetingRow } from "@dracara/types";
import { Badge, Button, Card, CardContent, cn } from "@dracara/ui";
import { useQuery } from "@tanstack/react-query";
import {
  addMonths,
  eachDayOfInterval,
  endOfMonth,
  endOfWeek,
  format,
  isSameDay,
  isSameMonth,
  isToday,
  parseISO,
  startOfMonth,
  startOfWeek,
  subMonths,
} from "date-fns";
import { CalendarClock, ChevronLeft, ChevronRight, Video } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { apiListAll } from "@/lib/api";

const STATUS_TONE: Record<string, string> = {
  scheduled: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
  completed: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
  cancelled: "bg-muted text-muted-foreground",
  rescheduled: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-200",
};

function safeDate(iso: string): Date | null {
  try {
    const d = parseISO(iso);
    return Number.isNaN(d.getTime()) ? null : d;
  } catch {
    return null;
  }
}

export default function CalendarPage() {
  const [cursor, setCursor] = useState(new Date());
  const [selected, setSelected] = useState<Date>(new Date());

  const { data: meetings = [], isLoading } = useQuery({
    queryKey: ["meetings", "calendar"],
    queryFn: () => apiListAll<MeetingRow>("/meetings"),
  });

  // Times come back as instants; grouping by local day is what a calendar means by "a day".
  const byDay = useMemo(() => {
    const map = new Map<string, MeetingRow[]>();
    for (const m of meetings) {
      const d = safeDate(m.scheduled_at);
      if (!d) continue;
      const key = format(d, "yyyy-MM-dd");
      map.set(key, [...(map.get(key) ?? []), m]);
    }
    for (const [, list] of map) {
      list.sort((a, b) => a.scheduled_at.localeCompare(b.scheduled_at));
    }
    return map;
  }, [meetings]);

  const days = useMemo(
    () =>
      eachDayOfInterval({
        start: startOfWeek(startOfMonth(cursor)),
        end: endOfWeek(endOfMonth(cursor)),
      }),
    [cursor]
  );

  const selectedMeetings = byDay.get(format(selected, "yyyy-MM-dd")) ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Calendar</h1>
          <p className="mt-1 text-muted-foreground">
            Every meeting across your deals. Connect Google Calendar in{" "}
            <Link href="/settings" className="underline underline-offset-4">
              settings
            </Link>{" "}
            to have external events appear here too.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="icon" className="h-8 w-8" onClick={() => setCursor(subMonths(cursor, 1))}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="min-w-[9rem] text-center text-sm font-semibold">
            {format(cursor, "MMMM yyyy")}
          </span>
          <Button variant="outline" size="icon" className="h-8 w-8" onClick={() => setCursor(addMonths(cursor, 1))}>
            <ChevronRight className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-8 text-xs"
            onClick={() => {
              setCursor(new Date());
              setSelected(new Date());
            }}
          >
            Today
          </Button>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <Card className="overflow-hidden">
          <CardContent className="p-3">
            <div className="grid grid-cols-7 gap-px text-center text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((d) => (
                <div key={d} className="py-2">
                  {d}
                </div>
              ))}
            </div>
            <div className="grid grid-cols-7 gap-1">
              {days.map((day) => {
                const dayMeetings = byDay.get(format(day, "yyyy-MM-dd")) ?? [];
                const outside = !isSameMonth(day, cursor);
                const isSelected = isSameDay(day, selected);
                return (
                  <button
                    key={day.toISOString()}
                    type="button"
                    onClick={() => setSelected(day)}
                    className={cn(
                      "flex min-h-[4.5rem] flex-col items-start gap-1 rounded-lg border border-transparent p-2 text-left transition-colors hover:bg-muted/50",
                      outside && "opacity-40",
                      isSelected && "border-border bg-muted/60",
                      isToday(day) && !isSelected && "border-[#0B7FB3]/40"
                    )}
                  >
                    <span
                      className={cn(
                        "text-xs font-semibold tabular-nums",
                        isToday(day) && "text-[#0B7FB3]"
                      )}
                    >
                      {format(day, "d")}
                    </span>
                    {dayMeetings.slice(0, 2).map((m) => (
                      <span
                        key={m.id}
                        className="w-full truncate rounded bg-[#0B7FB3]/10 px-1 py-0.5 text-[10px] text-[#0B7FB3]"
                      >
                        {format(parseISO(m.scheduled_at), "HH:mm")} {m.title}
                      </span>
                    ))}
                    {dayMeetings.length > 2 ? (
                      <span className="text-[10px] text-muted-foreground">
                        +{dayMeetings.length - 2} more
                      </span>
                    ) : null}
                  </button>
                );
              })}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="space-y-3 p-4">
            <div>
              <h2 className="text-sm font-semibold">{format(selected, "EEEE, d MMMM")}</h2>
              <p className="text-xs text-muted-foreground">
                {isLoading
                  ? "Loading…"
                  : selectedMeetings.length === 0
                    ? "Nothing scheduled."
                    : `${selectedMeetings.length} meeting${selectedMeetings.length === 1 ? "" : "s"}`}
              </p>
            </div>

            {selectedMeetings.map((m) => (
              <div key={m.id} className="rounded-lg border border-border/60 p-3">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm font-medium leading-tight">{m.title}</p>
                  <Badge className={cn("shrink-0 text-[10px] capitalize", STATUS_TONE[m.status])}>
                    {m.status}
                  </Badge>
                </div>
                <p className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
                  <CalendarClock className="h-3.5 w-3.5" />
                  {format(parseISO(m.scheduled_at), "HH:mm")} · {m.duration_minutes} min
                </p>
                <div className="mt-2 flex items-center gap-2">
                  {m.google_meet_link ? (
                    <Button variant="outline" size="sm" className="h-7 gap-1.5 text-xs" asChild>
                      <a href={m.google_meet_link} target="_blank" rel="noreferrer">
                        <Video className="h-3 w-3" />
                        Join
                      </a>
                    </Button>
                  ) : null}
                  {m.lead_id ? (
                    <Button variant="ghost" size="sm" className="h-7 text-xs" asChild>
                      <Link href={`/leads/${m.lead_id}/reminders`}>Open deal</Link>
                    </Button>
                  ) : (
                    <span className="text-[11px] text-muted-foreground">
                      Synced from Calendar, not linked to a deal
                    </span>
                  )}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
