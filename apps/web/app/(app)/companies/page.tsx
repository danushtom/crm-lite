"use client";

import type { CompanyRow, ContactRow, LeadWithOpportunities } from "@dracara/types";
import { Badge, Button, Card, CardContent, Input, Skeleton } from "@dracara/ui";
import { CompanyDrawer } from "@/components/companies/company-drawer";
import { useQuery } from "@tanstack/react-query";
import {
  ChevronDown,
  ChevronsUpDown,
  LayoutGrid,
  Linkedin,
  List,
  Search,
  X,
} from "lucide-react";
import Link from "next/link";
import { useState, useMemo, useEffect } from "react";
import { apiListAll } from "@/lib/api";
import { leadStage, leadValue } from "@/lib/leads";
import { CompaniesGallery } from "@/components/companies/companies-gallery";
import { Avatar } from "@/components/shared/avatar";
import { TablePagination } from "@/components/shared/table-pagination";
import { compareValues, usePagination, useSort } from "@/lib/use-table-controls";
import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { cn } from "@dracara/ui";

type CompanySortKey = "name" | "stage" | "contactsCount" | "value" | "contactRole";

/** Order here must match the order cells are rendered in the table body. */
const SORTABLE_COLUMNS: { key: CompanySortKey; label: string }[] = [
  { key: "name", label: "Company" },
  { key: "stage", label: "Stage" },
  { key: "contactsCount", label: "Contacts" },
  { key: "value", label: "Pipeline value" },
  { key: "contactRole", label: "Position" },
];

/** Shared with the contacts page so the two stats strips collapse together. */
const STATS_COLLAPSED_KEY = "crm-stats-collapsed";

type CompanyStage = "Won" | "Leads" | "Lost" | "Discovery";

const STAGE_VARIANTS: Record<CompanyStage, string> = {
  Won: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
  Leads: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  Lost: "bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300",
  Discovery: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
};

function leadStageToCompanyStage(stage?: string | null): CompanyStage {
  if (!stage) return "Leads";
  if (stage === "won" || stage === "delivery_transition") return "Won";
  if (stage === "lost") return "Lost";
  if (stage === "discovery_scheduled" || stage === "requirements_gathering") return "Discovery";
  return "Leads";
}

function formatCompactCurrency(n: number): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "USD",
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(n);
}

function toK(n: number): string {
  if (n >= 1000) return `$${Math.round(n / 10) / 100}K`;
  return `$${Math.round(n)}`;
}

