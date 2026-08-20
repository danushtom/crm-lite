"use client";

import { ChevronDown, ChevronRight } from "lucide-react";
import {
  addDays,
  addMinutes,
  addMonths,
  format,
  isSameDay,
  parseISO,
  startOfMonth,
  startOfWeek,
} from "date-fns";
import { useMemo, useState } from "react";

export type DashboardMeeting = {
  id: string;
  title: string;
  scheduled_at: string;
  duration_minutes?: number | null;
  google_meet_link?: string | null;
};

const WEEK_START = 0; // Sunday

function formatAgendaTime(d: Date): string {
  return format(d, "h:mm a").replace(":", ".").toLowerCase();
}

function platformAction(m: DashboardMeeting):
  | { kind: "link"; label: string; href: string }
  | { kind: "noop"; label: string }
  | null {
  if (m.google_meet_link) {
    return { kind: "link", label: "On Google Meet", href: m.google_meet_link };
  }
  if (/slack/i.test(m.title)) {
    return { kind: "noop", label: "On Slack" };
  }
  return null;
}

/** Decorative attendee stack — no attendee API yet */
function AvatarStack({ seed }: { seed: string }) {
  const extra = (seed.split("").reduce((a, c) => a + c.charCodeAt(0), 0) % 8) + 1;
  const tones = [
    "from-violet-400 to-purple-600",
    "from-sky-400 to-blue-600",
    "from-amber-400 to-orange-500",
  ];
  return (
    <div className="flex items-center">
      <div className="flex -space-x-2">
        {tones.map((tone, i) => (
          <div
            key={i}
            className={`h-8 w-8 shrink-0 rounded-full border-2 border-white bg-gradient-to-br shadow-sm dark:border-[hsl(var(--card))] ${tone}`}
          />
        ))}
      </div>
      <div className="-ml-2 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border-2 border-white bg-muted text-[10px] font-semibold text-muted-foreground dark:border-[hsl(var(--card))]">
        +{extra}
      </div>
    </div>
  );
}

