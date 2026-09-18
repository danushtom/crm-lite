"use client";

/**
 * Deals the nightly AI pass flagged as stalling.
 *
 * Renders nothing at all when AI is off, when the job has not run yet, or when nothing is at
 * risk — a dashboard card that permanently reads "0 deals at risk" trains people to ignore the
 * space it occupies.
 */

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle, cn } from "@dracara/ui";
import { AlertTriangle, ArrowRight } from "lucide-react";
import { apiFetch } from "@/lib/api";

type DealHealthSnapshot = {
  opportunity_id: string;
  opportunity_title: string | null;
  company_name: string | null;
  risk_level: "low" | "medium" | "high";
  reasons: string[];
  suggested_action: string | null;
  assessed_by_model: boolean;
  generated_at: string | null;
};

const RISK_STYLES: Record<string, string> = {
  high: "bg-destructive/10 text-destructive",
  medium: "bg-amber-500/10 text-amber-600 dark:text-amber-400",
  low: "bg-muted text-muted-foreground",
};

export function DealsAtRisk() {
  const { data: status } = useQuery({
    queryKey: ["ai", "status"],
    queryFn: () => apiFetch<{ configured: boolean }>("/ai/status"),
    staleTime: 5 * 60 * 1000,
  });

  const { data: snapshots } = useQuery({
    queryKey: ["ai", "deal-health"],
    queryFn: () => apiFetch<DealHealthSnapshot[]>("/ai/deal-health?limit=25"),
    enabled: Boolean(status?.configured),
  });

  const atRisk = (snapshots ?? []).filter((s) => s.risk_level !== "low");
  if (!status?.configured || atRisk.length === 0) return null;

  return (
    <Card className="border border-border/70">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
        <CardTitle className="flex items-center gap-2 text-sm font-semibold">
          <AlertTriangle className="h-4 w-4 text-amber-500" />
          {atRisk.length} deal{atRisk.length === 1 ? "" : "s"} at risk
        </CardTitle>
        <span className="text-[11px] text-muted-foreground">Reviewed nightly</span>
      </CardHeader>
      <CardContent className="space-y-2 pt-0">
        {atRisk.slice(0, 5).map((snapshot) => (
          <Link
            key={snapshot.opportunity_id}
            href={`/opportunities/${snapshot.opportunity_id}`}
            className="group flex items-start gap-3 rounded-lg border border-border/60 px-3 py-2.5 transition-colors hover:bg-muted/50"
          >
            <span
              className={cn(
                "mt-0.5 shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium uppercase",
                RISK_STYLES[snapshot.risk_level],
              )}
            >
              {snapshot.risk_level}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-foreground">
                {snapshot.opportunity_title || "Untitled deal"}
                {snapshot.company_name && (
                  <span className="font-normal text-muted-foreground"> · {snapshot.company_name}</span>
                )}
              </p>
              <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
                {snapshot.suggested_action || snapshot.reasons.slice(0, 2).join(" · ")}
              </p>
            </div>
            <ArrowRight className="mt-1 h-3.5 w-3.5 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
          </Link>
        ))}
        {atRisk.length > 5 && (
          <p className="pt-1 text-[11px] text-muted-foreground">
            and {atRisk.length - 5} more
          </p>
        )}
      </CardContent>
    </Card>
  );
}