export default function CompaniesPage() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const viewMode = searchParams.get("view") || "list";

  // Seeded from ?q= so the global search in the top bar lands here with its term applied.
  const [searchQuery, setSearchQuery] = useState(searchParams.get("q") ?? "");
  const [statsCollapsed, setStatsCollapsed] = useState(false);
  const { sortKey, sortDirection, toggleSort } = useSort<CompanySortKey>("name", "asc");

  useEffect(() => {
    try {
      setStatsCollapsed(localStorage.getItem(STATS_COLLAPSED_KEY) === "true");
    } catch {
      // Blocked storage: default to expanded.
    }
  }, []);

  const toggleStats = () => {
    setStatsCollapsed((collapsed) => {
      const next = !collapsed;
      try {
        localStorage.setItem(STATS_COLLAPSED_KEY, String(next));
      } catch {
        // Non-fatal.
      }
      return next;
    });
  };

  const { data: companies = [], isLoading: companiesLoading, error: companiesError } = useQuery({
    queryKey: ["companies", "list"],
    queryFn: () => apiListAll<CompanyRow>("/companies"),
  });

  const { data: leads = [], isLoading: leadsLoading, error: leadsError } = useQuery({
    queryKey: ["leads", "companies-page"],
    queryFn: () => apiListAll<LeadWithOpportunities>("/leads"),
  });

  const { data: contacts = [], isLoading: contactsLoading, error: contactsError } = useQuery({
    queryKey: ["contacts", "companies-page"],
    queryFn: () => apiListAll<ContactRow>("/contacts"),
  });

  const isLoading = companiesLoading || leadsLoading || contactsLoading;
  const error = (companiesError || leadsError || contactsError) as Error | null;

  const rows = useMemo(() => {
    const leadsByCompany = new Map<string, LeadWithOpportunities[]>();
    for (const lead of leads) {
      const arr = leadsByCompany.get(lead.company_id) ?? [];
      arr.push(lead);
      leadsByCompany.set(lead.company_id, arr);
    }

    const contactsByCompany = new Map<string, ContactRow[]>();
    for (const contact of contacts) {
      const arr = contactsByCompany.get(contact.company_id) ?? [];
      arr.push(contact);
      contactsByCompany.set(contact.company_id, arr);
    }

    return companies.map((company) => {
      const companyLeads = leadsByCompany.get(company.id) ?? [];
      const companyContacts = contactsByCompany.get(company.id) ?? [];
      const latestLead = companyLeads[0];
      const primary = companyContacts.find((c) => c.is_primary) ?? companyContacts[0];
      const stage = leadStageToCompanyStage(
        latestLead ? leadStage(latestLead) ?? undefined : undefined
      );
      // A company with no leads is worth nothing yet -- it is not worth a number derived from
      // the length of its name, which is what this used to display.
      const value = companyLeads.reduce((sum, lead) => sum + (leadValue(lead) ?? 0), 0);

      return {
        id: company.id,
        name: company.name,
        stage,
        value,
        contactName: primary?.full_name ?? "No contact",
        contactRole: primary?.role ?? "Unassigned",
        contactsCount: companyContacts.length,
        industry: company.industry,
        website: company.website ?? null,
        linkedinUrl: company.linkedin_url ?? null,
      };
    });
  }, [companies, contacts, leads]);

  const searchedRows = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(
      (r) =>
        r.name.toLowerCase().includes(q) ||
        (r.industry ?? "").toLowerCase().includes(q) ||
        r.contactName.toLowerCase().includes(q) ||
        r.stage.toLowerCase().includes(q)
    );
  }, [rows, searchQuery]);

  const sortedRows = useMemo(
    () =>
      [...searchedRows].sort((a, b) =>
        compareValues(a[sortKey as keyof typeof a], b[sortKey as keyof typeof b], sortDirection)
      ),
    [searchedRows, sortKey, sortDirection]
  );

  const pagination = usePagination(sortedRows);

  const summary = useMemo(() => {
    const total = rows.reduce((sum, row) => sum + row.value, 0);
    const average = rows.length > 0 ? total / rows.length : 0;
    const discoveryCount = rows.filter((r) => r.stage === "Discovery").length;
    const wonCount = rows.filter((r) => r.stage === "Won").length;
    const lostCount = rows.filter((r) => r.stage === "Lost").length;

    // Real distribution across the companies in view. These four figures used to be
    // generated from a hash of the row count, which made them stable enough to look like
    // data and meant nothing at all.
    const byIndustry = new Map<string, number>();
    for (const row of rows) {
      const key = row.industry?.trim() || "Unspecified";
      byIndustry.set(key, (byIndustry.get(key) ?? 0) + row.value);
    }
    const industryTotal = [...byIndustry.values()].reduce((a, b) => a + b, 0) || 1;
    const campaigns = [...byIndustry.entries()]
      .map(([name, value]) => ({ name, value, pct: Math.round((value / industryTotal) * 100) }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 4)
      .map((c, i) => ({ ...c, mostEffective: i === 0 }));

    return {
      average,
      discoveryCount,
      wonCount,
      lostCount,
      totalCompanies: rows.length,
      campaigns,
    };
  }, [rows]);

  return (
    <div className="-mt-1 space-y-3">
      <div className="flex flex-col gap-2.5 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search companies…"
              aria-label="Search companies"
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
          <CompanyDrawer />
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
        </div>
      </div>

      <Card className="rounded-xl border border-border/70 bg-card shadow-[0_1px_3px_rgba(15,23,42,0.06)]">
        <CardContent className="space-y-4 pt-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
            <div>
              <div className="flex items-center gap-2">
                <p className="text-sm font-semibold text-foreground">Cust. Acquisition Cost</p>
                <Badge className="h-5 rounded-md bg-rose-100 px-1.5 text-[10px] font-semibold text-rose-700 dark:bg-rose-900/30 dark:text-rose-300">
                  {Math.max(1, summary.lostCount)}%
                </Badge>
              </div>
              <p className="mt-2 text-[38px] font-semibold leading-none tracking-tight text-[#0A1128] dark:text-foreground">
                {formatCompactCurrency(summary.average)}
                <span className="ml-1 text-xs font-medium text-muted-foreground">average</span>
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={toggleStats}
                aria-expanded={!statsCollapsed}
                className="h-8 gap-1 rounded-md border-border/70 px-3 text-xs font-semibold"
              >
                {statsCollapsed ? "Expand" : "Collapse"}
                <ChevronDown
                  className={cn(
                    "h-3.5 w-3.5 text-muted-foreground transition-transform",
                    statsCollapsed && "rotate-180"
                  )}
                />
              </Button>
            </div>
          </div>

          <div className={cn("grid gap-2 md:grid-cols-4", statsCollapsed && "hidden")}>
            {summary.campaigns.map((campaign) => (
              <div key={campaign.name} className="rounded-sm border border-border/70 bg-white px-3 pb-2 pt-3 dark:bg-card">
                <div className="flex items-center justify-between">
                  <p className="text-[22px] font-semibold text-[#0A1128] dark:text-foreground">{toK(campaign.value)}</p>
                  {campaign.mostEffective ? (
                    <Badge className="h-5 rounded-md bg-emerald-100 px-2 text-[10px] font-semibold text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300">
                      Most Effective
                    </Badge>
                  ) : null}
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  Bring <span className="font-semibold text-foreground">{campaign.pct}%</span> new cust
                </p>
                <div className="mt-2 h-1 w-full rounded bg-[#2FA8E8]" />
                <p className="mt-2 text-sm font-medium text-foreground">{campaign.name}</p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card className="rounded-xl border border-border/70 shadow-[0_1px_3px_rgba(15,23,42,0.06)]">
        <CardContent className="overflow-x-auto px-3 py-2">
          {error ? (
            <p className="text-sm text-destructive">{(error as Error).message}</p>
          ) : isLoading ? (
            <table className="w-full min-w-[920px] border-collapse text-sm">
              <thead>
                  <tr className="border-b border-border/70 text-left text-[11px] font-semibold text-muted-foreground">
                    {SORTABLE_COLUMNS.map((col) => (
                      <th key={col.key} className="py-2.5 pr-4">{col.label}</th>
                    ))}
                    <th className="py-2.5 pr-4">Links</th>
                  </tr>
              </thead>
              <tbody>
                {Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i} className="border-b border-border/50">
                    <td className="py-2.5 pr-4"><Skeleton className="h-4 w-32" /></td>
                    <td className="py-2.5 pr-4"><Skeleton className="h-5 w-20 rounded-full" /></td>
                    <td className="py-2.5 pr-4">
                      <div className="flex items-center gap-2.5">
                        <Skeleton className="h-8 w-8 rounded-full shrink-0" />
                        <div className="space-y-1.5">
                          <Skeleton className="h-3 w-20" />
                          <Skeleton className="h-2 w-12" />
                        </div>
                      </div>
                    </td>
                    <td className="py-2.5 pr-4"><Skeleton className="h-4 w-16" /></td>
                    <td className="py-2.5 pr-4"><Skeleton className="h-4 w-28" /></td>
                    <td className="py-2.5 pr-4"><Skeleton className="h-4 w-12" /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : rows.length === 0 ? (
            <p className="text-sm text-muted-foreground">No companies yet.</p>
          ) : viewMode === "gallery" ? (
            <CompaniesGallery companies={rows} />
          ) : (
              <table className="w-full min-w-[920px] border-collapse text-sm">
              <thead>
                  <tr className="select-none border-b border-border/70 text-left text-[11px] font-semibold text-muted-foreground">
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
                    <th className="py-2.5 pr-4">Links</th>
                </tr>
              </thead>
              <tbody>
                {pagination.pageRows.map((c, index) => (
                  <tr
                    key={c.id}
                    className="group border-b border-border/50 transition-colors hover:bg-muted/30 animate-in fade-in slide-in-from-bottom-2 duration-500 fill-mode-both"
                    style={{ animationDelay: `${index * 50}ms` }}
                  >
                      <td className="py-2.5 pr-4">
                        {/* The list had no way into a company at all; only the gallery linked
                            here, and until now that link 404ed. */}
                        <Link
                          href={`/companies/${c.id}`}
                          className="text-[13px] font-semibold text-foreground hover:underline hover:underline-offset-2"
                        >
                          {c.name}
                        </Link>
                      </td>
                      <td className="py-2.5 pr-4">
                        <Badge className={`font-medium ${STAGE_VARIANTS[c.stage]}`}>{c.stage}</Badge>
                      </td>
                      <td className="py-2.5 pr-4">
                        <div className="flex items-center gap-2.5">
                          <Avatar name={c.contactName} />
                          <div className="leading-tight">
                            <p className="text-[13px] font-semibold text-foreground">{c.contactName}</p>
                            <p className="text-[11px] text-muted-foreground">{c.contactsCount} total</p>
                          </div>
                        </div>
                      </td>
                      <td className="py-2.5 pr-4 font-medium text-foreground">
                        {c.value > 0 ? formatCompactCurrency(c.value) : "—"}
                      </td>
                      <td className="py-2.5 pr-4 text-muted-foreground">{c.contactRole}</td>
                      <td className="py-2.5 pr-4">
                        {/* Real links only. This column used to render href="#" with the company
                            name in it, which looked like a LinkedIn profile and went nowhere. */}
                        <div className="flex items-center gap-2">
                          {c.linkedinUrl ? (
                            <a
                              href={c.linkedinUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              aria-label={`${c.name} on LinkedIn`}
                              className="text-muted-foreground hover:text-[#0B7FB3]"
                            >
                              <Linkedin className="h-3.5 w-3.5" />
                            </a>
                          ) : null}
                          {c.website ? (
                            <a
                              href={c.website}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-[11px] text-[#0B7FB3] hover:underline"
                            >
                              Website
                            </a>
                          ) : null}
                          {!c.linkedinUrl && !c.website ? (
                            <span className="text-[11px] text-muted-foreground">—</span>
                          ) : null}
                        </div>
                      </td>
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
  );
}