export function DashboardCalendarWidget({ meetings }: { meetings: DashboardMeeting[] }) {
  const [selectedDate, setSelectedDate] = useState(() => new Date());

  const weekStart = useMemo(
    () => startOfWeek(selectedDate, { weekStartsOn: WEEK_START }),
    [selectedDate]
  );

  const weekDays = useMemo(() => Array.from({ length: 7 }, (_, i) => addDays(weekStart, i)), [weekStart]);

  const monthAnchor = startOfMonth(selectedDate);
  const monthSelectValue = format(monthAnchor, "yyyy-MM");

  const monthOptions = useMemo(() => {
    const months: { label: string; value: string }[] = [];
    const base = startOfMonth(new Date());
    for (let i = -12; i <= 12; i++) {
      const m = addMonths(base, i);
      months.push({ label: format(m, "MMMM yyyy"), value: format(m, "yyyy-MM") });
    }
    return months;
  }, []);

  function onMonthChange(value: string) {
    const [y, mo] = value.split("-").map(Number);
    const next = new Date(selectedDate);
    next.setFullYear(y, mo - 1, Math.min(selectedDate.getDate(), new Date(y, mo, 0).getDate()));
    setSelectedDate(next);
  }

  const dayMeetings = useMemo(() => {
    return meetings
      .filter((m) => {
        try {
          return isSameDay(parseISO(m.scheduled_at), selectedDate);
        } catch {
          return false;
        }
      })
      .sort((a, b) => new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime());
  }, [meetings, selectedDate]);

  const agendaBlocks = useMemo(() => {
    type Block =
      | { kind: "meeting"; meeting: DashboardMeeting; start: Date; end: Date }
      | { kind: "available"; start: Date; end: Date };

    const blocks: Block[] = [];
    const sorted = [...dayMeetings];
    for (let i = 0; i < sorted.length; i++) {
      const m = sorted[i];
      const start = parseISO(m.scheduled_at);
      const dur = m.duration_minutes ?? 30;
      const end = addMinutes(start, dur);
      if (i > 0) {
        const prev = sorted[i - 1];
        const prevEnd = addMinutes(parseISO(prev.scheduled_at), prev.duration_minutes ?? 30);
        if (start.getTime() - prevEnd.getTime() >= 20 * 60 * 1000) {
          blocks.push({ kind: "available", start: prevEnd, end: start });
        }
      } else {
        const dayStart = new Date(selectedDate);
        dayStart.setHours(9, 0, 0, 0);
        if (start.getTime() - dayStart.getTime() >= 25 * 60 * 1000) {
          blocks.push({ kind: "available", start: dayStart, end: start });
        }
      }
      blocks.push({ kind: "meeting", meeting: m, start, end });
    }
    return blocks;
  }, [dayMeetings, selectedDate]);

  return (
    <div className="flex h-full min-h-[420px] flex-col rounded-2xl border border-[#E5E7EB] bg-white shadow-[0_1px_3px_rgba(15,23,42,0.06)] dark:border-border dark:bg-card">
      {/* Header */}
      <div className="flex items-start justify-between gap-3 border-b border-[#E5E7EB] px-4 pb-2.5 pt-3 dark:border-border">
        <h2 className="text-base font-semibold tracking-tight text-[#111827] dark:text-foreground">Calendar</h2>
        <div className="relative shrink-0">
          <select
            aria-label="Select month"
            value={monthSelectValue}
            onChange={(e) => onMonthChange(e.target.value)}
            className="h-9 cursor-pointer appearance-none rounded-lg border border-[#E5E7EB] bg-white py-1.5 pl-3 pr-9 text-sm font-medium text-[#111827] shadow-sm outline-none ring-offset-background focus-visible:ring-2 focus-visible:ring-ring dark:border-border dark:bg-card dark:text-foreground"
          >
            {monthOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground opacity-70" />
        </div>
      </div>

      {/* Week strip */}
      <div className="border-b border-[#E5E7EB] px-2 pb-0 pt-3 dark:border-border">
        <div className="grid grid-cols-7 gap-1">
          {weekDays.map((day) => {
            const isSelected = isSameDay(day, selectedDate);
            const label = format(day, "EEE");
            const num = format(day, "d");
            return (
              <button
                key={day.toISOString()}
                type="button"
                onClick={() => setSelectedDate(day)}
                className="flex flex-col items-center pb-2 pt-1 transition-colors"
              >
                <span
                  className={`text-[11px] font-medium uppercase tracking-wide ${
                    isSelected ? "text-[#111827] dark:text-foreground" : "text-[#9CA3AF]"
                  }`}
                >
                  {label}
                </span>
                <span
                  className={`mt-0.5 text-[15px] font-semibold tabular-nums ${
                    isSelected ? "text-[#111827] dark:text-foreground" : "text-[#6B7280]"
                  }`}
                >
                  {num}
                </span>
                <span
                  className={`mt-1 h-0.5 w-8 rounded-full ${isSelected ? "bg-[#111827] dark:bg-foreground" : "bg-transparent"}`}
                  aria-hidden
                />
              </button>
            );
          })}
        </div>
      </div>

      {/* Agenda */}
      <div className="flex flex-1 flex-col gap-0 overflow-y-auto px-4 pb-3 pt-3">
        {meetings.length === 0 ? (
          <p className="text-sm text-[#6B7280] dark:text-muted-foreground">No upcoming meetings.</p>
        ) : agendaBlocks.length === 0 ? (
          <div className="rounded-xl border border-[#E5E7EB] bg-[#FAFAFA] px-3 py-8 text-center dark:border-border dark:bg-muted/30">
            <p className="text-sm font-semibold text-[#111827] dark:text-foreground">Available</p>
            <p className="mt-1 text-xs text-[#6B7280] dark:text-muted-foreground">Nothing scheduled this day.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {agendaBlocks.map((block, idx) => {
              if (block.kind === "available") {
                return (
                  <div key={`avail-${idx}`} className="flex gap-3">
                    <span className="w-14 shrink-0 pt-0.5 text-right text-[11px] font-medium leading-snug text-[#9CA3AF] dark:text-muted-foreground">
                      {formatAgendaTime(block.start)}
                    </span>
                    <div className="min-w-0 flex-1 rounded-xl border border-[#E5E7EB] bg-white px-3 py-3 dark:border-border dark:bg-card">
                      <p className="text-sm font-semibold text-[#111827] dark:text-foreground">Available Time</p>
                      <p className="mt-0.5 text-xs text-[#6B7280] dark:text-muted-foreground">
                        {formatAgendaTime(block.start)} – {formatAgendaTime(block.end)}
                      </p>
                    </div>
                  </div>
                );
              }

              const m = block.meeting;
              const action = platformAction(m);
              const showAvatars = Boolean(m.google_meet_link) || /slack/i.test(m.title);

              return (
                <div key={m.id} className="flex gap-3">
                  <span className="w-14 shrink-0 pt-0.5 text-right text-[11px] font-medium leading-snug text-[#9CA3AF] dark:text-muted-foreground">
                    {formatAgendaTime(block.start)}
                  </span>
                  <div className="min-w-0 flex-1 rounded-xl border border-[#E5E7EB] bg-white px-3 py-3 dark:border-border dark:bg-card">
                    <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between md:gap-4">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-semibold leading-snug text-[#111827] dark:text-foreground">{m.title}</p>
                        <p className="mt-1 text-xs text-[#6B7280] dark:text-muted-foreground">
                          {formatAgendaTime(block.start)} – {formatAgendaTime(block.end)}
                        </p>
                      </div>
                      <div className="flex shrink-0 flex-col items-stretch gap-2 sm:flex-row sm:items-center sm:gap-3 md:flex-row md:items-center">
                        {showAvatars ? <AvatarStack seed={String(m.id)} /> : null}
                        {action?.kind === "link" ? (
                          <a
                            href={action.href}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center justify-center gap-1 rounded-full border border-[#E5E7EB] bg-white px-3 py-1.5 text-xs font-medium text-[#111827] shadow-sm transition-colors hover:bg-[#F9FAFB] dark:border-border dark:bg-muted/40 dark:text-foreground dark:hover:bg-muted"
                          >
                            {action.label}
                            <ChevronRight className="h-3.5 w-3.5 opacity-60" />
                          </a>
                        ) : action?.kind === "noop" ? (
                          <button
                            type="button"
                            className="inline-flex items-center justify-center gap-1 rounded-full border border-[#E5E7EB] bg-white px-3 py-1.5 text-xs font-medium text-[#111827] shadow-sm dark:border-border dark:bg-muted/40 dark:text-foreground"
                          >
                            {action.label}
                            <ChevronRight className="h-3.5 w-3.5 opacity-60" />
                          </button>
                        ) : null}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
