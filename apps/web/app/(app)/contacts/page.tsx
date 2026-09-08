"use client";

import type { ContactRow, LeadWithOpportunities } from "@dracara/types";
import { 
  Badge, 
  Button, 
  Card, 
  CardContent,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
  Input,
  Skeleton
} from "@dracara/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useApiMutation } from "@/lib/use-api-mutation";
import {
  ChevronDown,
  ChevronsUpDown,
  Filter,
  LayoutGrid,
  List,
  Plus,
  SlidersHorizontal,
  Sparkles,
  MoreHorizontal,
  Trash2,
  Mail,
  Phone,
  Search,
  X,
  Check,
} from "lucide-react";
import { useMemo, useState, useEffect } from "react";
import { apiFetch, apiListAll } from "@/lib/api";
import Link from "next/link";
import { ContactDrawer } from "@/components/contacts/contact-drawer";
import { ContactsGallery } from "@/components/contacts/contacts-gallery";
import { TablePagination } from "@/components/shared/table-pagination";
import { StatsStrip } from "@/components/shared/stats-strip";
import { LogActivityDrawer } from "@/components/activities/log-activity-drawer";
import { usePagination } from "@/lib/use-table-controls";
import { cn } from "@dracara/ui";
import { leadStage } from "@/lib/leads";
import { useRouter, useSearchParams, usePathname } from "next/navigation";

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

function initials(name: string): string {
  const parts = (name || "").trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 1).toUpperCase();
  return `${parts[0].slice(0, 1)}${parts[1].slice(0, 1)}`.toUpperCase();
}

function formatCompactCurrency(n: number): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "USD",
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(n);
}

type ContactWithCompany = ContactRow & { companies?: { name?: string | null } | null };

function contactPipelineStage(contact: ContactRow, leads: LeadWithOpportunities[]): CompanyStage {
  for (const lead of leads) {
    if (lead.primary_contact_id === contact.id) {
      return leadStageToCompanyStage(leadStage(lead) ?? undefined);
    }
  }
  const leadsByCompany = new Map<string, LeadWithOpportunities[]>();
  for (const lead of leads) {
    const arr = leadsByCompany.get(lead.company_id) ?? [];
    arr.push(lead);
    leadsByCompany.set(lead.company_id, arr);
  }
  const companyLeads = leadsByCompany.get(contact.company_id) ?? [];
  const first = companyLeads[0];
  return leadStageToCompanyStage(first ? leadStage(first) ?? undefined : undefined);
}

