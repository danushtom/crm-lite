"use client";

import { Badge, Button, Card, CardContent, CardHeader, CardTitle } from "@dracara/ui";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { ChevronRight, Layers } from "lucide-react";

export default function LeadOpportunitiesPage() {
  const { id } = useParams<{ id: string }>();

  const { data: oppRows = [], isLoading } = useQuery({
    queryKey: ["opportunity-by-lead", id],
    queryFn: () => apiFetch<Record<string, unknown>[]>(`/opportunities?lead_id=${encodeURIComponent(id)}`),
  });

  const humanizeUnderscore = (s: string) =>
    s
      .split("_")
      .filter(Boolean)
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ");

  const formatCurrency = (val: unknown, curr: unknown) => {
    if (val == null) return "—";
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: String(curr ?? "USD"),
      maximumFractionDigits: 0,
    }).format(Number(val));
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">Opportunities</h2>
        <p className="mt-1 text-sm text-muted-foreground">Commercial deals and pipeline records for this lead.</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading opportunities…</p>
        ) : oppRows.length > 0 ? (
          oppRows.map((opp) => (
            <Card key={String(opp.id)} className="rounded-xl border border-border/70 bg-card shadow-sm">
              <CardHeader className="border-b border-border/40 pb-3">
                <div className="flex items-start justify-between">
                  <CardTitle className="text-base font-semibold">{String(opp.title || "Untitled Opportunity")}</CardTitle>
                  <Badge variant="outline" className="capitalize">
                    {humanizeUnderscore(String(opp.stage))}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="pt-4">
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <p className="text-xs text-muted-foreground uppercase font-bold tracking-wider">Value</p>
                    <p className="mt-1 font-semibold text-lg">{formatCurrency(opp.quoted_value, opp.currency)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground uppercase font-bold tracking-wider">Probability</p>
                    <p className="mt-1 font-semibold text-lg">{String(opp.deal_probability)}%</p>
                  </div>
                </div>
                <div className="mt-6 flex justify-end">
                  <Button size="sm" variant="secondary" className="gap-1.5" asChild>
                    <Link href={`/opportunities/${String(opp.id)}`}>
                      Open Details
                      <ChevronRight className="h-4 w-4" />
                    </Link>
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))
        ) : (
          <Card className="col-span-full py-20 text-center border-dashed">
            <CardContent>
              <p className="text-sm text-muted-foreground">No active opportunities found.</p>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
