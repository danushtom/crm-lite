"use client";

import type { ContactRow, LeadRow } from "@dracara/types";
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
  Input
} from "@dracara/ui";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
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
  UserPlus,
  WalletCards,
  MoreHorizontal,
  Trash2,
  Mail,
  Phone,
  Search,
  X,
  Check,
} from "lucide-react";
import { useMemo, useState, useEffect } from "react";
import { apiFetch } from "@/lib/api";
import Link from "next/link";
import { AddContactDrawer } from "@/components/contacts/add-contact-drawer";
import { cn } from "@dracara/ui";

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

function toK(n: number): string {
  if (n >= 1000) return `$${Math.round(n / 10) / 100}K`;
  return `$${Math.round(n)}`;
}

type ContactWithCompany = ContactRow & { companies?: { name?: string | null } | null };

function contactPipelineStage(contact: ContactRow, leads: LeadRow[]): CompanyStage {
  for (const lead of leads) {
    if (lead.primary_contact_id === contact.id) {
      return leadStageToCompanyStage(lead.stage);
    }
  }
  const leadsByCompany = new Map<string, LeadRow[]>();
  for (const lead of leads) {
    const arr = leadsByCompany.get(lead.company_id) ?? [];
    arr.push(lead);
    leadsByCompany.set(lead.company_id, arr);
  }
  const companyLeads = leadsByCompany.get(contact.company_id) ?? [];
  return leadStageToCompanyStage(companyLeads[0]?.stage);
}

