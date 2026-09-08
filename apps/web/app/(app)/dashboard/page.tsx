"use client";

import type { LeadStage, LeadWithOpportunities } from "@dracara/types";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@dracara/ui";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
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
import { KpiCard } from "@/components/shared/kpi-card";
import { humanizeEnum } from "@/lib/forms";
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

type TrendPoint = {
  month: string;
  label: string;
  won_value: number;
  won_count: number;
  opened_value: number;
  opened_count: number;
};

type LeadWithCo = LeadWithOpportunities & {
  companies?: { name?: string; segment?: string | null } | null;
};

/**
 * Ranges the revenue chart offers.
 *
 * These replace a 1D/1W/1M/6M/1Y/ALL row that had no click handler at all and permanently
 * highlighted 1Y while the chart always drew six months. The endpoint aggregates by calendar
 * month and accepts 1-24, so sub-month ranges are not offered -- they could not be honoured.
 */
const TREND_RANGES = [
  { months: 3, label: "3M" },
  { months: 6, label: "6M" },
  { months: 12, label: "1Y" },
  { months: 24, label: "2Y" },
];

/**
 * The two lead breakdowns this card can show.
 *
 * A third tab, "Qualification", used to sit alongside these. Nothing in the schema records a
 * qualification state distinct from pipeline stage, so it is dropped rather than reintroduced
 * as another view of the same numbers under a different name.
 */
