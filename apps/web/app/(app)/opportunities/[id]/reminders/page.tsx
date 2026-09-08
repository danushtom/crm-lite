"use client";

import { Button, Card, CardContent, CardHeader, CardTitle, cn } from "@dracara/ui";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useState } from "react";
import { apiFetch, apiList } from "@/lib/api";
import { MeetingDrawer } from "@/components/meetings/meeting-drawer";
import {
  addMonths,
  eachDayOfInterval,
  endOfMonth,
  endOfWeek,
  format,
  isSameDay,
  isSameMonth,
  parseISO,
  startOfMonth,
  startOfWeek,
  subMonths,
} from "date-fns";
import { ChevronLeft, ChevronRight, Plus, Calendar as CalendarIcon } from "lucide-react";

type MeetingRow = {
  id: string;
  title: string;
  scheduled_at: string;
  status: string;
};

type TaskRow = {
  id: string;
  title: string;
  due_at: string;
  status: string;
};

export default function OpportunityRemindersPage() {
  const { id } = useParams<{ id: string }>();
  const [currentDate, setCurrentDate] = useState(new Date());

  // Fetch opportunity to get lead_id
  const { data: opp } = useQuery({
    queryKey: ["opportunity", id],
    queryFn: () => apiFetch<{ lead_id: string }>(`/opportunities/${id}`),
  });

  const leadId = opp?.lead_id;

  const { data: meetings = [] } = useQuery({
    queryKey: ["meetings", leadId],
    queryFn: () => apiList<MeetingRow>(`/leads/${leadId}/meetings`),
    enabled: !!leadId,
  });

  const { data: tasks = [] } = useQuery({
    queryKey: ["tasks", leadId],
    queryFn: () => apiList<TaskRow>(`/leads/${leadId}/tasks`),
    enabled: !!leadId,
  });

  const cardShell = "rounded-xl border border-border/70 bg-card shadow-sm overflow-hidden";

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">Reminders</h2>
          <p className="mt-1 text-sm text-muted-foreground">Deal-specific meetings and tasks.</p>
        </div>
        {leadId ? <MeetingDrawer leadId={leadId} /> : null}
      </div>

      <Card className={cardShell}>
        <CardHeader className="flex flex-row items-center justify-between border-b border-border/60 bg-muted/5 py-3">
          <div className="flex items-center gap-4">
            <h4 className="text-sm font-semibold">{format(currentDate, "MMMM yyyy")}</h4>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={() => setCurrentDate(subMonths(currentDate, 1))}
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={() => setCurrentDate(addMonths(currentDate, 1))}
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
          <Button variant="outline" size="sm" className="h-8 gap-1.5 text-xs" onClick={() => setCurrentDate(new Date())}>
            Today
          </Button>
        </CardHeader>
        <CardContent className="p-0">
          <div className="grid grid-cols-7 border-b border-border/50 bg-muted/10">
            {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((day) => (
              <div key={day} className="py-2 text-center text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                {day}
              </div>
            ))}
          </div>
          <div className="grid grid-cols-7 border-l border-t border-border/30">
            {(() => {
              const monthStart = startOfMonth(currentDate);
              const monthEnd = endOfMonth(monthStart);
              const startDate = startOfWeek(monthStart);
              const endDate = endOfWeek(monthEnd);
              const calendarDays = eachDayOfInterval({ start: startDate, end: endDate });

              return calendarDays.map((day) => {
                const dayTasks = tasks.filter((t) => isSameDay(parseISO(t.due_at), day));
                const dayMeetings = meetings.filter((m) => isSameDay(parseISO(m.scheduled_at), day));

                return (
                  <div
                    key={day.toString()}
                    className={cn(
                      "min-h-[110px] border-b border-r border-border/30 p-2 transition-colors",
                      !isSameMonth(day, monthStart) && "bg-muted/5 opacity-40",
                      isSameDay(day, new Date()) && "bg-[#0B7FB3]/8 dark:bg-[#0B7FB3]/10"
                    )}
                  >
                    <span
                      className={cn(
                        "inline-flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-medium",
                        isSameDay(day, new Date()) && "bg-[#0B7FB3] text-white shadow-sm"
                      )}
                    >
                      {format(day, "d")}
                    </span>
                    <div className="mt-1 space-y-1">
                      {dayMeetings.map((m) => (
                        <div
                          key={m.id}
                          className="truncate rounded bg-[#0B7FB3]/15 px-1.5 py-0.5 text-[10px] font-medium text-[#096892] dark:bg-[#0B7FB3]/30 dark:text-[#4FB8E3]"
                        >
                          {m.title}
                        </div>
                      ))}
                      {dayTasks.map((t) => (
                        <div
                          key={t.id}
                          className={cn(
                            "truncate rounded px-1.5 py-0.5 text-[10px] font-medium",
                            t.status === "completed"
                              ? "bg-slate-100 text-slate-500 line-through dark:bg-slate-800"
                              : "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-200"
                          )}
                        >
                          {t.title}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              });
            })()}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
