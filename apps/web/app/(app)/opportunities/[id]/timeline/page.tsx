"use client";

import { Badge, Button, Card, CardContent } from "@dracara/ui";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { apiFetch, apiList } from "@/lib/api";
import { Clock, Info } from "lucide-react";
import { format, parseISO } from "date-fns";

export default function OpportunityInteractionsPage() {
  const { id } = useParams<{ id: string }>();

  // Fetch opportunity to get lead_id
  const { data: opp } = useQuery({
    queryKey: ["opportunity", id],
    queryFn: () => apiFetch<{ lead_id: string }>(`/opportunities/${id}`),
  });

  // Fetch activities for that lead
  const { data: rows = [], isLoading } = useQuery({
    queryKey: ["activities", opp?.lead_id],
    queryFn: () => apiList<Record<string, unknown>>(`/leads/${opp?.lead_id}/activities`),
    enabled: !!opp?.lead_id,
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">Interactions</h2>
          <p className="mt-1 text-sm text-muted-foreground">Historical touchpoints from the initial lead through the sales process.</p>
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-24 w-full bg-muted/40 animate-pulse rounded-lg" />
          ))}
        </div>
      ) : rows.length > 0 ? (
        <div className="relative space-y-6 before:absolute before:inset-0 before:ml-5 before:-translate-x-px before:h-full before:w-0.5 before:bg-border/50">
          {rows.map((a) => (
            <div key={String(a.id)} className="relative flex items-start gap-6 group">
              <div className="z-10 flex h-10 w-10 shrink-0 items-center justify-center rounded-full border-4 border-background bg-indigo-100 text-indigo-600 shadow-sm">
                <Clock className="h-4 w-4" />
              </div>
              <Card className="flex-1 rounded-xl border border-border/70 shadow-sm transition-shadow hover:shadow-md">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between gap-4">
                    <span className="text-[10px] font-bold uppercase tracking-widest text-indigo-600">{String(a.type)}</span>
                    <span className="text-[11px] text-muted-foreground">
                      {a.performed_at ? format(parseISO(String(a.performed_at)), "MMM d, yyyy · h:mm a") : "—"}
                    </span>
                  </div>
                  <p className="mt-2 text-sm text-foreground whitespace-pre-wrap leading-relaxed">{String(a.description)}</p>
                </CardContent>
              </Card>
            </div>
          ))}
        </div>
      ) : (
        <Card className="py-20 text-center border-dashed">
          <div className="flex flex-col items-center gap-2">
            <Info className="h-8 w-8 text-muted-foreground/40" />
            <p className="text-sm text-muted-foreground">No interactions recorded for this deal cycle.</p>
          </div>
        </Card>
      )}
    </div>
  );
}
