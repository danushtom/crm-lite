"use client";

import type { LeadStage, OpportunityRow } from "@dracara/types";
import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle, cn } from "@dracara/ui";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { useMemo } from "react";
import {
  Bar,
  BarChart,
  Cell,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { apiFetch, apiListAll } from "@/lib/api";
import { LEAD_STAGE_OPTIONS, humanizeEnum } from "@/lib/forms";
import { KpiCard } from "@/components/shared/kpi-card";

type Dashboard = {
  pipeline_total: number;
  weighted_forecast: number;
  pipeline_by_currency: Record<string, number>;
  mixed_currency: boolean;
  stage_values: Record<string, number>;
  win_loss_ratio_30d: { wins: number; losses: number };
  proposals_pending_response: number;
  overdue_tasks_count: number;
};

/** The order deals actually move through, so the funnel reads top to bottom. */
const FUNNEL: LeadStage[] = [
  "prospect",
  "contacting",
  "discovery_scheduled",
  "requirements_gathering",
  "solution_design",
  "proposal_sent",
  "negotiation",
  "won",
];

export default function ReportsPage() {
  const { data: dash } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => apiFetch<Dashboard>("/dashboard"),
  });

  const { data: opportunities = [], isLoading } = useQuery({
    queryKey: ["opportunities", "reports"],
    queryFn: () => apiListAll<OpportunityRow>("/opportunities"),
  });

  const funnel = useMemo(() => {
    const counts = new Map<string, { count: number; value: number }>();
    for (const o of opportunities) {
      const cur = counts.get(o.stage) ?? { count: 0, value: 0 };
      counts.set(o.stage, {
        count: cur.count + 1,
        value: cur.value + Number(o.quoted_value ?? 0),
      });
    }
    return FUNNEL.map((stage) => ({
      stage,
      label: humanizeEnum(stage),
      ...(counts.get(stage) ?? { count: 0, value: 0 }),
    }));
  }, [opportunities]);

  const bySource = useMemo(() => {
    // Reads through the embedded lead, since source is a property of the lead, not the deal.
    const counts = new Map<string, number>();
    for (const o of opportunities as (OpportunityRow & { leads?: { lead_source?: string } })[]) {
      const source = o.leads?.lead_source ?? "unknown";
      counts.set(source, (counts.get(source) ?? 0) + 1);
    }
    return [...counts.entries()]
      .map(([source, count]) => ({ label: humanizeEnum(source), count }))
      .sort((a, b) => b.count - a.count);
  }, [opportunities]);

  const wins = dash?.win_loss_ratio_30d.wins ?? 0;
  const losses = dash?.win_loss_ratio_30d.losses ?? 0;
  const decided = wins + losses;
  const winRate = decided > 0 ? Math.round((wins / decided) * 100) : null;

  const currencies = Object.entries(dash?.pipeline_by_currency ?? {});

  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground">
        Pipeline shape, conversion and where the work comes from.
      </p>

      {dash?.mixed_currency ? (
        <div className="flex gap-2 rounded-lg border border-amber-300/60 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <p>
            Your pipeline spans more than one currency, so a single total would add different
            units together. The figures below are broken out by currency instead.
          </p>
        </div>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="Pipeline"
          value={
            currencies.length === 0
              ? "—"
              : currencies.map(([c, v]) => `${c} ${Math.round(v).toLocaleString()}`).join(" · ")
          }
          hint={`${opportunities.length} open pursuits`}
        />
        <KpiCard
          label="Weighted forecast"
          value={dash ? Math.round(dash.weighted_forecast).toLocaleString() : "—"}
          hint="Pipeline × probability"
        />
        <KpiCard
          label="Win rate (30d)"
          value={winRate === null ? "—" : `${winRate}%`}
          hint={decided === 0 ? "Nothing closed yet" : `${wins} won · ${losses} lost`}
        />
        <KpiCard
          label="Awaiting response"
          value={String(dash?.proposals_pending_response ?? 0)}
          hint="Proposals sent, no answer"
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Pipeline funnel</CardTitle>
          <CardDescription>
            Pursuits at each stage. A stage far wider than the one after it is where deals stall.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="h-64 animate-pulse rounded-lg bg-muted/30" />
          ) : (
            <div className="space-y-2">
              {funnel.map((row, i) => {
                const widest = Math.max(...funnel.map((f) => f.count), 1);
                const prev = i > 0 ? funnel[i - 1].count : null;
                const dropped = prev !== null && prev > 0 ? Math.round((1 - row.count / prev) * 100) : null;
                return (
                  <div key={row.stage} className="flex items-center gap-3">
                    <span className="w-40 shrink-0 text-xs text-muted-foreground">{row.label}</span>
                    <div className="h-7 flex-1 overflow-hidden rounded bg-muted/40">
                      <div
                        className={cn(
                          "flex h-full items-center rounded px-2 text-[11px] font-semibold text-white",
                          row.stage === "won" ? "bg-emerald-500" : "bg-[#0B7FB3]"
                        )}
                        style={{ width: `${Math.max((row.count / widest) * 100, row.count ? 6 : 0)}%` }}
                      >
                        {row.count > 0 ? row.count : null}
                      </div>
                    </div>
                    <span className="w-16 shrink-0 text-right text-[11px] text-muted-foreground">
                      {dropped !== null && dropped > 0 ? `−${dropped}%` : ""}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Where deals come from</CardTitle>
            <CardDescription>Pursuits by the source of the lead behind them.</CardDescription>
          </CardHeader>
          <CardContent className="h-64">
            {bySource.length === 0 ? (
              <p className="text-sm text-muted-foreground">No data yet.</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={bySource} layout="vertical" margin={{ left: 24 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} opacity={0.3} />
                  <XAxis type="number" allowDecimals={false} fontSize={11} />
                  <YAxis dataKey="label" type="category" width={90} fontSize={11} />
                  <Tooltip cursor={{ fill: "hsl(var(--muted))" }} />
                  <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                    {bySource.map((entry) => (
                      <Cell key={entry.label} fill="#0B7FB3" />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Value by stage</CardTitle>
            <CardDescription>
              What is committed at each point in the pipeline.
              {dash?.mixed_currency ? " Mixed currencies — read with care." : ""}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {LEAD_STAGE_OPTIONS.filter((s) => (dash?.stage_values?.[s.value] ?? 0) > 0).map((s) => (
              <div key={s.value} className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">{s.label}</span>
                <span className="font-medium tabular-nums">
                  {Math.round(dash!.stage_values[s.value]).toLocaleString()}
                </span>
              </div>
            ))}
            {Object.keys(dash?.stage_values ?? {}).length === 0 ? (
              <p className="text-sm text-muted-foreground">No value recorded yet.</p>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
