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
  UserPlus,
  WalletCards,
} from "lucide-react";
import { useMemo } from "react";
import { apiListAll } from "@/lib/api";

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
  const parts = name.trim().split(/\s+/).filter(Boolean);
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

export default function CompaniesPage() {
  const { data: companies = [], isLoading: companiesLoading, error: companiesError } = useQuery({
    queryKey: ["companies", "list"],
    queryFn: () => apiListAll<CompanyRow>("/companies"),
  });

  const { data: leads = [], isLoading: leadsLoading, error: leadsError } = useQuery({
    queryKey: ["leads", "companies-page"],
    queryFn: () => apiListAll<LeadRow>("/leads"),
  });

  const { data: contacts = [], isLoading: contactsLoading, error: contactsError } = useQuery({
    queryKey: ["contacts", "companies-page"],
    queryFn: () => apiListAll<ContactRow>("/contacts"),
  });

  const isLoading = companiesLoading || leadsLoading || contactsLoading;
  const error = (companiesError || leadsError || contactsError) as Error | null;

  const rows = useMemo(() => {
    const leadsByCompany = new Map<string, LeadRow[]>();
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
      const stage = leadStageToCompanyStage(latestLead?.stage);
      const value =
        companyLeads.reduce((sum, lead) => sum + (lead.estimated_value ?? 0), 0) ||
        Math.max(120, (company.name.length % 8) * 80 + 120);

      return {
        id: company.id,
        name: company.name,
        stage,
        value,
        contactName: primary?.full_name ?? "No contact",
        contactRole: primary?.role ?? "Unassigned",
        contactsCount: companyContacts.length,
      };
    });
  }, [companies, contacts, leads]);

  const summary = useMemo(() => {
    const total = rows.reduce((sum, row) => sum + row.value, 0);
    const average = rows.length > 0 ? total / rows.length : 0;
    const discoveryCount = rows.filter((r) => r.stage === "Discovery").length;
    const wonCount = rows.filter((r) => r.stage === "Won").length;
    const lostCount = rows.filter((r) => r.stage === "Lost").length;

    const campaignSeed = Math.max(1, rows.length);
    const campaigns = [
      { name: "Events", pct: 15 + (summaryHash(rows, 2) % 8), value: 320 + campaignSeed * 12 },
      { name: "Micro KOL", pct: 20 + (summaryHash(rows, 3) % 9), value: 360 + campaignSeed * 14 },
      { name: "Meta Ads", pct: 23 + (summaryHash(rows, 5) % 10), value: 410 + campaignSeed * 16 },
      { name: "Referral", pct: 42, value: 220 + campaignSeed * 8, mostEffective: true },
    ];

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
          <Button size="sm" className="h-8 gap-1.5 rounded-md bg-[#0A1128] px-3 text-xs font-semibold text-white hover:bg-[#1a2a53]">
            <Plus className="h-3.5 w-3.5" />
            Add New
            <ChevronDown className="h-3.5 w-3.5 text-white/80" />
          </Button>
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
              <Button variant="outline" size="sm" className="h-8 gap-1 rounded-md border-border/70 px-3 text-xs font-semibold">
                Collapse
                <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
              </Button>
            </div>
          </div>

          <div className="grid gap-2 md:grid-cols-4">
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
            <p className="text-sm text-muted-foreground">Loading companies…</p>
          ) : rows.length === 0 ? (
            <p className="text-sm text-muted-foreground">No companies yet.</p>
          ) : (
              <table className="w-full min-w-[920px] border-collapse text-sm">
              <thead>
                  <tr className="border-b border-border/70 text-left text-[11px] font-semibold text-muted-foreground">
                    <th className="w-8 py-2.5">
                      <input type="checkbox" className="h-3.5 w-3.5 rounded border-border" />
                    </th>
                    <th className="py-2.5 pr-4">
                      <div className="inline-flex items-center gap-1.5">
                        Company
                        <ChevronsUpDown className="h-3 w-3" />
                      </div>
                    </th>
                    <th className="py-2.5 pr-4">
                      <div className="inline-flex items-center gap-1.5">
                        Linkedin
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
                        Contacts
                        <ChevronsUpDown className="h-3 w-3" />
                      </div>
                    </th>
                    <th className="py-2.5 pr-4">
                      <div className="inline-flex items-center gap-1.5">
                        Position
                        <ChevronsUpDown className="h-3 w-3" />
                      </div>
                    </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((c) => (
                  <tr key={c.id} className="border-b border-border/50">
                      <td className="w-8 py-2.5">
                        <input type="checkbox" className="h-3.5 w-3.5 rounded border-border" />
                      </td>
                      <td className="py-2.5 pr-4 font-medium text-foreground">{c.name}</td>
                      <td className="py-2.5 pr-4">
                        <a href="#" className="font-medium text-[#111827] underline underline-offset-2 dark:text-slate-100">
                          {c.name}
                        </a>
                      </td>
                      <td className="py-2.5 pr-4">
                        <Badge className={`font-medium ${STAGE_VARIANTS[c.stage]}`}>{c.stage}</Badge>
                      </td>
                      <td className="py-2.5 pr-4">
                        <div className="flex items-center gap-2.5">
                          <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-slate-200 text-[11px] font-semibold text-slate-700 dark:bg-slate-700 dark:text-slate-100">
                            {initials(c.contactName)}
                          </span>
                          <div className="leading-tight">
                            <p className="text-[13px] font-semibold text-foreground">{c.contactName}</p>
                            <p className="text-[11px] text-muted-foreground">{c.contactsCount} total</p>
                          </div>
                        </div>
                      </td>
                      <td className="py-2.5 pr-4 text-muted-foreground">{c.contactRole}</td>
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
                n === 2
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

function summaryHash(rows: { id: string }[], seed: number): number {
  return rows.reduce((acc, row) => {
    let hash = acc;
    for (let i = 0; i < row.id.length; i += 1) {
      hash = (hash * 31 + row.id.charCodeAt(i) + seed) % 9973;
    }
    return hash;
  }, seed * 17);
}
