"use client";

import { useQuery } from "@tanstack/react-query";
import { apiListAll } from "@/lib/api";
import type { OpportunityRow } from "@dracara/types";
import { format, parseISO } from "date-fns";
import Link from "next/link";
import { Skeleton } from "@dracara/ui";
import { Clock } from "lucide-react";

type OpportunityWithLead = OpportunityRow & {
  leads?: {
    project_type?: string | null;
    companies?: { name?: string | null } | null;
  } | null;
};

export function OpportunitiesTimeline() {
  const { data: opportunities = [], isLoading } = useQuery({
    queryKey: ["opportunities", "pipeline"],
    queryFn: () => apiListAll<OpportunityWithLead>("/opportunities"),
  });

  if (isLoading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="flex gap-4">
            <div className="w-24 shrink-0 text-right">
              <Skeleton className="h-4 w-16 ml-auto" />
            </div>
            <div className="relative pb-6">
              <div className="absolute left-1/2 top-1.5 h-full w-px -translate-x-1/2 bg-border" />
              <div className="absolute left-1/2 top-1.5 h-2.5 w-2.5 -translate-x-1/2 rounded-full bg-muted border border-border" />
            </div>
            <div className="flex-1 rounded-lg border border-border bg-card p-4">
              <Skeleton className="h-5 w-1/3 mb-2" />
              <Skeleton className="h-4 w-1/4" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  // Sort by updated_at descending
  const sorted = [...opportunities].sort((a, b) => {
    return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
  });

  return (
    <div className="animate-in slide-in-from-bottom-2 fade-in duration-300">
      <div className="space-y-6">
        {sorted.length === 0 ? (
          <div className="rounded-lg border border-border bg-card p-8 text-center text-muted-foreground">
            No opportunities found in the timeline.
          </div>
        ) : (
          sorted.map((opp, i) => {
            const companyName = opp.leads?.companies?.name ?? "Unknown company";
            const stageStr = opp.stage.replace(/_/g, " ");
            const displayStage = stageStr.charAt(0).toUpperCase() + stageStr.slice(1);
            const isLast = i === sorted.length - 1;
            
            let displayValue = "—";
            if (opp.quoted_value != null) {
              const currency = opp.currency ?? "USD";
              displayValue = new Intl.NumberFormat("en-US", {
                style: "currency",
                currency: currency,
                maximumFractionDigits: 0,
              }).format(Number(opp.quoted_value));
            }

            let dateLabel = "Unknown";
            let timeLabel = "";
            try {
              const d = parseISO(opp.updated_at);
              dateLabel = format(d, "MMM d");
              timeLabel = format(d, "h:mm a");
            } catch {
              // ignore
            }

            return (
              <div key={opp.id} className="group flex gap-4">
                <div className="w-24 shrink-0 text-right pt-0.5">
                  <div className="text-sm font-semibold text-foreground">{dateLabel}</div>
                  <div className="text-xs text-muted-foreground">{timeLabel}</div>
                </div>
                
                <div className="relative">
                  {!isLast && <div className="absolute left-1/2 top-3 h-full w-px -translate-x-1/2 bg-border group-hover:bg-primary/20 transition-colors" />}
                  <div className="relative z-10 flex h-6 w-6 items-center justify-center rounded-full border border-border bg-card ring-4 ring-[hsl(var(--canvas))]">
                    <Clock className="h-3 w-3 text-muted-foreground" />
                  </div>
                </div>

                <div className="flex-1 pb-6">
                  <Link href={`/opportunities/${opp.id}`}>
                    <div className="rounded-lg border border-border bg-card p-4 shadow-sm transition-all hover:border-primary/50 hover:shadow-md">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div>
                          <h4 className="font-semibold text-foreground">{opp.leads?.project_type || "Opportunity"}</h4>
                          <p className="text-sm text-muted-foreground">{companyName}</p>
                        </div>
                        <div className="text-right">
                          <div className="font-semibold text-foreground">{displayValue}</div>
                          <span className="inline-flex items-center rounded-md bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground ring-1 ring-inset ring-border/50">
                            {displayStage}
                          </span>
                        </div>
                      </div>
                    </div>
                  </Link>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
