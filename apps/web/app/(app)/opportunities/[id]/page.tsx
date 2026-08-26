"use client";

import { Badge, Button, Card, CardContent, CardHeader, CardTitle, cn } from "@dracara/ui";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { OpportunityDrawer } from "@/components/opportunities/opportunity-drawer";
import { 
  FileText, 
  Layers, 
  Terminal, 
  Clock, 
  ChevronRight, 
  DollarSign, 
  Percent, 
  Calendar,
  ExternalLink,
  Plus
} from "lucide-react";
import { format, parseISO } from "date-fns";

type Proposal = {
  id: string;
  version: number;
  title: string;
  status: string;
  quoted_price: number;
  created_at: string;
};

type OpportunityData = {
  id: string;
  lead_id: string;
  title: string;
  stage: string;
  quoted_value: number;
  currency: string;
  deal_probability: number;
  timeline_weeks: number;
  tech_stack: string;
  requirements_doc: string;
  architecture_notes: string;
  proposals?: Proposal[];
};

export default function OpportunityOverview() {
  const { id } = useParams<{ id: string }>();

  const { data: opp, isLoading } = useQuery({
    queryKey: ["opportunity", id],
    queryFn: () => apiFetch<OpportunityData>(`/opportunities/${id}`),
  });

  if (isLoading || !opp) return <div className="space-y-6 animate-pulse">
    <div className="h-64 bg-muted/40 rounded-xl" />
    <div className="grid grid-cols-3 gap-6">
      <div className="h-96 bg-muted/20 rounded-xl col-span-2" />
      <div className="h-96 bg-muted/20 rounded-xl" />
    </div>
  </div>;

  const formatCurrency = (val: number, curr: string) => {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: curr || "USD",
      maximumFractionDigits: 0,
    }).format(val || 0);
  };

  const proposals = opp.proposals || [];

  const kpiCardClass = "rounded-xl border border-border/70 bg-card shadow-sm overflow-hidden";

  return (
    <div className="space-y-6">
      {/* Commercial KPIs */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card className={kpiCardClass}>
          <CardContent className="p-4 flex flex-col justify-between h-full">
            <div className="flex items-center justify-between text-muted-foreground">
              <span className="text-[10px] font-bold uppercase tracking-wider">Quoted Value</span>
              <DollarSign className="h-4 w-4" />
            </div>
            <p className="mt-3 text-2xl font-bold text-foreground">{formatCurrency(opp.quoted_value, opp.currency)}</p>
          </CardContent>
        </Card>

        <Card className={kpiCardClass}>
          <CardContent className="p-4 flex flex-col justify-between h-full">
            <div className="flex items-center justify-between text-muted-foreground">
              <span className="text-[10px] font-bold uppercase tracking-wider">Win Probability</span>
              <Percent className="h-4 w-4" />
            </div>
            <div className="mt-3">
              <p className="text-2xl font-bold text-foreground">{opp.deal_probability}%</p>
              <div className="mt-2 h-1.5 w-full rounded-full bg-muted overflow-hidden">
                <div 
                  className={cn(
                    "h-full rounded-full",
                    opp.deal_probability >= 70 ? "bg-emerald-500" : opp.deal_probability >= 40 ? "bg-amber-500" : "bg-rose-500"
                  )} 
                  style={{ width: `${opp.deal_probability}%` }} 
                />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className={kpiCardClass}>
          <CardContent className="p-4 flex flex-col justify-between h-full">
            <div className="flex items-center justify-between text-muted-foreground">
              <span className="text-[10px] font-bold uppercase tracking-wider">Est. Timeline</span>
              <Clock className="h-4 w-4" />
            </div>
            <p className="mt-3 text-2xl font-bold text-foreground">{opp.timeline_weeks || "—"} <span className="text-sm font-normal text-muted-foreground">weeks</span></p>
          </CardContent>
        </Card>

        <Card className={kpiCardClass}>
          <CardContent className="p-4 flex flex-col justify-between h-full">
            <div className="flex items-center justify-between text-muted-foreground">
              <span className="text-[10px] font-bold uppercase tracking-wider">Next Step</span>
              <Calendar className="h-4 w-4" />
            </div>
            <p className="mt-3 text-sm font-medium text-foreground">Review Proposal v{proposals.length || 1}</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Left Column: Technical Context */}
        <div className="space-y-6 lg:col-span-2">
          <Card className="rounded-xl border border-border/70 shadow-sm">
            <CardHeader className="border-b border-border/50 pb-3">
              <CardTitle className="flex items-center gap-2 text-base font-semibold">
                <Terminal className="h-4 w-4 text-indigo-600" />
                Technical Blueprint
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-4 space-y-6">
              <div className="grid gap-6 sm:grid-cols-2">
                <div className="space-y-2">
                  <h4 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Tech Stack</h4>
                  <p className="text-sm text-foreground leading-relaxed">
                    {opp.tech_stack || "No technical stack defined yet."}
                  </p>
                </div>
                <div className="space-y-2">
                  <h4 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Architecture Notes</h4>
                  <p className="text-sm text-foreground leading-relaxed">
                    {opp.architecture_notes || "No architectural constraints logged."}
                  </p>
                </div>
              </div>
              <div className="space-y-2 border-t border-border/50 pt-4">
                <h4 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Requirements Summary</h4>
                <div className="rounded-lg bg-muted/20 p-4 border border-border/40">
                  <p className="text-sm text-foreground whitespace-pre-wrap leading-relaxed italic text-muted-foreground">
                    &ldquo;{opp.requirements_doc || "Requirements document has not been drafted yet."}&rdquo;
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Proposals Section */}
          <Card className="rounded-xl border border-border/70 shadow-sm">
            <CardHeader className="flex flex-row items-center justify-between border-b border-border/50 pb-3">
              <CardTitle className="flex items-center gap-2 text-base font-semibold">
                <FileText className="h-4 w-4 text-indigo-600" />
                Proposals
              </CardTitle>
              <Button size="sm" variant="outline" className="h-8 gap-1.5 text-xs">
                <Plus className="h-3.5 w-3.5" />
                New Version
              </Button>
            </CardHeader>
            <CardContent className="pt-4">
              {proposals.length > 0 ? (
                <div className="space-y-3">
                  {proposals.map((p) => (
                    <div key={p.id} className="flex items-center justify-between rounded-lg border border-border/60 bg-muted/10 p-3 hover:bg-muted/20 transition-colors group">
                      <div className="flex items-center gap-3">
                        <div className="flex h-9 w-9 items-center justify-center rounded bg-white shadow-sm border border-border/50 dark:bg-card">
                          <FileText className="h-5 w-5 text-indigo-500" />
                        </div>
                        <div>
                          <p className="text-sm font-semibold text-foreground">v{p.version} · {p.title}</p>
                          <p className="text-[11px] text-muted-foreground">
                            {format(parseISO(p.created_at), "MMM d, yyyy")} · {formatCurrency(p.quoted_price, opp.currency)}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className="capitalize text-[10px]">
                          {p.status}
                        </Badge>
                        <Button variant="ghost" size="icon" className="h-8 w-8 opacity-0 group-hover:opacity-100 transition-opacity">
                          <ExternalLink className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="py-8 text-center">
                  <p className="text-sm text-muted-foreground">No proposals drafted yet.</p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right Column: Meta & Links */}
        <div className="space-y-6">
          <Card className="rounded-xl border border-border/70 shadow-sm">
            <CardHeader className="border-b border-border/50 pb-3">
              <CardTitle className="flex items-center gap-2 text-base font-semibold">
                <Layers className="h-4 w-4 text-muted-foreground" />
                Source Lead
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-4">
              <div className="rounded-lg border border-indigo-100 bg-indigo-50/50 p-4 dark:border-indigo-900/30 dark:bg-indigo-900/10">
                <p className="text-xs text-indigo-700 dark:text-indigo-300 font-medium mb-1">Origin Lead Record</p>
                <p className="text-sm font-semibold text-foreground mb-3">{opp.title}</p>
                <Button size="sm" className="w-full h-8 gap-1.5 text-xs bg-indigo-600 hover:bg-indigo-700" asChild>
                  <Link href={`/leads/${opp.lead_id}`}>
                    Go to Lead View
                    <ChevronRight className="h-3.5 w-3.5" />
                  </Link>
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
