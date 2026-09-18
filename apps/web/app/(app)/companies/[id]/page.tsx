"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Badge, Button, Skeleton, cardShell, cn } from "@dracara/ui";
import { ArrowRight, Building2, Globe, Linkedin, MapPin, Users } from "lucide-react";
import { useMemo } from "react";
import type { CompanyRow, ContactRow, LeadWithOpportunities } from "@dracara/types";
import { apiFetch, apiListAll } from "@/lib/api";
import { Avatar } from "@/components/shared/avatar";
import { CompanyDrawer } from "@/components/companies/company-drawer";
import { CompanyResearchPanel } from "@/components/companies/company-research-panel";
import { DataTable, type Column } from "@/components/shared/data-table";
import { KpiCard } from "@/components/shared/kpi-card";
import { PageSection } from "@/components/shared/page-section";
import { formatDate } from "@/lib/format";
import { humanizeEnum } from "@/lib/forms";
import { leadCurrency, leadStage, leadValue } from "@/lib/leads";

/** Absolute URL for a field users may have typed without a scheme. */
function externalHref(url: string): string {
  return url.startsWith("http://") || url.startsWith("https://") ? url : `https://${url}`;
}

function formatMoney(amount: number | null | undefined, currency: string | undefined): string {
  if (amount == null) return "—";
  try {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: currency || "USD",
      maximumFractionDigits: 0,
    }).format(Number(amount));
  } catch {
    return `${currency ?? ""} ${amount}`;
  }
}

/**
 * A company, its people and its deals.
 *
 * This route did not exist. The companies gallery linked every card at `/companies/{id}` and
 * every one of those cards 404ed, and the list view had no way into a company at all -- so the
 * only thing you could do with a company was edit its fields in a drawer.
 */