export default function ContactsPage() {
  const queryClient = useQueryClient();

  const [searchQuery, setSearchQuery] = useState("");
  const [selectedStage, setSelectedStage] = useState<string>("all");
  const [sortField, setSortField] = useState<"name" | "company" | "role" | "stage" | "source">("name");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");
  const [showFilters, setShowFilters] = useState(false);
  const [showSort, setShowSort] = useState(false);
  const [isStatsCollapsed, setIsStatsCollapsed] = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem("crm-stats-collapsed");
    if (saved) {
      setIsStatsCollapsed(saved === "true");
    }
  }, []);

  const toggleStats = () => {
    const next = !isStatsCollapsed;
    setIsStatsCollapsed(next);
    localStorage.setItem("crm-stats-collapsed", next.toString());
  };

  const { data: rows = [], isLoading, error } = useQuery({
    queryKey: ["contacts", "list"],
    queryFn: () => apiFetch<ContactWithCompany[]>("/contacts"),
  });

  const { data: leads = [] } = useQuery({
    queryKey: ["leads", "contacts-page"],
    queryFn: () => apiFetch<LeadRow[]>("/leads?limit=200"),
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

  const { mutate: updateContact } = useMutation({
    mutationFn: async ({ id, data }: { id: string; data: Partial<ContactRow> }) => {
      return apiFetch(`/contacts/${id}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["contacts", "list"] });
    },
  });

  const { mutate: deleteContact } = useMutation({
    mutationFn: async (id: string) => {
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

  const summary = useMemo(() => {
    const campaigns = [
      { name: "Events", pct: 15, value: 640 },
      { name: "Micro KOL", pct: 20, value: 480 },
      { name: "Meta Ads", pct: 23, value: 456 },
      { name: "Referral", pct: 42, value: 235, mostEffective: true },
    ];

    return {
      average: 462.72,
      campaigns,
    };
  }, []);

  const isFiltered = selectedStage !== "all" || searchQuery !== "";

  return (
    <div className="-mt-1 space-y-3">
      {/* Action Bar */}
      <div className="flex flex-col gap-2.5 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <Button className="h-8 gap-1.5 rounded-md bg-[#0B7FB3] px-3 text-xs font-semibold text-white hover:bg-[#0a6d99]">
            <Sparkles className="h-3.5 w-3.5" />
            Ask AI
          </Button>
          
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
          <AddContactDrawer />
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

      {/* Stats Card */}
      <Card className="rounded-xl border border-border/70 bg-card shadow-[0_1px_3px_rgba(15,23,42,0.06)] overflow-hidden">
        <CardContent className={cn("pt-4 transition-all duration-300", isStatsCollapsed ? "pb-4" : "pb-6")}>
          <div className={cn("flex flex-col gap-3 transition-all duration-300", isStatsCollapsed ? "md:flex-row md:items-center md:justify-between" : "md:flex-row md:items-start md:justify-between")}>
            <div className={cn("flex transition-all duration-300", isStatsCollapsed ? "items-center gap-3" : "flex-col")}>
              <div className="flex items-center gap-2">
                <p className="text-sm font-semibold text-foreground">Cust. Acquisition Cost</p>
                <Badge className="h-5 rounded-md bg-rose-100 px-1.5 text-[10px] font-semibold text-rose-700 dark:bg-rose-900/30 dark:text-rose-300">
                  - 4%
                </Badge>
              </div>
              <p className={cn(
                "font-semibold tracking-tight text-[#0A1128] dark:text-foreground transition-all duration-300", 
                isStatsCollapsed ? "text-xl mt-0" : "text-[38px] leading-none mt-2"
              )}>
                <span className={cn("text-muted-foreground transition-all duration-300", isStatsCollapsed ? "text-lg" : "text-[28px]")}>$</span>462<span className={cn("text-muted-foreground transition-all duration-300", isStatsCollapsed ? "text-lg" : "text-[28px]")}>.72</span>
                <span className={cn("ml-2 font-medium text-muted-foreground transition-all duration-300", isStatsCollapsed ? "text-[11px]" : "text-xs")}>average</span>
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="outline" size="sm" className="h-8 gap-1.5 rounded-md border-border/70 px-3 text-xs">
                <Clock3 className="h-3.5 w-3.5 text-muted-foreground" />
                History
              </Button>
              <Button variant="outline" size="sm" className="h-8 gap-1.5 rounded-md border-border/70 px-3 text-xs">
                <UserPlus className="h-3.5 w-3.5 text-muted-foreground" />
                Assign Task
              </Button>
              <Button variant="outline" size="sm" className="h-8 gap-1.5 rounded-md border-border/70 px-3 text-xs">
                <WalletCards className="h-3.5 w-3.5 text-muted-foreground" />
                Adjust Spend
              </Button>
              <Button 
                variant="outline" 
                size="sm" 
                className="h-8 gap-1 rounded-md border-border/70 px-3 text-xs font-semibold"
                onClick={toggleStats}
              >
                {isStatsCollapsed ? "Expand" : "Collapse"}
                <ChevronDown className={cn("h-3.5 w-3.5 text-muted-foreground transition-transform", isStatsCollapsed ? "" : "rotate-180")} />
              </Button>
            </div>
          </div>

          <div className={cn(
            "grid md:grid-cols-4 overflow-hidden transition-all duration-300 ease-in-out",
            isStatsCollapsed ? "max-h-0 opacity-0 gap-0 mt-0" : "max-h-[500px] opacity-100 gap-2 mt-4"
          )}>
            {summary.campaigns.map((campaign, i) => {
              const colors = ["bg-[#18395B]", "bg-[#2FA8E8]", "bg-[#45B2F0]", "bg-[#E2E8F0]"];
              const barColor = colors[i] || colors[0];
              return (
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
                  <div className={`mt-2 h-1 w-full rounded ${barColor}`} />
                  <p className="mt-2 text-sm font-medium text-foreground flex items-center gap-1.5">
                    <span className={`inline-block h-2 w-2 rounded-sm ${barColor}`} />
                    {campaign.name}
                  </p>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Editable Table */}
      <Card className="rounded-xl border border-border/70 shadow-[0_1px_3px_rgba(15,23,42,0.06)] overflow-hidden">
        <CardContent className="overflow-x-auto px-3 py-2">
          {error ? (
            <div className="p-4"><p className="text-sm text-destructive">{(error as Error).message}</p></div>
          ) : isLoading ? (
            <div className="p-4"><p className="text-sm text-muted-foreground">Loading contacts…</p></div>
          ) : rows.length === 0 ? (
            <div className="p-4"><p className="text-sm text-muted-foreground">No contacts yet.</p></div>
          ) : filteredAndSortedRows.length === 0 ? (
            <div className="p-8 text-center space-y-3">
              <p className="text-sm font-medium text-muted-foreground">No contacts match the selected search or filter criteria.</p>
              <Button size="sm" variant="outline" onClick={() => { setSelectedStage("all"); setSearchQuery(""); }}>
                Reset Filters
              </Button>
            </div>
          ) : (
            <table className="w-full min-w-[1020px] border-collapse text-sm">
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
                {filteredAndSortedRows.map((c) => {
                  const stage = contactPipelineStage(c, leads);
                  return (
                  <tr key={c.id} className="border-b border-border/50 group hover:bg-muted/30 transition-colors">
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
                            <DropdownMenuItem className="gap-2">
                              <Mail className="h-3.5 w-3.5" />
                              Send Email
                            </DropdownMenuItem>
                            <DropdownMenuItem className="gap-2">
                              <Phone className="h-3.5 w-3.5" />
                              Log Call
                            </DropdownMenuItem>
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

      {/* Pagination */}
      <div className="flex items-center justify-between px-1 pb-1 pt-2">
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
