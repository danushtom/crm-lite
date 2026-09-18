"use client";

import type { CompanyRow, ContactRow, LeadWithOpportunities } from "@dracara/types";
import { Badge, Button, Card, CardContent, Input, Skeleton } from "@dracara/ui";
import { useQuery } from "@tanstack/react-query";
import {
  ChevronsUpDown,
  Clock3,
  LayoutGrid,
  List,
  Search,
  Sparkles,
  Target,
  WalletCards,
  X,
} from "lucide-react";
import { useState, useMemo } from "react";
import Link from "next/link";
import { apiListAll } from "@/lib/api";
import { AddLeadDrawer } from "@/components/leads/add-lead-drawer";
import { AskAiDrawer } from "@/components/ai/ask-ai-drawer";
import { LeadsGallery } from "@/components/leads/leads-gallery";
import { TablePagination } from "@/components/shared/table-pagination";
import { StatsStrip } from "@/components/shared/stats-strip";
import { compareValues, usePagination, useSort } from "@/lib/use-table-controls";
import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { cn } from "@dracara/ui";
import { leadCurrency, leadScore, leadStage, leadValue } from "@/lib/leads";

type LeadSortKey = "projectType" | "stage" | "score" | "value" | "source" | "nextFollowup";

const SORTABLE_COLUMNS: { key: LeadSortKey; label: string }[] = [
  { key: "projectType", label: "Project Name" },
  { key: "stage", label: "Stage" },
  { key: "score", label: "Score" },
  { key: "value", label: "Value" },
  { key: "source", label: "Source" },
  { key: "nextFollowup", label: "Next Follow-up" },
];

type LeadWithCo = LeadWithOpportunities & {
  companies?: { name?: string; segment?: string | null } | null;
};

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
  lost: "bg-rose-100 text-rose-700 dark:rose-900/30 dark:text-rose-300",
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

