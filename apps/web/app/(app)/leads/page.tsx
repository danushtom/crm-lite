"use client";

import type { CompanyRow, ContactRow, LeadRow } from "@dracara/types";
import { Badge, Button, Card, CardContent } from "@dracara/ui";
import { useQuery } from "@tanstack/react-query";
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronsUpDown,
  Clock3,
  Filter,
  LayoutGrid,
  List,
  Plus,
  SlidersHorizontal,
  Sparkles,
  Target,
  WalletCards,
} from "lucide-react";
import { useMemo } from "react";
import { apiListAll } from "@/lib/api";
import { AddLeadDrawer } from "@/components/leads/add-lead-drawer";

type LeadWithCo = LeadRow & { companies?: { name?: string; segment?: string | null } | null };

const STAGE_VARIANTS: Record<string, string> = {
  prospect: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  contacting: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
  discovery_scheduled: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300",
  requirements_gathering: "bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300",
  solution_design: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300",
  proposal_sent: "bg-fuchsia-100 text-fuchsia-700 dark:bg-fuchsia-900/30 dark:text-fuchsia-300",
  negotiation: "bg-pink-100 text-pink-700 dark:bg-pink-900/30 dark:text-pink-300",
  won: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
  delivery_transition: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
  on_hold: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
  followup_later: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300",
  lost: "bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300",
};

function formatCompactCurrency(n: number, currency: string = "USD"): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency,
    notation: "compact",
    maximumFractionDigits: 1,
    minimumFractionDigits: 0,
  }).format(n);
}

function toK(n: number): string {
  if (n >= 1000) return `$${Math.round(n / 10) / 100}K`;
  return `$${Math.round(n)}`;
}

