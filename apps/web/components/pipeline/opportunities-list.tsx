"use client";

import { useQuery } from "@tanstack/react-query";
import { apiListAll } from "@/lib/api";
import type { OpportunityRow } from "@dracara/types";
import { format, parseISO } from "date-fns";
import Link from "next/link";
import { Skeleton } from "@dracara/ui";

type OpportunityWithLead = OpportunityRow & {
  leads?: {
    project_type?: string | null;
    companies?: { name?: string | null } | null;
  } | null;
};

export function OpportunitiesList() {
  const { data: opportunities = [], isLoading } = useQuery({
    queryKey: ["opportunities", "pipeline"],
    queryFn: () => apiListAll<OpportunityWithLead>("/opportunities"),
  });

  if (isLoading) {
    return (
      <div className="rounded-lg border border-border overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 border-b border-border">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground w-1/3">Name</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Company</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Stage</th>
              <th className="px-4 py-3 text-right font-medium text-muted-foreground">Value</th>
              <th className="px-4 py-3 text-right font-medium text-muted-foreground">Last Updated</th>
            </tr>
          </thead>
          <tbody>
            {[1, 2, 3, 4, 5].map(i => (
              <tr key={i} className="border-b border-border/50">
                <td className="px-4 py-3"><Skeleton className="h-4 w-3/4" /></td>
                <td className="px-4 py-3"><Skeleton className="h-4 w-1/2" /></td>
                <td className="px-4 py-3"><Skeleton className="h-4 w-24" /></td>
                <td className="px-4 py-3 text-right"><Skeleton className="h-4 w-16 ml-auto" /></td>
                <td className="px-4 py-3 text-right"><Skeleton className="h-4 w-20 ml-auto" /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border overflow-hidden bg-card animate-in slide-in-from-bottom-2 fade-in duration-300">
      <table className="w-full text-sm">
        <thead className="bg-muted/50 border-b border-border">
          <tr>
            <th className="px-4 py-3 text-left font-medium text-muted-foreground w-1/3">Name</th>
            <th className="px-4 py-3 text-left font-medium text-muted-foreground">Company</th>
            <th className="px-4 py-3 text-left font-medium text-muted-foreground">Stage</th>
            <th className="px-4 py-3 text-right font-medium text-muted-foreground">Value</th>
            <th className="px-4 py-3 text-right font-medium text-muted-foreground">Last Updated</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border/50">
          {opportunities.length === 0 ? (
            <tr>
              <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">
                No opportunities found.
              </td>
            </tr>
          ) : (
            opportunities.map((opp) => {
              const companyName = opp.leads?.companies?.name ?? "Unknown company";
              const stageStr = opp.stage.replace(/_/g, " ");
              const displayStage = stageStr.charAt(0).toUpperCase() + stageStr.slice(1);
              
              let displayValue = "—";
              if (opp.quoted_value != null) {
                const currency = opp.currency ?? "USD";
                displayValue = new Intl.NumberFormat("en-US", {
                  style: "currency",
                  currency: currency,
                  maximumFractionDigits: 0,
                }).format(Number(opp.quoted_value));
              }

              return (
                <tr key={opp.id} className="group hover:bg-muted/30 transition-colors">
                  <td className="px-4 py-3">
                    <Link href={`/opportunities/${opp.id}`} className="font-medium text-foreground hover:underline">
                      {opp.leads?.project_type || "Opportunity"}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{companyName}</td>
                  <td className="px-4 py-3">
                    <span className="inline-flex items-center rounded-md bg-muted px-2 py-1 text-xs font-medium text-muted-foreground ring-1 ring-inset ring-border/50">
                      {displayStage}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right font-medium">{displayValue}</td>
                  <td className="px-4 py-3 text-right text-muted-foreground">
                    {(() => {
                      try {
                        return format(parseISO(opp.updated_at), "MMM d, yyyy");
                      } catch {
                        return "Unknown";
                      }
                    })()}
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}