export default function ContactsPage() {
  const queryClient = useQueryClient();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const viewMode = searchParams.get("view") || "list";

  // Seeded from ?q= so the global search in the top bar lands here with its term applied.
  const [searchQuery, setSearchQuery] = useState(searchParams.get("q") ?? "");
  const [selectedStage, setSelectedStage] = useState<string>("all");
  const [sortField, setSortField] = useState<"name" | "company" | "role" | "stage" | "source">("name");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");
  // Open the filter panel when arriving with a search term, so the active filter that is
  // shrinking the table is visible rather than hidden behind a collapsed toggle.
  const [showFilters, setShowFilters] = useState(Boolean(searchParams.get("q")));
  const [showSort, setShowSort] = useState(false);
  const { data: rows = [], isLoading, error } = useQuery({
    queryKey: ["contacts", "list"],
    queryFn: () => apiListAll<ContactWithCompany>("/contacts"),
  });

  const { data: leads = [] } = useQuery({
    queryKey: ["leads", "contacts-page"],
    queryFn: () => apiListAll<LeadWithOpportunities>("/leads"),
  });

  const filteredAndSortedRows = useMemo(() => {
    return rows
      .filter((c) => {
        const stage = contactPipelineStage(c, leads);
        if (selectedStage !== "all" && stage !== selectedStage) {
          return false;
        }
        if (searchQuery.trim()) {
          const q = searchQuery.toLowerCase().trim();
          const nameMatch = (c.full_name ?? "").toLowerCase().includes(q);
          const companyMatch = (c.companies?.name ?? "").toLowerCase().includes(q);
          const roleMatch = (c.role ?? "").toLowerCase().includes(q);
          const emailMatch = (c.email ?? "").toLowerCase().includes(q);
          if (!nameMatch && !companyMatch && !roleMatch && !emailMatch) {
            return false;
          }
        }
        return true;
      })
      .sort((a, b) => {
        let valA = "";
        let valB = "";
        if (sortField === "name") {
          valA = a.full_name ?? "";
          valB = b.full_name ?? "";
        } else if (sortField === "company") {
          valA = a.companies?.name ?? "";
          valB = b.companies?.name ?? "";
        } else if (sortField === "role") {
          valA = a.role ?? "";
          valB = b.role ?? "";
        } else if (sortField === "stage") {
          valA = contactPipelineStage(a, leads);
          valB = contactPipelineStage(b, leads);
        } else if (sortField === "source") {
          valA = a.source ?? "";
          valB = b.source ?? "";
        }
        const cmp = valA.localeCompare(valB);
        return sortOrder === "asc" ? cmp : -cmp;
      });
  }, [rows, leads, selectedStage, searchQuery, sortField, sortOrder]);

  const pagination = usePagination(filteredAndSortedRows);

  const { mutate: updateContact } = useApiMutation({
    errorTitle: "Could not update contact",    mutationFn: async ({ id, data }: { id: string; data: Partial<ContactRow> }) => {
      return apiFetch(`/contacts/${id}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["contacts", "list"] });
    },
  });

  const { mutate: deleteContact } = useApiMutation({
    errorTitle: "Could not update contact",    mutationFn: async (id: string) => {
      return apiFetch(`/contacts/${id}`, { method: "DELETE" });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["contacts", "list"] });
    },
  });

  const handleBlur = (id: string, field: string, value: string, originalValue: string | null | undefined) => {
    if (value.trim() !== (originalValue || "").trim()) {
      updateContact({ id, data: { [field]: value.trim() } });
    }
  };

  /**
   * The lead a contact's activity should attach to: the one they are the primary contact on,
   * otherwise any lead at their company. Activities belong to leads, not contacts, so without
   * one there is nothing to log against.
   */
  const contactLeadId = (contact: ContactWithCompany): string | null => {
    const asPrimary = leads.find((l) => l.primary_contact_id === contact.id);
    if (asPrimary) return asPrimary.id;
    return leads.find((l) => l.company_id === contact.company_id)?.id ?? null;
  };

  const summary = useMemo(() => {
    // Where these contacts came from, from the contacts themselves. These four rows were
    // hardcoded constants -- the same numbers regardless of the data.
    const bySource = new Map<string, number>();
    for (const c of rows) {
      const key = c.source ? c.source.replace(/_/g, " ") : "unspecified";
      bySource.set(key, (bySource.get(key) ?? 0) + 1);
    }
    const total = rows.length || 1;
    const campaigns = [...bySource.entries()]
      .map(([name, value]) => ({ name, value, pct: Math.round((value / total) * 100) }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 4)
      .map((c, i) => ({ ...c, mostEffective: i === 0 }));

    return {
      total: rows.length,
      campaigns,
    };
  }, [rows]);

  const isFiltered = selectedStage !== "all" || searchQuery !== "";

  return (
    <div className="-mt-1 space-y-3">
      {/* Action Bar */}
      <div className="flex flex-col gap-2.5 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex flex-wrap items-center gap-2">

          
          <Button 
            variant={showFilters || isFiltered ? "default" : "outline"} 
            size="sm" 
            onClick={() => setShowFilters(!showFilters)}
            className={cn(
              "h-8 gap-1.5 rounded-md border-border/70 px-3 text-xs",
              (showFilters || isFiltered) ? "bg-[#0A1128] text-white hover:bg-[#1a2a53]" : ""
            )}
          >
            <Filter className="h-3.5 w-3.5" />
            Filter
            {isFiltered && !showFilters ? (
              <span className="ml-0.5 rounded-full bg-white/20 px-1.5 py-0.5 text-[10px] font-bold">
                Active
              </span>
            ) : null}
          </Button>

          <Button 
            variant={showSort ? "default" : "outline"} 
            size="sm" 
            onClick={() => setShowSort(!showSort)}
            className={cn(
              "h-8 gap-1.5 rounded-md border-border/70 px-3 text-xs",
              showSort ? "bg-[#0A1128] text-white hover:bg-[#1a2a53]" : ""
            )}
          >
            <SlidersHorizontal className="h-3.5 w-3.5" />
            Sort: {sortField.charAt(0).toUpperCase() + sortField.slice(1)}
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
          <ContactDrawer />
        </div>
      </div>

      {showFilters ? (
        <div className="flex flex-wrap items-center gap-4 rounded-xl border border-border/70 bg-card p-3 shadow-[0_1px_3px_rgba(15,23,42,0.06)]">
          <div className="relative flex-1 min-w-[200px] max-w-sm">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search contacts by name, company, email, role…"
              className="h-9 w-full rounded-md pl-9 pr-8 text-xs border-border/70"
            />
            {searchQuery ? (
              <button
                type="button"
                onClick={() => setSearchQuery("")}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            ) : null}
          </div>

          <div className="flex items-center gap-1.5 border-l border-border/70 pl-4">
            <span className="text-xs font-medium text-muted-foreground mr-1">Stage:</span>
            {(["all", "Won", "Leads", "Discovery", "Lost"] as const).map((st) => (
              <button
                key={st}
                onClick={() => setSelectedStage(st)}
                className={cn(
                  "inline-flex h-7 items-center justify-center rounded-full px-3 text-xs font-medium transition-colors",
                  selectedStage === st 
                    ? "bg-[#0A1128] text-white dark:bg-white dark:text-black" 
                    : "bg-muted text-muted-foreground hover:bg-muted/80 hover:text-foreground"
                )}
              >
                {st === "all" ? "All" : st}
              </button>
            ))}
          </div>

          {isFiltered ? (
            <div className="flex items-center ml-auto">
              <Button 
                variant="ghost" 
                size="sm" 
                className="h-8 px-2 text-xs text-rose-600 hover:text-rose-700 hover:bg-rose-50"
                onClick={() => {
                  setSelectedStage("all");
                  setSearchQuery("");
                }}
              >
                Reset Filters
              </Button>
            </div>
          ) : null}
        </div>
      ) : null}

      {showSort ? (
        <div className="flex flex-wrap items-center gap-4 rounded-xl border border-border/70 bg-card p-3 shadow-[0_1px_3px_rgba(15,23,42,0.06)]">
          <div className="flex items-center gap-1.5 pl-2">
            <span className="text-xs font-medium text-muted-foreground mr-2">Sort by:</span>
            {[
              { id: "name", label: "Name" },
              { id: "company", label: "Company" },
              { id: "role", label: "Role" },
              { id: "stage", label: "Stage" },
              { id: "source", label: "Source" },
            ].map((f) => (
              <button
                key={f.id}
                onClick={() => {
                  if (sortField === f.id) {
                    setSortOrder(sortOrder === "asc" ? "desc" : "asc");
                  } else {
                    setSortField(f.id as any);
                    setSortOrder("asc");
                  }
                }}
                className={cn(
                  "inline-flex h-7 items-center justify-center rounded-full px-3 text-xs font-medium transition-colors",
                  sortField === f.id 
                    ? "bg-[#0A1128] text-white dark:bg-white dark:text-black" 
                    : "bg-muted text-muted-foreground hover:bg-muted/80 hover:text-foreground"
                )}
              >
                {f.label}
                {sortField === f.id && (
                  <ChevronDown className={cn("ml-1.5 h-3 w-3 transition-transform", sortOrder === "desc" ? "" : "rotate-180")} />
                )}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {/* The headline here read "Cust. Acquisition Cost -- $462.72 average, -4%". All three
          numbers were literals. Nothing in the product measures acquisition cost: the
          marketing_channel_metrics table that would hold spend has no API and no writer, so
          the figure could not be made real. The tiles beneath it were already a genuine
          source breakdown, so the headline now describes those. History / Assign Task /
          Adjust Spend sat alongside and were three more buttons with no handler; none of them
          has a meaning at page level with no contact selected, so they are gone rather than
          reimplemented as something they never were. */}
      <StatsStrip
        headlineLabel="Contacts"
        headline={String(summary.total)}
        tiles={summary.campaigns.map((campaign) => ({
          label: campaign.name,
          value: String(campaign.value),
          hint: (
            <>
              <span className="font-semibold text-foreground">{campaign.pct}%</span> of contacts
            </>
          ),
          emphasis: campaign.mostEffective,
        }))}
      />

      {/* Editable Table */}
      <Card className="rounded-xl border border-border/70 shadow-[0_1px_3px_rgba(15,23,42,0.06)] overflow-hidden">
        <CardContent className="overflow-x-auto px-3 py-2">
          {error ? (
            <div className="p-4"><p className="text-sm text-destructive">{(error as Error).message}</p></div>
          ) : isLoading ? (
            <table className="w-full min-w-[1020px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-border/70 text-left text-[11px] font-semibold text-muted-foreground select-none">
                  <th className="w-8 py-2.5">
                    <input type="checkbox" className="h-3.5 w-3.5 rounded border-border" disabled />
                  </th>
                  <th className="py-2.5 pr-4">Name</th>
                  <th className="py-2.5 pr-4">Company</th>
                  <th className="py-2.5 pr-4">Role</th>
                  <th className="py-2.5 pr-4">Stage</th>
                  <th className="py-2.5 pr-4">Source</th>
                  <th className="py-2.5 pr-4">Email</th>
                  <th className="py-2.5 pr-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i} className="border-b border-border/50">
                    <td className="w-8 py-2.5"><Skeleton className="h-3.5 w-3.5 rounded" /></td>
                    <td className="py-2.5 pr-4">
                      <div className="flex items-center gap-2.5">
                        <Skeleton className="h-8 w-8 rounded-full shrink-0" />
                        <Skeleton className="h-4 w-32" />
                      </div>
                    </td>
                    <td className="py-2.5 pr-4"><Skeleton className="h-4 w-28" /></td>
                    <td className="py-2.5 pr-4"><Skeleton className="h-4 w-24" /></td>
                    <td className="py-2.5 pr-4"><Skeleton className="h-5 w-20 rounded-full" /></td>
                    <td className="py-2.5 pr-4"><Skeleton className="h-4 w-20" /></td>
                    <td className="py-2.5 pr-4"><Skeleton className="h-4 w-36" /></td>
                    <td className="py-2.5 pr-4 text-right"><Skeleton className="h-7 w-7 rounded-md ml-auto" /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : rows.length === 0 ? (
            <div className="p-4"><p className="text-sm text-muted-foreground">No contacts yet.</p></div>
          ) : filteredAndSortedRows.length === 0 ? (
            <p className="text-sm text-muted-foreground">No contacts found.</p>
          ) : viewMode === "gallery" ? (
            <ContactsGallery contacts={filteredAndSortedRows} leads={leads} />
          ) : (
            <table className="w-full min-w-[920px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-border/70 text-left text-[11px] font-semibold text-muted-foreground select-none">
                  <th className="w-8 py-2.5">
                    <input type="checkbox" className="h-3.5 w-3.5 rounded border-border" />
                  </th>
                  <th 
                    className="py-2.5 pr-4 cursor-pointer hover:text-foreground"
                    onClick={() => {
                      if (sortField === "name") setSortOrder(sortOrder === "asc" ? "desc" : "asc");
                      else { setSortField("name"); setSortOrder("asc"); }
                    }}
                  >
                    <div className="inline-flex items-center gap-1.5">
                      Name
                      <ChevronsUpDown className="h-3 w-3" />
                    </div>
                  </th>
                  <th 
                    className="py-2.5 pr-4 cursor-pointer hover:text-foreground"
                    onClick={() => {
                      if (sortField === "company") setSortOrder(sortOrder === "asc" ? "desc" : "asc");
                      else { setSortField("company"); setSortOrder("asc"); }
                    }}
                  >
                    <div className="inline-flex items-center gap-1.5">
                      Company
                      <ChevronsUpDown className="h-3 w-3" />
                    </div>
                  </th>
                  <th 
                    className="py-2.5 pr-4 cursor-pointer hover:text-foreground"
                    onClick={() => {
                      if (sortField === "role") setSortOrder(sortOrder === "asc" ? "desc" : "asc");
                      else { setSortField("role"); setSortOrder("asc"); }
                    }}
                  >
                    <div className="inline-flex items-center gap-1.5">
                      Role
                      <ChevronsUpDown className="h-3 w-3" />
                    </div>
                  </th>
                  <th 
                    className="py-2.5 pr-4 cursor-pointer hover:text-foreground"
                    onClick={() => {
                      if (sortField === "stage") setSortOrder(sortOrder === "asc" ? "desc" : "asc");
                      else { setSortField("stage"); setSortOrder("asc"); }
                    }}
                  >
                    <div className="inline-flex items-center gap-1.5">
                      Stage
                      <ChevronsUpDown className="h-3 w-3" />
                    </div>
                  </th>
                  <th 
                    className="py-2.5 pr-4 cursor-pointer hover:text-foreground"
                    onClick={() => {
                      if (sortField === "source") setSortOrder(sortOrder === "asc" ? "desc" : "asc");
                      else { setSortField("source"); setSortOrder("asc"); }
                    }}
                  >
                    <div className="inline-flex items-center gap-1.5">
                      Source
                      <ChevronsUpDown className="h-3 w-3" />
                    </div>
                  </th>
                  <th className="py-2.5 pr-4">
                    <div className="inline-flex items-center gap-1.5">
                      Email
                    </div>
                  </th>
                  <th className="py-2.5 pr-4 text-right">
                    <div className="inline-flex items-center gap-1.5">
                      Actions
                    </div>
                  </th>
                </tr>
              </thead>
              <tbody>
                {pagination.pageRows.map((c, index) => {
                  const stage = contactPipelineStage(c, leads);
                  return (
                  <tr 
                    key={c.id} 
                    className="border-b border-border/50 group hover:bg-muted/30 transition-colors animate-in fade-in slide-in-from-bottom-2 duration-500 fill-mode-both"
                    style={{ animationDelay: `${index * 50}ms` }}
                  >
                    <td className="w-8 py-2.5">
                      <input type="checkbox" className="h-3.5 w-3.5 rounded border-border" />
                    </td>
                    <td className="py-2.5 pr-4">
                      <div className="flex items-center gap-2.5">
                        <Link href={`/contacts/${c.id}`} className="shrink-0">
                          <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-slate-200 text-[11px] font-semibold text-slate-700 dark:bg-slate-700 dark:text-slate-100 transition-colors hover:bg-slate-300 dark:hover:bg-slate-600">
                            {initials(c.full_name ?? "Unknown")}
                          </span>
                        </Link>
                        <div className="leading-tight flex-1">
                          <Link href={`/contacts/${c.id}`} className="text-[13px] font-semibold text-foreground hover:underline hover:underline-offset-2">
                            {c.full_name || "Unknown"}
                          </Link>
                        </div>
                      </div>
                    </td>
                    <td className="py-2.5 pr-4">
                      <input 
                        defaultValue={c.companies?.name ?? ""}
                        readOnly
                        placeholder="Company"
                        className="w-full bg-transparent outline-none text-[13px] text-foreground font-medium placeholder:text-muted-foreground/50 cursor-pointer hover:underline hover:underline-offset-2 focus:border-b focus:border-primary/50"
                      />
                    </td>
                    <td className="py-2.5 pr-4">
                      <input 
                        defaultValue={c.role ?? ""}
                        onBlur={(e) => handleBlur(c.id, "role", e.target.value, c.role)}
                        placeholder="Role"
                        className="w-full bg-transparent outline-none text-[13px] text-muted-foreground placeholder:text-muted-foreground/50 focus:border-b focus:border-primary/50"
                      />
                    </td>
                    <td className="py-2.5 pr-4">
                      <Badge className={`font-medium ${STAGE_VARIANTS[stage]}`}>{stage}</Badge>
                    </td>
                    <td className="py-2.5 pr-4">
                      <span className="text-[13px] text-muted-foreground capitalize">
                        {c.source ? c.source.replace("_", " ") : "—"}
                      </span>
                    </td>
                    <td className="py-2.5 pr-4">
                      <input 
                        defaultValue={c.email ?? ""}
                        onBlur={(e) => handleBlur(c.id, "email", e.target.value, c.email)}
                        placeholder="Email"
                        className="w-full bg-transparent outline-none text-[13px] text-muted-foreground placeholder:text-muted-foreground/50 focus:border-b focus:border-primary/50"
                      />
                    </td>
                    <td className="py-2.5 pr-4 text-right">
                      <div className="flex items-center justify-end opacity-0 group-hover:opacity-100 transition-opacity">
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <button className="h-7 w-7 inline-flex items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground">
                              <MoreHorizontal className="h-3.5 w-3.5" />
                            </button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end" className="w-40">
                            {/* Both of these were menu items with no handler. */}
                            <DropdownMenuItem
                              className="gap-2"
                              disabled={!c.email}
                              onClick={() => {
                                if (c.email) window.location.href = `mailto:${c.email}`;
                              }}
                            >
                              <Mail className="h-3.5 w-3.5" />
                              Send email
                            </DropdownMenuItem>
                            {contactLeadId(c) ? (
                              <LogActivityDrawer
                                leadId={contactLeadId(c)!}
                                type="call"
                                title="Log a call"
                                trigger={
                                  <DropdownMenuItem
                                    className="gap-2"
                                    onSelect={(e) => e.preventDefault()}
                                  >
                                    <Phone className="h-3.5 w-3.5" />
                                    Log call
                                  </DropdownMenuItem>
                                }
                              />
                            ) : (
                              <DropdownMenuItem
                                className="gap-2"
                                disabled
                                title="A call is logged against a lead; this contact has none."
                              >
                                <Phone className="h-3.5 w-3.5" />
                                Log call
                              </DropdownMenuItem>
                            )}
                            <DropdownMenuSeparator />
                            <DropdownMenuItem 
                              className="gap-2 text-rose-600 focus:text-rose-600 focus:bg-rose-50"
                              onClick={() => {
                                if (confirm("Are you sure you want to delete this contact?")) {
                                  deleteContact(c.id);
                                }
                              }}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                              Delete
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    </td>
                  </tr>
                  );
                })}
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