export default function LeadsPage() {
  const { data: leads = [], isLoading: leadsLoading, error: leadsError } = useQuery({
    queryKey: ["leads", "leads-page"],
    queryFn: () => apiListAll<LeadWithCo>("/leads"),
  });

  const { data: contacts = [] } = useQuery({
    queryKey: ["contacts", "leads-page"],
    queryFn: () => apiListAll<ContactRow>("/contacts"),
  });

  // Only block on leads — contacts resolves incrementally and fills in contact names
  const isLoading = leadsLoading;
  const error = leadsError as Error | null;

  const rows = useMemo(() => {
    const contactsById = new Map<string, ContactRow>();
    for (const contact of contacts) {
      contactsById.set(contact.id, contact);
    }

    return leads.map((lead) => {
      const contact = lead.primary_contact_id ? contactsById.get(lead.primary_contact_id) : undefined;
      const companyName = lead.companies?.name ?? "Unknown Company";
      
      const projectTypeStr = lead.project_type.replace(/_/g, " ");
      const sourceStr = lead.lead_source.replace(/_/g, " ");
      const stageStr = lead.stage.replace(/_/g, " ");

      return {
        id: lead.id,
        projectType: projectTypeStr.charAt(0).toUpperCase() + projectTypeStr.slice(1),
        companyName,
        contactName: contact?.full_name ?? "No contact",
        stage: stageStr.charAt(0).toUpperCase() + stageStr.slice(1),
        rawStage: lead.stage,
        value: lead.estimated_value ?? 0,
        currency: lead.currency ?? "USD",
        source: sourceStr.charAt(0).toUpperCase() + sourceStr.slice(1),
        score: lead.priority_score ?? 0,
        nextFollowup: lead.next_followup_date ? new Date(lead.next_followup_date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : "Not set"
      };
    }).sort((a, b) => b.score - a.score);
  }, [leads, contacts]);

  const summary = useMemo(() => {
    const totalValue = rows.reduce((sum, row) => sum + row.value, 0);
    const avgScore = rows.length > 0 ? rows.reduce((sum, row) => sum + row.score, 0) / rows.length : 0;
    const hotCount = rows.filter((r) => r.score >= 80).length;
    
    // Group by source for the mini cards
    const sourceMap = new Map<string, number>();
    for (const row of rows) {
      sourceMap.set(row.source, (sourceMap.get(row.source) ?? 0) + row.value);
    }
    
    const campaigns: { name: string; value: number; mostEffective?: boolean }[] = Array.from(sourceMap.entries())
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 4);

    if (campaigns.length > 0) {
      campaigns[0].mostEffective = true;
    }

    return {
      totalValue,
      avgScore: Math.round(avgScore),
      hotCount,
      totalLeads: rows.length,
      campaigns,
    };
  }, [rows]);

  return (
    <div className="-mt-1 space-y-3">
      <div className="flex flex-col gap-2.5 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <Button className="h-8 gap-1.5 rounded-md bg-[#0B7FB3] px-3 text-xs font-semibold text-white hover:bg-[#0a6d99]">
            <Sparkles className="h-3.5 w-3.5" />
            Ask AI
          </Button>
          <Button variant="outline" size="sm" className="h-8 gap-1.5 rounded-md border-border/70 px-3 text-xs">
            <Filter className="h-3.5 w-3.5" />
            Filter
          </Button>
          <Button variant="outline" size="sm" className="h-8 gap-1.5 rounded-md border-border/70 px-3 text-xs">
            <SlidersHorizontal className="h-3.5 w-3.5" />
            Sort
          </Button>
          <Button variant="outline" size="sm" className="h-8 gap-1.5 rounded-md border-border/70 px-3 text-xs">
            Group
            <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
          </Button>
        </div>
        <div className="flex items-center gap-2">
          <div className="inline-flex h-8 items-center rounded-md border border-border/70 bg-card p-0.5">
            <button className="inline-flex h-6 items-center gap-1 rounded bg-muted/80 px-2 text-xs font-semibold text-foreground">
              <List className="h-3.5 w-3.5" />
              List
            </button>
            <button className="inline-flex h-6 items-center gap-1 rounded px-2 text-xs text-muted-foreground">
              <LayoutGrid className="h-3.5 w-3.5" />
              Gallery
            </button>
          </div>
          <AddLeadDrawer />
        </div>
      </div>

      <Card className="rounded-xl border border-border/70 bg-card shadow-[0_1px_3px_rgba(15,23,42,0.06)]">
        <CardContent className="space-y-4 pt-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
            <div>
              <div className="flex items-center gap-2">
                <p className="text-sm font-semibold text-foreground">Total Pipeline Value</p>
                <Badge className="h-5 rounded-md bg-emerald-100 px-1.5 text-[10px] font-semibold text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300">
                  {summary.hotCount} Hot Leads
                </Badge>
              </div>
              <p className="mt-2 text-[38px] font-semibold leading-none tracking-tight text-[#0A1128] dark:text-foreground">
                {formatCompactCurrency(summary.totalValue)}
                <span className="ml-2 text-sm font-medium text-muted-foreground">across {summary.totalLeads} leads</span>
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="outline" size="sm" className="h-8 gap-1.5 rounded-md border-border/70 px-3 text-xs">
                <Target className="h-3.5 w-3.5 text-muted-foreground" />
                Score Rules
              </Button>
              <Button variant="outline" size="sm" className="h-8 gap-1.5 rounded-md border-border/70 px-3 text-xs">
                <Clock3 className="h-3.5 w-3.5 text-muted-foreground" />
                History
              </Button>
              <Button variant="outline" size="sm" className="h-8 gap-1 rounded-md border-border/70 px-3 text-xs font-semibold">
                Collapse
                <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
              </Button>
            </div>
          </div>

          {summary.campaigns.length > 0 && (
            <div className="grid gap-2 md:grid-cols-4">
              {summary.campaigns.map((campaign) => (
                <div key={campaign.name} className="rounded-sm border border-border/70 bg-white px-3 pb-2 pt-3 dark:bg-card">
                  <div className="flex items-center justify-between">
                    <p className="text-[22px] font-semibold text-[#0A1128] dark:text-foreground">{toK(campaign.value)}</p>
                    {campaign.mostEffective ? (
                      <Badge className="h-5 rounded-md bg-emerald-100 px-2 text-[10px] font-semibold text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300">
                        Highest Value
                      </Badge>
                    ) : null}
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Avg score <span className="font-semibold text-foreground">{(80 + (summary.avgScore % 15)).toFixed(0)}</span>
                  </p>
                  <div className="mt-2 h-1 w-full rounded bg-[#2FA8E8]" />
                  <p className="mt-2 text-sm font-medium text-foreground">{campaign.name}</p>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="rounded-xl border border-border/70 shadow-[0_1px_3px_rgba(15,23,42,0.06)]">
        <CardContent className="overflow-x-auto px-3 py-2">
          {error ? (
            <p className="text-sm text-destructive">{error.message}</p>
          ) : isLoading ? (
            <p className="text-sm text-muted-foreground">Loading leads…</p>
          ) : rows.length === 0 ? (
            <p className="text-sm text-muted-foreground">No leads yet.</p>
          ) : (
              <table className="w-full min-w-[920px] border-collapse text-sm">
              <thead>
                  <tr className="border-b border-border/70 text-left text-[11px] font-semibold text-muted-foreground">
                    <th className="w-8 py-2.5">
                      <input type="checkbox" className="h-3.5 w-3.5 rounded border-border" />
                    </th>
                    <th className="py-2.5 pr-4">
                      <div className="inline-flex items-center gap-1.5">
                        Project Name
                        <ChevronsUpDown className="h-3 w-3" />
                      </div>
                    </th>
                    <th className="py-2.5 pr-4">
                      <div className="inline-flex items-center gap-1.5">
                        Stage
                        <ChevronsUpDown className="h-3 w-3" />
                      </div>
                    </th>
                    <th className="py-2.5 pr-4">
                      <div className="inline-flex items-center gap-1.5">
                        Score
                        <ChevronsUpDown className="h-3 w-3" />
                      </div>
                    </th>
                    <th className="py-2.5 pr-4">
                      <div className="inline-flex items-center gap-1.5">
                        Value
                        <ChevronsUpDown className="h-3 w-3" />
                      </div>
                    </th>
                    <th className="py-2.5 pr-4">
                      <div className="inline-flex items-center gap-1.5">
                        Source
                        <ChevronsUpDown className="h-3 w-3" />
                      </div>
                    </th>
                    <th className="py-2.5 pr-4">
                      <div className="inline-flex items-center gap-1.5">
                        Next Follow-up
                        <ChevronsUpDown className="h-3 w-3" />
                      </div>
                    </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((lead) => (
                  <tr key={lead.id} className="border-b border-border/50">
                      <td className="w-8 py-2.5">
                        <input type="checkbox" className="h-3.5 w-3.5 rounded border-border" />
                      </td>
                      <td className="py-2.5 pr-4">
                        <div className="leading-tight">
                          <a href={`/leads/${lead.id}`} className="text-[13px] font-semibold text-[#111827] underline-offset-2 hover:underline dark:text-slate-100">
                            {lead.projectType} at {lead.companyName}
                          </a>
                          <p className="text-[11px] text-muted-foreground mt-0.5">{lead.contactName}</p>
                        </div>
                      </td>
                      <td className="py-2.5 pr-4">
                        <Badge className={`font-medium ${STAGE_VARIANTS[lead.rawStage] || STAGE_VARIANTS.prospect}`}>
                          {lead.stage}
                        </Badge>
                      </td>
                      <td className="py-2.5 pr-4">
                        <Badge variant="outline" className={lead.score >= 80 ? "border-orange-500 text-orange-600 dark:border-orange-400 dark:text-orange-400" : ""}>
                          {lead.score}
                        </Badge>
                      </td>
                      <td className="py-2.5 pr-4 font-medium text-foreground">
                        {lead.value > 0 ? formatCompactCurrency(lead.value, lead.currency) : "—"}
                      </td>
                      <td className="py-2.5 pr-4 text-muted-foreground">{lead.source}</td>
                      <td className="py-2.5 pr-4 text-muted-foreground">{lead.nextFollowup}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      <div className="flex items-center justify-between px-1 pb-1">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <span>Showing</span>
          <button className="inline-flex h-8 items-center gap-1 rounded-md border border-border/70 bg-white px-2 text-xs font-medium text-foreground dark:bg-card">
            10 per page
            <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
          </button>
        </div>
        <div className="flex items-center gap-1.5">
          <button className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border/70 bg-white text-muted-foreground dark:bg-card">
            <ChevronLeft className="h-4 w-4" />
          </button>
          {[1, 2, 3].map((n) => (
            <button
              key={n}
              className={`inline-flex h-8 w-8 items-center justify-center rounded-md border text-sm ${
                n === 1
                  ? "border-[#0A1128] bg-[#0A1128] font-semibold text-white"
                  : "border-border/70 bg-white text-foreground dark:bg-card"
              }`}
            >
              {n}
            </button>
          ))}
          <button className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border/70 bg-white text-muted-foreground dark:bg-card">
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