const LEAD_VIEWS = ["Status", "Sources"] as const;

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

  const [leadView, setLeadView] = useState<(typeof LEAD_VIEWS)[number]>("Status");

  const bySource = useMemo(() => {
    const counts = new Map<string, number>();
    for (const l of leads) {
      counts.set(l.lead_source, (counts.get(l.lead_source) ?? 0) + 1);
    }
    return [...counts.entries()]
      .map(([source, count]) => ({ label: humanizeEnum(source), count }))
      .sort((a, b) => b.count - a.count);
  }, [leads]);

  /** Lead id -> company name, so the attention list can name a lead rather than show a uuid. */
  const leadNames = useMemo(() => {
    const map = new Map<string, string>();
    for (const l of leads) {
      if (l.companies?.name) map.set(l.id, l.companies.name);
    }
    return map;
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

  // Real monthly history. This used to be generated from pipeline_total by a formula, so it
  // moved plausibly while describing nothing that had actually happened.
  const [trendMonths, setTrendMonths] = useState(6);
  const { data: trend = [] } = useQuery({
    queryKey: ["dashboard", "trend", trendMonths],
    queryFn: () => apiFetch<TrendPoint[]>(`/dashboard/trend?months=${trendMonths}`),
  });

  const revenueSeries = useMemo(
    () => trend.map((t) => ({ m: t.label, v: Number(t.won_value), opened: Number(t.opened_value) })),
    [trend]
  );
  const hasTrendData = revenueSeries.some((p) => p.v > 0 || p.opened > 0);

  /**
   * Month-over-month change from the real series.
   *
   * Every delta chip on this page used to be a string literal -- "+24 vs last week",
   * "+8 vs last week", "+22%" -- shown identically whether the number had gone up, down or
   * nowhere. A dashboard that reports growth on an empty workspace is worse than one that
   * reports nothing, so these return null when there is no prior month to compare against.
   */
  const changeBetweenLastTwoMonths = (pick: (point: TrendPoint) => number) => {
    if (trend.length < 2) return null;
    const current = pick(trend[trend.length - 1]);
    const previous = pick(trend[trend.length - 2]);
    if (previous === 0) return current === 0 ? null : { label: "New this month", positive: true };
    const pct = Math.round(((current - previous) / previous) * 100);
    if (pct === 0) return { label: "Flat vs last month", positive: true };
    return { label: `${pct > 0 ? "+" : ""}${pct}% vs last month`, positive: pct > 0 };
  };

  const wonInWindow = trend.reduce((sum, point) => sum + Number(point.won_value), 0);
  const openedDelta = changeBetweenLastTwoMonths((p) => Number(p.opened_count));
  const wonValueDelta = changeBetweenLastTwoMonths((p) => Number(p.won_value));

  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <KpiCard
          label="Leads"
          value={String(leads.length)}
          delta={openedDelta}
          hint="Every lead in the workspace"
        />
        <KpiCard
          label="Conversion rate"
          value={wins + losses > 0 ? `${conversionPct}%` : "—"}
          hint={
            wins + losses > 0
              ? `${wins} won · ${losses} lost in the last 30 days`
              : "Nothing has closed in the last 30 days"
          }
        />
        <KpiCard
          label="Forecast margin"
          value={pipeline > 0 ? `${marginPct}%` : "—"}
          hint="Weighted forecast ÷ open pipeline"
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="overflow-hidden rounded-2xl border-border/80 shadow-[0_1px_3px_rgba(15,23,42,0.06)] xl:col-span-2">
          <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-4 pb-2">
            <div>
              <CardTitle className="text-lg font-semibold text-[#0A1128] dark:text-foreground">Won revenue</CardTitle>
              <div className="mt-1 flex items-baseline gap-2">
                {/* The real total of what closed in this window. This used to read
                    `pipeline_total / 100`, falling back to the literal 32209 on an empty
                    workspace -- a number with no basis in anything, in a currency the
                    workspace may not even use. */}
                <span className="text-3xl font-semibold tabular-nums tracking-tight">
                  {wonInWindow.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </span>
                {wonValueDelta ? (
                  <span
                    className={
                      wonValueDelta.positive
                        ? "text-sm font-medium text-emerald-600"
                        : "text-sm font-medium text-rose-600"
                    }
                  >
                    {wonValueDelta.label}
                  </span>
                ) : null}
              </div>
              <CardDescription className="mt-1">
                Closed-won value over the last {trendMonths} months, against value opened.
              </CardDescription>
            </div>
            <div className="flex gap-1 rounded-lg border border-border bg-muted/40 p-0.5 text-[11px] font-medium text-muted-foreground">
              {TREND_RANGES.map((range) => (
                <button
                  key={range.months}
                  type="button"
                  aria-pressed={range.months === trendMonths}
                  onClick={() => setTrendMonths(range.months)}
                  className={`rounded-md px-2 py-1 transition-colors ${
                    range.months === trendMonths
                      ? "bg-card text-foreground shadow-sm"
                      : "hover:text-foreground"
                  }`}
                >
                  {range.label}
                </button>
              ))}
            </div>
          </CardHeader>
          <CardContent className="h-72 pt-0">
            {!hasTrendData ? (
              <div className="flex h-full items-center justify-center">
                <p className="text-sm text-muted-foreground">
                  Nothing has been opened or won yet, so there is no history to chart.
                </p>
              </div>
            ) : (
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
                  tickFormatter={(v) => `${(Number(v) / 1000).toFixed(0)}k`}
                />
                <Tooltip
                  formatter={(v: number, name) => [
                    v.toLocaleString(),
                    name === "v" ? "Won" : "Opened",
                  ]}
                  contentStyle={{ borderRadius: "12px", border: "1px solid hsl(var(--border))" }}
                />
                <Area type="monotone" dataKey="opened" stroke="#94a3b8" strokeWidth={1.5} fill="none" strokeDasharray="4 3" />
                <Area type="monotone" dataKey="v" stroke="#2563eb" strokeWidth={2} fill="url(#revFill)" />
              </AreaChart>
            </ResponsiveContainer>
            )}
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
            {/* These were three static spans with no handler; the first was permanently
                highlighted and the other two did nothing. Both views are derivable from data
                already on the page, so they now switch. */}
            <div className="mt-3 flex gap-4 border-b border-border pb-2">
              {LEAD_VIEWS.map((view) => (
                <button
                  key={view}
                  type="button"
                  onClick={() => setLeadView(view)}
                  aria-pressed={leadView === view}
                  className={`text-xs font-semibold uppercase tracking-wide transition-colors ${
                    leadView === view
                      ? "border-b-2 border-[hsl(var(--primary))] pb-2 text-[hsl(var(--primary))]"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {view}
                </button>
              ))}
            </div>
          </CardHeader>
          <CardContent>
            {leadView === "Status" ? (
              <>
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
              </>
            ) : bySource.length === 0 ? (
              <p className="text-sm text-muted-foreground">No leads yet.</p>
            ) : (
              <div className="space-y-2">
                {bySource.map((row) => (
                  <div key={row.label} className="space-y-1">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-medium">{row.label}</span>
                      <span className="tabular-nums text-muted-foreground">
                        {row.count} · {Math.round((row.count / Math.max(leads.length, 1)) * 100)}%
                      </span>
                    </div>
                    <div className="h-2 overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full rounded-full bg-[#0B7FB3]"
                        style={{ width: `${(row.count / bySource[0].count) * 100}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
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

        {/* A "Top locations" card used to sit here with India 42% / Singapore 18% /
            Australia 14% hardcoded and captioned "Illustrative regional split". There is no
            country or region column anywhere in the schema, so it could not be made real; a
            panel of invented percentages next to real ones teaches people to distrust both. */}
        <Card className="rounded-2xl border-border/80 shadow-[0_1px_3px_rgba(15,23,42,0.06)]">
          <CardHeader>
            <CardTitle className="text-lg font-semibold">Needs attention</CardTitle>
            <CardDescription>Hot leads with no recent activity</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {(dash?.hot_leads_needing_action ?? []).length === 0 ? (
              <p className="text-sm text-muted-foreground">
                Nothing is going cold. Every hot lead has been touched recently.
              </p>
            ) : (
              dash!.hot_leads_needing_action.slice(0, 5).map((leadId) => (
                <Link
                  key={leadId}
                  href={`/leads/${leadId}`}
                  className="flex items-center justify-between rounded-xl border border-border/60 bg-muted/20 px-3 py-2 transition-colors hover:bg-muted/40"
                >
                  <span className="truncate text-sm font-medium">
                    {leadNames.get(leadId) ?? "Lead"}
                  </span>
                  <ArrowUpRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                </Link>
              ))
            )}
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

function LeadBucket({ label, count, tone }: { label: string; count: number; tone: string }) {
  return (
    <div className={`rounded-xl px-3 py-3 ${tone}`}>
      <p className="text-[11px] font-semibold uppercase tracking-wide opacity-80">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{count}</p>
    </div>
  );
}
