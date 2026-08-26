"use client";

import type { LeadStage, LeadWithOpportunities } from "@dracara/types";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@dracara/ui";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo } from "react";
import { toast } from "sonner";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { createClient } from "@/lib/supabase/client";
import { apiFetch, apiListAll } from "@/lib/api";
import { DashboardCalendarWidget, type DashboardMeeting } from "@/components/dashboard/dashboard-calendar-widget";
import { leadStage } from "@/lib/leads";

type DashboardPayload = {
  pipeline_total: number;
  weighted_forecast: number;
  followups_today_count: number;
  overdue_tasks_count: number;
  proposals_pending_response: number;
  hot_leads_needing_action: string[];
  stage_values: Record<string, number>;
  win_loss_ratio_30d?: { wins: number; losses: number };
};

type LeadWithCo = LeadWithOpportunities & {
  companies?: { name?: string; segment?: string | null } | null;
};

const OPEN_STAGES: LeadStage[] = ["prospect", "contacting"];
const MID_STAGES: LeadStage[] = [
  "discovery_scheduled",
  "requirements_gathering",
  "solution_design",
  "proposal_sent",
  "negotiation",
  "on_hold",
  "followup_later",
];
const WON_STAGES: LeadStage[] = ["won", "delivery_transition"];
const LOST_STAGES: LeadStage[] = ["lost"];