export default function CompanyDetailPage() {
  const { id } = useParams() as { id: string };

  const { data: company, isLoading, error } = useQuery({
    queryKey: ["companies", id],
    queryFn: () => apiFetch<CompanyRow>(`/companies/${id}`),
    retry: false,
  });

  const { data: contacts = [], isLoading: contactsLoading } = useQuery({
    queryKey: ["contacts", "by-company", id],
    queryFn: () => apiListAll<ContactRow>(`/contacts?company_id=${id}`),
  });

  const { data: allLeads = [], isLoading: leadsLoading } = useQuery({
    queryKey: ["leads", "by-company"],
    queryFn: () => apiListAll<LeadWithOpportunities>("/leads"),
  });

  const leads = useMemo(() => allLeads.filter((lead) => lead.company_id === id), [allLeads, id]);

  // A lead with no pursuit yet has no stage at all, so it counts as open rather than being
  // coerced into one of the closed stages.
  const CLOSED_STAGES = ["won", "lost", "delivery_transition"];
  const openValue = useMemo(
    () =>
      leads
        .filter((lead) => {
          const stage = leadStage(lead);
          return stage === null || !CLOSED_STAGES.includes(stage);
        })
        .reduce((sum, lead) => sum + leadValue(lead), 0),
    [leads]
  );

  const currency = leads.length > 0 ? leadCurrency(leads[0]) : undefined;
  const wonCount = leads.filter((lead) => leadStage(lead) === "won").length;

  const contactColumns: Column<ContactRow>[] = [
    {
      key: "name",
      header: "Name",
      skeletonWidth: "w-40",
      cell: (contact) => (
        <div className="flex items-center gap-2.5">
          <Avatar name={contact.full_name} />
          <Link
            href={`/contacts/${contact.id}`}
            className="text-[13px] font-semibold text-foreground hover:underline hover:underline-offset-2"
          >
            {contact.full_name || "Unknown"}
          </Link>
          {contact.is_primary ? (
            <Badge variant="secondary" className="text-[10px]">
              Primary
            </Badge>
          ) : null}
        </div>
      ),
    },
    { key: "role", header: "Role", cell: (contact) => contact.role || "—" },
    {
      key: "email",
      header: "Email",
      skeletonWidth: "w-48",
      cell: (contact) =>
        contact.email ? (
          <a href={`mailto:${contact.email}`} className="text-muted-foreground hover:underline">
            {contact.email}
          </a>
        ) : (
          "—"
        ),
    },
    {
      key: "phone",
      header: "Phone",
      cell: (contact) =>
        contact.phone ? (
          <a
            href={`tel:${contact.phone.replace(/\s/g, "")}`}
            className="tabular-nums text-muted-foreground hover:underline"
          >
            {contact.phone}
          </a>
        ) : (
          "—"
        ),
    },
  ];

  const leadColumns: Column<LeadWithOpportunities>[] = [
    {
      key: "stage",
      header: "Stage",
      skeletonWidth: "w-28",
      cell: (lead) => {
        const stage = leadStage(lead);
        return stage ? (
          <Badge variant="outline" className="text-[10px]">
            {humanizeEnum(stage)}
          </Badge>
        ) : (
          <span className="text-muted-foreground">No pursuit yet</span>
        );
      },
    },
    { key: "type", header: "Project", cell: (lead) => humanizeEnum(lead.project_type) },
    {
      key: "source",
      header: "Source",
      cell: (lead) => (
        <span className="text-muted-foreground">{humanizeEnum(lead.lead_source)}</span>
      ),
    },
    {
      key: "value",
      header: "Value",
      skeletonWidth: "w-20",
      cell: (lead) => (
        <span className="tabular-nums">{formatMoney(leadValue(lead), leadCurrency(lead))}</span>
      ),
    },
    {
      key: "followup",
      header: "Next follow-up",
      skeletonWidth: "w-24",
      cell: (lead) => (
        <span className="text-muted-foreground">{formatDate(lead.next_followup_date)}</span>
      ),
    },
    {
      key: "actions",
      header: <span className="sr-only">Open</span>,
      className: "text-right",
      skeletonWidth: "w-12",
      cell: (lead) => (
        <Button variant="ghost" size="sm" className="h-8 gap-1 text-xs" asChild>
          <Link href={`/leads/${lead.id}`}>
            Open
            <ArrowRight className="h-3 w-3" />
          </Link>
        </Button>
      ),
    },
  ];

  if (error) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-destructive">{(error as Error).message}</p>
        <Button variant="outline" size="sm" asChild>
          <Link href="/companies">Back to companies</Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className={cn(cardShell, "p-5")}>
        {isLoading || !company ? (
          <div className="space-y-3">
            <Skeleton className="h-7 w-56" />
            <Skeleton className="h-4 w-72" />
          </div>
        ) : (
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <Avatar name={company.name} square className="h-12 w-12 text-sm" />
              <div>
                <h2 className="text-xl font-semibold tracking-tight text-[#0A1128] dark:text-foreground">
                  {company.name}
                </h2>
                <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                  {company.industry ? (
                    <span className="inline-flex items-center gap-1">
                      <Building2 className="h-3.5 w-3.5" />
                      {company.industry}
                    </span>
                  ) : null}
                  {company.location ? (
                    <span className="inline-flex items-center gap-1">
                      <MapPin className="h-3.5 w-3.5" />
                      {company.location}
                    </span>
                  ) : null}
                  {company.size ? (
                    <span className="inline-flex items-center gap-1">
                      <Users className="h-3.5 w-3.5" />
                      {company.size}
                    </span>
                  ) : null}
                  {company.segment ? (
                    <Badge variant="secondary" className="text-[10px]">
                      {humanizeEnum(company.segment)}
                    </Badge>
                  ) : null}
                </div>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {company.website ? (
                <a
                  href={externalHref(company.website)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border/70 bg-background px-3 text-xs font-medium hover:bg-muted/50"
                >
                  <Globe className="h-3.5 w-3.5 text-muted-foreground" />
                  Website
                </a>
              ) : null}
              {company.linkedin_url ? (
                <a
                  href={externalHref(company.linkedin_url)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border/70 bg-background px-3 text-xs font-medium hover:bg-muted/50"
                >
                  <Linkedin className="h-3.5 w-3.5 text-muted-foreground" />
                  LinkedIn
                </a>
              ) : null}
              <CompanyDrawer company={company} />
            </div>
          </div>
        )}
      </div>

      {/* Renders nothing unless web research is configured (EXA_API_KEY). */}
      <CompanyResearchPanel companyId={id} />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard label="Contacts" value={contactsLoading ? "—" : String(contacts.length)} />
        <KpiCard label="Leads" value={leadsLoading ? "—" : String(leads.length)} />
        <KpiCard
          label="Open value"
          value={leadsLoading ? "—" : formatMoney(openValue, currency)}
          hint="Excludes won and lost"
        />
        <KpiCard label="Won" value={leadsLoading ? "—" : String(wonCount)} />
      </div>

      <PageSection
        title="People"
        description="Everyone on record at this company."
        action={
          <Button variant="outline" size="sm" className="h-8 text-xs" asChild>
            <Link href="/contacts">All contacts</Link>
          </Button>
        }
      >
        <DataTable
          rows={contacts}
          columns={contactColumns}
          isLoading={contactsLoading}
          emptyMessage="No contacts recorded at this company yet."
          minWidth="min-w-[720px]"
          skeletonRows={3}
        />
      </PageSection>

      <PageSection title="Deals" description="Every lead opened against this company.">
        <DataTable
          rows={leads}
          columns={leadColumns}
          isLoading={leadsLoading}
          emptyMessage="No leads against this company yet."
          minWidth="min-w-[820px]"
          skeletonRows={3}
        />
      </PageSection>
    </div>
  );
}