export default function LeadsPage() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const viewMode = searchParams.get("view") || "list";

  const [showAi, setShowAi] = useState(false);
  // Seeded from ?q= so the global search in the top bar lands here with its term applied.
  const [searchQuery, setSearchQuery] = useState(searchParams.get("q") ?? "");
  const { sortKey, sortDirection, toggleSort } = useSort<LeadSortKey>("score", "desc");
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
      const stage = leadStage(lead);
      const stageStr = (stage ?? "no pursuit").replace(/_/g, " ");

      return {
        id: lead.id,
        projectType: projectTypeStr.charAt(0).toUpperCase() + projectTypeStr.slice(1),
        companyName,
        contactName: contact?.full_name ?? "No contact",
        stage: stageStr.charAt(0).toUpperCase() + stageStr.slice(1),
        rawStage: stage,
        value: leadValue(lead),
        currency: leadCurrency(lead),
        source: sourceStr.charAt(0).toUpperCase() + sourceStr.slice(1),
        score: leadScore(lead),
        // Raw ISO date, not a display string: the gallery formats it as a relative distance
        // and would throw on a pre-formatted value (new Date("Not set") is an Invalid Date).
        nextFollowup: lead.next_followup_date ?? null,
        nextFollowupLabel: lead.next_followup_date
          ? new Date(lead.next_followup_date).toLocaleDateString(undefined, { month: "short", day: "numeric" })
          : "Not set",
      };
    });
  }, [leads, contacts]);

  const searchedRows = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(
      (r) =>
        r.projectType.toLowerCase().includes(q) ||
        r.companyName.toLowerCase().includes(q) ||
        r.contactName.toLowerCase().includes(q) ||
        r.stage.toLowerCase().includes(q) ||
        r.source.toLowerCase().includes(q)
    );
  }, [rows, searchQuery]);

  const sortedRows = useMemo(() => {
    return [...searchedRows].sort((a, b) =>
      compareValues(a[sortKey as keyof typeof a], b[sortKey as keyof typeof b], sortDirection)
    );
  }, [searchedRows, sortKey, sortDirection]);

  const pagination = usePagination(sortedRows);

  const summary = useMemo(() => {
    const totalValue = rows.reduce((sum, row) => sum + row.value, 0);
    const hotCount = rows.filter((r) => r.score >= 80).length;

    // Value and score per source. The score shown on each tile used to be
    // `80 + (globalAverage % 15)` -- the same number on all four tiles regardless of source,
    // which is why every card read "Avg score 85". It is now that source's own average.
    const bySource = new Map<string, { value: number; scoreTotal: number; count: number }>();
    for (const row of rows) {
      const entry = bySource.get(row.source) ?? { value: 0, scoreTotal: 0, count: 0 };
      entry.value += row.value;
      entry.scoreTotal += row.score;
      entry.count += 1;
      bySource.set(row.source, entry);
    }

    const campaigns = Array.from(bySource.entries())
      .map(([name, entry]) => ({
        name,
        value: entry.value,
        count: entry.count,
        avgScore: entry.count > 0 ? Math.round(entry.scoreTotal / entry.count) : 0,
      }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 4);

    return {
      totalValue,
      hotCount,
      totalLeads: rows.length,
      campaigns,
    };
  }, [rows]);

  return (
    <>
      <AskAiDrawer open={showAi} onOpenChange={setShowAi} />
      <div className="-mt-1 space-y-3">
        <div className="flex flex-col gap-2.5 xl:flex-row xl:items-center xl:justify-between">
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search leads…"
                aria-label="Search leads"
                className="h-8 w-full rounded-md border-border/70 pl-8 pr-8 text-xs sm:w-64"
              />
              {searchQuery ? (
                <button
                  type="button"
                  aria-label="Clear search"
                  onClick={() => setSearchQuery("")}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              ) : null}
            </div>
            <Button
              type="button"
              size="sm"
              onClick={() => setShowAi(true)}
              className="h-8 gap-1.5 rounded-md bg-[#0B7FB3] px-3 text-xs font-semibold text-white hover:bg-[#0a6d99]"
            >
              <Sparkles className="h-3.5 w-3.5" />
              Ask AI
            </Button>
          </div>
          <div className="flex items-center gap-2">
            <div className="inline-flex h-8 items-center rounded-md border border-border/70 bg-card p-0.5">
              <button 
                onClick={() => {
                  const p = new URLSearchParams(searchParams.toString());
                  p.set("view", "list");
                  router.push(`${pathname}?${p.toString()}`);
                }}
                className={cn("inline-flex h-6 items-center gap-1 rounded px-2 text-xs transition-colors", viewMode === "list" ? "bg-muted/80 font-semibold text-foreground" : "text-muted-foreground")}
              >
                <List className="h-3.5 w-3.5" />
                List
              </button>
              <button 
                onClick={() => {
                  const p = new URLSearchParams(searchParams.toString());
                  p.set("view", "gallery");
                  router.push(`${pathname}?${p.toString()}`);
                }}
                className={cn("inline-flex h-6 items-center gap-1 rounded px-2 text-xs transition-colors", viewMode === "gallery" ? "bg-muted/80 font-semibold text-foreground" : "text-muted-foreground")}
              >
                <LayoutGrid className="h-3.5 w-3.5" />
                Gallery
              </button>
            </div>
            <AddLeadDrawer />
          </div>
        </div>

      <StatsStrip
        headlineLabel="Total Pipeline Value"
        headline={formatCompactCurrency(summary.totalValue)}
        headlineSuffix={`across ${summary.totalLeads} ${summary.totalLeads === 1 ? "lead" : "leads"}`}
        badge={
          summary.hotCount > 0
            ? { text: `${summary.hotCount} Hot Leads`, tone: "positive" }
            : undefined
        }
        emphasisLabel="Highest value"
        tiles={summary.campaigns.map((campaign, index) => ({
          label: campaign.name,
          // The same formatter as the headline: the tiles used a separate toK() helper that
          // rendered 49.4M as "$49400K", so a card and the total above it disagreed on units.
          value: formatCompactCurrency(campaign.value),
          hint: (
            <>
              {campaign.count} {campaign.count === 1 ? "lead" : "leads"} · avg score{" "}
              <span className="font-semibold text-foreground">{campaign.avgScore}</span>
            </>
          ),
          emphasis: index === 0,
        }))}
      />

      <Card className="rounded-xl border border-border/70 shadow-[0_1px_3px_rgba(15,23,42,0.06)]">
        <CardContent className="overflow-x-auto px-3 py-2">
          {error ? (
            <p className="text-sm text-destructive">{error.message}</p>
          ) : isLoading ? (
            <table className="w-full min-w-[920px] border-collapse text-sm">
              <thead>
                  <tr className="border-b border-border/70 text-left text-[11px] font-semibold text-muted-foreground">
                    <th className="w-8 py-2.5">
                      <input type="checkbox" className="h-3.5 w-3.5 rounded border-border" disabled />
                    </th>
                    <th className="py-2.5 pr-4">Project Name</th>
                    <th className="py-2.5 pr-4">Stage</th>
                    <th className="py-2.5 pr-4">Score</th>
                    <th className="py-2.5 pr-4">Value</th>
                    <th className="py-2.5 pr-4">Source</th>
                    <th className="py-2.5 pr-4">Next Follow-up</th>
                  </tr>
              </thead>
              <tbody>
                {Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i} className="border-b border-border/50">
                    <td className="w-8 py-2.5"><Skeleton className="h-3.5 w-3.5 rounded" /></td>
                    <td className="py-2.5 pr-4">
                      <div className="space-y-1.5">
                        <Skeleton className="h-4 w-32" />
                        <Skeleton className="h-3 w-24" />
                      </div>
                    </td>
                    <td className="py-2.5 pr-4"><Skeleton className="h-5 w-20 rounded-full" /></td>
                    <td className="py-2.5 pr-4"><Skeleton className="h-5 w-8 rounded-full" /></td>
                    <td className="py-2.5 pr-4"><Skeleton className="h-4 w-16" /></td>
                    <td className="py-2.5 pr-4"><Skeleton className="h-4 w-20" /></td>
                    <td className="py-2.5 pr-4"><Skeleton className="h-4 w-16" /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : rows.length === 0 ? (
            <p className="text-sm text-muted-foreground">No leads yet.</p>
          ) : viewMode === "gallery" ? (
            <LeadsGallery leads={rows} />
          ) : (
              <table className="w-full min-w-[920px] border-collapse text-sm">
              <thead>
                  <tr className="border-b border-border/70 text-left text-[11px] font-semibold text-muted-foreground select-none">
                    {SORTABLE_COLUMNS.map((col) => (
                      <th
                        key={col.key}
                        className="cursor-pointer py-2.5 pr-4 hover:text-foreground"
                        onClick={() => toggleSort(col.key)}
                        aria-sort={
                          sortKey === col.key
                            ? sortDirection === "asc"
                              ? "ascending"
                              : "descending"
                            : "none"
                        }
                      >
                        <div className="inline-flex items-center gap-1.5">
                          {col.label}
                          <ChevronsUpDown
                            className={cn("h-3 w-3", sortKey === col.key && "text-foreground")}
                          />
                        </div>
                      </th>
                    ))}
                </tr>
              </thead>
              <tbody>
                {pagination.pageRows.map((lead, index) => (
                  <tr
                    key={lead.id}
                    className="group border-b border-border/50 transition-colors hover:bg-muted/30 animate-in fade-in slide-in-from-bottom-2 duration-500 fill-mode-both"
                    style={{ animationDelay: `${index * 50}ms` }}
                  >
                      <td className="py-2.5 pr-4">
                        <div className="leading-tight">
                          <Link href={`/leads/${lead.id}`} className="text-[13px] font-semibold text-foreground underline-offset-2 hover:underline">
                            {lead.projectType} at {lead.companyName}
                          </Link>
                          <p className="text-[11px] text-muted-foreground mt-0.5">{lead.contactName}</p>
                        </div>
                      </td>
                      <td className="py-2.5 pr-4">
                        <Badge className={`font-medium ${(lead.rawStage && STAGE_VARIANTS[lead.rawStage]) || STAGE_VARIANTS.prospect}`}>
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
                      <td className="py-2.5 pr-4 text-muted-foreground">{lead.nextFollowupLabel}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      {viewMode === "list" ? (
        <TablePagination
          page={pagination.page}
          pageCount={pagination.pageCount}
          pageSize={pagination.pageSize}
          total={pagination.total}
          onPageChange={pagination.setPage}
          onPageSizeChange={pagination.setPageSize}
        />
      ) : null}
      </div>
    </>
  );
}