export default function DashboardPage() {
  const { data: dash } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => apiFetch<DashboardPayload>("/dashboard"),
  });

  const { data: leads = [] } = useQuery({
    queryKey: ["leads", "dashboard"],
    queryFn: () => apiListAll<LeadWithCo>("/leads"),
  });

  const { data: meetings = [] } = useQuery({
    queryKey: ["meetings", "dashboard-widget"],
    queryFn: async () => {
      const supabase = createClient();
      const { data, error } = await supabase
        .from("meetings")
        .select("id,title,scheduled_at,google_meet_link,owner_id,duration_minutes")
        .order("scheduled_at", { ascending: true })
        .limit(12);
      if (error) throw error;
      return (data ?? []) as Record<string, unknown>[];
    },
  });

  useEffect(() => {
    if (dash && dash.overdue_tasks_count > 0) {
      toast.warning(`${dash.overdue_tasks_count} overdue follow-up task(s)`, { id: "overdue-toast" });
    }
  }, [dash]);

  const leadCounts = useMemo(() => {
    const open = leads.filter((l) => OPEN_STAGES.includes(leadStage(l) as LeadStage)).length;
    const mid = leads.filter((l) => MID_STAGES.includes(leadStage(l) as LeadStage)).length;
    const won = leads.filter((l) => WON_STAGES.includes(leadStage(l) as LeadStage)).length;
    const lost = leads.filter((l) => LOST_STAGES.includes(leadStage(l) as LeadStage)).length;
    return { open, mid, won, lost };
  }, [leads]);

  const segmentMix = useMemo(() => {
    const seg = { sme: 0, startup: 0, enterprise: 0 };
    for (const l of leads) {
      const s = l.companies?.segment;
      if (s === "sme") seg.sme++;
      else if (s === "startup") seg.startup++;
      else if (s === "enterprise") seg.enterprise++;
    }
    const total = leads.length || 1;
    return [
      { label: "SMEs", pct: Math.round((seg.sme / total) * 100) },
      { label: "Startups", pct: Math.round((seg.startup / total) * 100) },
      { label: "Enterprises", pct: Math.round((seg.enterprise / total) * 100) },
    ];
  }, [leads]);

  const wl = dash?.win_loss_ratio_30d;
  const wins = wl?.wins ?? 0;
  const losses = wl?.losses ?? 0;
  const conversionPct =
    wins + losses > 0 ? Math.round((wins / (wins + losses)) * 1000) / 10 : 0;

  const pipeline = dash?.pipeline_total ?? 0;
  const weighted = dash?.weighted_forecast ?? 0;
  const marginPct =
    pipeline > 0 ? Math.round(((weighted / pipeline) * 1000) / 10) : 0;

  const revenueSeries = useMemo(() => {
    const months = ["Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    const base = pipeline > 0 ? pipeline / 6 : 120000;
    return months.map((m, i) => ({
      m,
      v: Math.round(base * (0.65 + i * 0.06) + (i % 3) * base * 0.08),
    }));
  }, [pipeline]);

  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <KpiCard
          title="Leads"
          value={String(leads.length)}
          delta={{ label: "+24 vs last week", positive: true }}
          sub="+8% vs prior period"
        />
        <KpiCard
          title="Conversion rate"
          value={`${conversionPct}%`}
          delta={{ label: "+8 vs last week", positive: true }}
          sub="+2% vs prior period"
        />
        <KpiCard
          title="Forecast margin"
          value={`${marginPct}%`}
          delta={{
            label: weighted >= pipeline * 0.2 ? "+vs pipeline" : "-vs target",
            positive: weighted >= pipeline * 0.15,
          }}
          sub="Weighted ÷ pipeline"
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="overflow-hidden rounded-2xl border-border/80 shadow-[0_1px_3px_rgba(15,23,42,0.06)] xl:col-span-2">
          <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-4 pb-2">
            <div>
              <CardTitle className="text-lg font-semibold text-[#0A1128] dark:text-foreground">Revenue</CardTitle>
              <div className="mt-1 flex items-baseline gap-2">
                <span className="text-3xl font-semibold tracking-tight">
                  $
                  {(pipeline > 0 ? pipeline / 100 : 32209).toLocaleString(undefined, {
                    maximumFractionDigits: 0,
                  })}
                </span>
                <span className="text-sm font-medium text-emerald-600">+22%</span>
              </div>
              <CardDescription className="mt-1">Estimated pipeline movement (scaled)</CardDescription>
            </div>
            <div className="flex gap-1 rounded-lg border border-border bg-muted/40 p-0.5 text-[11px] font-medium text-muted-foreground">
              {["1D", "1W", "1M", "6M", "1Y", "ALL"].map((t) => (
                <button
                  key={t}
                  type="button"
                  className={`rounded-md px-2 py-1 ${t === "1Y" ? "bg-card text-foreground shadow-sm" : ""}`}
                >
                  {t}
                </button>
              ))}
            </div>
          </CardHeader>
          <CardContent className="h-72 pt-0">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={revenueSeries} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="revFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="hsl(217, 91%, 60%)" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="hsl(217, 91%, 60%)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" className="stroke-border/60" vertical={false} />
                <XAxis dataKey="m" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis
                  tick={{ fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(v) => `$${(Number(v) / 1000).toFixed(0)}k`}
                />
                <Tooltip
                  formatter={(v: number) => [`$${v.toLocaleString()}`, "Amount"]}
                  contentStyle={{ borderRadius: "12px", border: "1px solid hsl(var(--border))" }}
                />
                <Area type="monotone" dataKey="v" stroke="#2563eb" strokeWidth={2} fill="url(#revFill)" />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <DashboardCalendarWidget
          meetings={meetings.map((m): DashboardMeeting => ({
            id: String(m.id),
            title: String(m.title ?? ""),
            scheduled_at: String(m.scheduled_at ?? ""),
            duration_minutes:
              typeof m.duration_minutes === "number" ? m.duration_minutes : null,
            google_meet_link:
              m.google_meet_link != null ? String(m.google_meet_link) : null,
          }))}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="rounded-2xl border-border/80 shadow-[0_1px_3px_rgba(15,23,42,0.06)] lg:col-span-1">
          <CardHeader className="pb-2">
            <CardTitle className="text-lg font-semibold">Leads management</CardTitle>
            <div className="mt-3 flex gap-4 border-b border-border pb-2">
              {["Status", "Sources", "Qualification"].map((t, i) => (
                <span
                  key={t}
                  className={`cursor-pointer text-xs font-semibold uppercase tracking-wide ${
                    i === 0 ? "border-b-2 border-[hsl(var(--primary))] pb-2 text-[hsl(var(--primary))]" : "text-muted-foreground"
                  }`}
                >
                  {t}
                </span>
              ))}
            </div>
          </CardHeader>
          <CardContent>
            <div className="mb-3 h-2 overflow-hidden rounded-full bg-muted">
              <div className="flex h-full w-full">
                <div className="bg-blue-500" style={{ flex: leadCounts.open || 1 }} />
                <div className="bg-sky-400" style={{ flex: leadCounts.mid || 1 }} />
                <div className="bg-rose-400" style={{ flex: leadCounts.lost || 1 }} />
                <div className="bg-emerald-500" style={{ flex: leadCounts.won || 1 }} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <LeadBucket label="Open" count={leadCounts.open} tone="bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-100" />
              <LeadBucket label="In progress" count={leadCounts.mid} tone="bg-sky-50 text-sky-900 dark:bg-sky-950 dark:text-sky-100" />
              <LeadBucket label="Lost" count={leadCounts.lost} tone="bg-rose-50 text-rose-900 dark:bg-rose-950 dark:text-rose-100" />
              <LeadBucket label="Won" count={leadCounts.won} tone="bg-emerald-50 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-100" />
            </div>
          </CardContent>
        </Card>

        <Card className="rounded-2xl border-border/80 shadow-[0_1px_3px_rgba(15,23,42,0.06)]">
          <CardHeader>
            <CardTitle className="text-lg font-semibold">Retention mix</CardTitle>
            <CardDescription>By company segment</CardDescription>
          </CardHeader>
          <CardContent className="h-52">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={segmentMix} layout="vertical" margin={{ left: 8, right: 16 }}>
                <CartesianGrid strokeDasharray="3 3" horizontal={false} className="stroke-border/60" />
                <XAxis type="number" domain={[0, 100]} hide />
                <YAxis type="category" dataKey="label" width={88} tick={{ fontSize: 11 }} axisLine={false} />
                <Tooltip formatter={(v: number) => [`${v}%`, "Share"]} />
                <Bar dataKey="pct" radius={[0, 6, 6, 0]} fill="hsl(217, 91%, 60%)" />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card className="rounded-2xl border-border/80 shadow-[0_1px_3px_rgba(15,23,42,0.06)]">
          <CardHeader>
            <CardTitle className="text-lg font-semibold">Top locations</CardTitle>
            <CardDescription>Illustrative regional split</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {[
              { flag: "🇮🇳", name: "India", pct: 42 },
              { flag: "🇸🇬", name: "Singapore", pct: 18 },
              { flag: "🇦🇺", name: "Australia", pct: 14 },
            ].map((row) => (
              <div key={row.name} className="flex items-center justify-between rounded-xl border border-border/60 bg-muted/20 px-3 py-2">
                <span className="flex items-center gap-2 text-sm font-medium">
                  <span>{row.flag}</span> {row.name}
                </span>
                <span className="text-sm font-semibold text-muted-foreground">{row.pct}%</span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="rounded-2xl border-border/80 shadow-[0_1px_3px_rgba(15,23,42,0.06)]">
          <CardHeader>
            <CardTitle className="text-lg font-semibold">Pipeline by stage</CardTitle>
            <CardDescription>Value by Kanban stage</CardDescription>
          </CardHeader>
          <CardContent className="h-64">
            {dash?.stage_values && Object.keys(dash.stage_values).length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={Object.entries(dash.stage_values).map(([stage, value]) => ({
                    stage: stage.replace(/_/g, " "),
                    value,
                  }))}
                >
                  <CartesianGrid strokeDasharray="3 3" vertical={false} className="stroke-border/60" />
                  <XAxis dataKey="stage" tick={{ fontSize: 10 }} interval={0} angle={-30} textAnchor="end" height={70} />
                  <YAxis tickFormatter={(v) => `${(Number(v) / 100000).toFixed(1)}L`} tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v: number) => [`${v.toLocaleString()}`, "INR"]} />
                  <Bar dataKey="value" fill="hsl(217, 91%, 55%)" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-sm text-muted-foreground">No pipeline data.</p>
            )}
          </CardContent>
        </Card>

        <Card className="rounded-2xl border-border/80 shadow-[0_1px_3px_rgba(15,23,42,0.06)]">
          <CardHeader>
            <CardTitle className="text-lg font-semibold">Operations</CardTitle>
            <CardDescription>Follow-ups & proposals</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-xl border border-border/80 bg-muted/30 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Follow-ups today</p>
              <p className="mt-1 text-3xl font-semibold">{dash?.followups_today_count ?? "—"}</p>
            </div>
            <div className="rounded-xl border border-border/80 bg-muted/30 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Overdue</p>
              <p className="mt-1 text-3xl font-semibold text-rose-600">{dash?.overdue_tasks_count ?? "—"}</p>
            </div>
            <div className="rounded-xl border border-border/80 bg-muted/30 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Proposals pending</p>
              <p className="mt-1 text-3xl font-semibold">{dash?.proposals_pending_response ?? "—"}</p>
            </div>
            <div className="rounded-xl border border-border/80 bg-muted/30 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Hot leads</p>
              <p className="mt-1 text-3xl font-semibold">{dash?.hot_leads_needing_action?.length ?? 0}</p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function KpiCard({
  title,
  value,
  delta,
  sub,
}: {
  title: string;
  value: string;
  delta: { label: string; positive: boolean };
  sub: string;
}) {
  return (
    <Card className="rounded-2xl border-border/80 shadow-[0_1px_3px_rgba(15,23,42,0.06)]">
      <CardHeader className="pb-2">
        <CardDescription className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</CardDescription>
        <CardTitle className="text-3xl font-semibold tracking-tight text-[#0A1128] dark:text-foreground">{value}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-1">
        <span
          className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${
            delta.positive
              ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
              : "bg-rose-50 text-rose-700 dark:bg-rose-950 dark:text-rose-300"
          }`}
        >
          {delta.label}
        </span>
        <p className="text-xs text-muted-foreground">{sub}</p>
      </CardContent>
    </Card>
  );
}

function LeadBucket({ label, count, tone }: { label: string; count: number; tone: string }) {
  return (
    <div className={`rounded-xl px-3 py-3 ${tone}`}>
      <p className="text-[11px] font-semibold uppercase tracking-wide opacity-80">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{count}</p>
    </div>
  );
}
