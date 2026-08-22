"use client";

import { useQuery } from "@tanstack/react-query";
import { 
  format, 
  parseISO, 
  startOfMonth, 
  endOfMonth, 
  startOfWeek, 
  endOfWeek, 
  eachDayOfInterval, 
  isSameMonth, 
  isSameDay, 
  addMonths, 
  subMonths 
} from "date-fns";
import Link from "next/link";
import { useParams } from "next/navigation";
import { scoreTier, type CompanyRow, type ContactRow, type LeadRow, type TaskRow, type MeetingRow } from "@dracara/types";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, cn } from "@dracara/ui";
import {
  ArrowRight,
  Bell,
  Briefcase,
  Building2,
  CalendarClock,
  ChevronRight,
  DollarSign,
  Globe,
  Info,
  Layers,
  Linkedin,
  Mail,
  MessageSquare,
  Phone,
  PhoneCall,
  Plus,
  Sparkles,
  Star,
  User,
  ChevronLeft,
} from "lucide-react";
import { useMemo, useState } from "react";
import { apiFetch, apiList, apiListAll } from "@/lib/api";

type ContactDetailTab = "overview" | "notes" | "conversations" | "timeline" | "reminders";

const segmentClass =
  "rounded-md px-3 py-2 text-sm font-medium transition-all outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2";

function humanizeUnderscore(s: string): string {
  return s
    .split("_")
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
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

function safeFormatDate(iso: string | null | undefined, fmt: string): string {
  if (!iso) return "—";
  try {
    return format(parseISO(iso), fmt);
  } catch {
    return iso;
  }
}

const cardShell = "rounded-xl border border-border/70 bg-card shadow-[0_1px_3px_rgba(15,23,42,0.06)]";

export default function ContactDetailsPage() {
  const { id } = useParams() as { id: string };
  const [activeTab, setActiveTab] = useState<ContactDetailTab>("overview");

  const { data: contact, isLoading: contactLoading, error: contactError } = useQuery({
    queryKey: ["contacts", id],
    queryFn: () => apiFetch<ContactRow>(`/contacts/${id}`),
  });

  const companyId = contact?.company_id;

  const { data: company, isLoading: companyLoading } = useQuery({
    queryKey: ["companies", companyId],
    queryFn: () => (companyId ? apiFetch<CompanyRow>(`/companies/${companyId}`) : Promise.resolve(null)),
    enabled: !!companyId,
  });

  const { data: leads = [] } = useQuery({
    queryKey: ["leads", "contact-details"],
    queryFn: () => apiListAll<LeadRow>("/leads"),
  });

  const [currentDate, setCurrentDate] = useState(new Date());

  const isLoading = contactLoading || companyLoading;

  const contactLeads = useMemo(() => {
    return leads.filter((l) => l.primary_contact_id === id || l.company_id === companyId);
  }, [leads, id, companyId]);

  const primaryLead = useMemo(() => {
    const asPrimary = contactLeads.find((l) => l.primary_contact_id === id);
    return asPrimary ?? contactLeads[0];
  }, [contactLeads, id]);

  const { data: tasks = [] } = useQuery({
    queryKey: ["tasks", primaryLead?.id],
    queryFn: () => (primaryLead ? apiList<TaskRow>(`/leads/${primaryLead.id}/tasks`) : Promise.resolve([])),
    enabled: !!primaryLead,
  });

  const { data: meetings = [] } = useQuery({
    queryKey: ["meetings", primaryLead?.id],
    queryFn: () => (primaryLead ? apiList<MeetingRow>(`/leads/${primaryLead.id}/meetings`) : Promise.resolve([])),
    enabled: !!primaryLead,
  });

  const pipelineTotal = useMemo(() => {
    return contactLeads.reduce((sum, l) => sum + (l.estimated_value != null ? Number(l.estimated_value) : 0), 0);
  }, [contactLeads]);

  const opportunityCount = useMemo(() => contactLeads.filter((l) => l.is_opportunity).length, [contactLeads]);

  if (isLoading) {
    return <div className="p-8 text-center text-muted-foreground">Loading contact details...</div>;
  }

  if (contactError || !contact) {
    return (
      <div className="p-8 text-center text-destructive">
        {contactError ? (contactError as Error).message : "Contact not found."}
      </div>
    );
  }

  const initials = contact.full_name
    .split(/\s+/)
    .map((n) => n[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  const companyInitial = (company?.name ?? "?").trim().slice(0, 1).toUpperCase();

  const locationParts = (company?.location || "").split(",");
  const city = locationParts[0]?.trim() || "-";
  const country = locationParts[1]?.trim() || "-";

  const pageTabs: { id: ContactDetailTab; label: string; count: number | null }[] = [
    { id: "overview", label: "Overview", count: null },
    { id: "notes", label: "Notes", count: 1 },
    { id: "conversations", label: "Conversations", count: 1 },
    { id: "timeline" as ContactDetailTab, label: "Timeline", count: contactLeads.length },
    { id: "reminders", label: "Reminders", count: 1 },
  ];

  const showLeadEvents = activeTab === "timeline";
  const showReview = activeTab === "notes";
  const showConversationsOnly = activeTab === "conversations";

  const tier = primaryLead ? scoreTier(primaryLead.priority_score) : null;

  return (
    <div className="mx-auto max-w-6xl space-y-4 pb-12 pt-2">
      <div className="flex items-center gap-2">
        <Link 
          href="/contacts" 
          className="group inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
        >
          <ChevronLeft className="h-3.5 w-3.5 transition-transform group-hover:-translate-x-0.5" />
          Back to Contacts
        </Link>
      </div>
      {/* Hero */}
      <div className={cn(cardShell, "overflow-hidden")}>
        <div className="flex flex-col gap-4 p-4 sm:p-5 md:flex-row md:items-start">
          <div className="relative h-16 w-16 shrink-0 overflow-hidden rounded-xl border border-border/60 bg-gradient-to-br from-teal-50 to-teal-100/80 dark:from-teal-950/50 dark:to-teal-900/30">
            {contact.avatar_url ? (
              // eslint-disable-next-line @next/next/no-img-element -- contact avatar from API
              <img src={contact.avatar_url} alt="" className="h-full w-full object-cover" />
            ) : (
              <div className="flex h-full w-full items-center justify-center text-2xl font-bold text-teal-800 dark:text-teal-200">
                {initials || "?"}
              </div>
            )}
          </div>
          <div className="min-w-0 flex-1 space-y-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Contact</p>
                <div className="mt-0.5 flex flex-wrap items-center gap-2">
                  <h1 className="text-xl font-bold tracking-tight text-[#0A1128] dark:text-foreground sm:text-2xl">
                    {contact.full_name}
                  </h1>
                  {contact.is_primary ? (
                    <Badge className="bg-amber-100 font-medium text-amber-900 dark:bg-amber-900/40 dark:text-amber-100">
                      Primary
                    </Badge>
                  ) : null}
                  <Badge variant="secondary" className="font-normal capitalize">
                    {contact.role || "Role unset"}
                  </Badge>
                </div>
                {company?.name ? (
                  <Link
                    href="/companies"
                    className="mt-1 inline-flex items-center gap-1 text-sm font-medium text-[#0B7FB3] hover:underline"
                  >
                    <Building2 className="h-3.5 w-3.5" />
                    {company.name}
                    <ChevronRight className="h-3.5 w-3.5 opacity-70" />
                  </Link>
                ) : null}
              </div>
              {primaryLead ? (
                <div className="flex flex-col items-end gap-1 text-right">
                  <div className="flex flex-wrap items-center justify-end gap-2">
                    <Badge variant="outline" className="font-normal capitalize">
                      {humanizeUnderscore(primaryLead.stage)}
                    </Badge>
                    <Badge
                      className={cn(
                        "font-semibold",
                        tier === "Hot" && "bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-200",
                        tier === "Warm" && "bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-200",
                        tier === "Cold" && "bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-200",
                      )}
                    >
                      {tier} · {primaryLead.priority_score}
                    </Badge>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">No related leads yet.</p>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-2 border-t border-border/50 pt-3">
              {contact.email ? (
                <a
                  href={`mailto:${contact.email}`}
                  className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-border/70 bg-background px-3 text-xs font-medium hover:bg-muted/50"
                >
                  <Mail className="h-3.5 w-3.5 text-muted-foreground" />
                  Email
                </a>
              ) : null}
              {contact.phone ? (
                <a
                  href={`tel:${contact.phone.replace(/\s/g, "")}`}
                  className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-border/70 bg-background px-3 text-xs font-medium hover:bg-muted/50"
                >
                  <Phone className="h-3.5 w-3.5 text-muted-foreground" />
                  Call
                </a>
              ) : null}
              {contact.linkedin_url ? (
                <a
                  href={contact.linkedin_url.startsWith("http") ? contact.linkedin_url : `https://${contact.linkedin_url}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-border/70 bg-background px-3 text-xs font-medium hover:bg-muted/50"
                >
                  <Linkedin className="h-3.5 w-3.5 text-muted-foreground" />
                  LinkedIn
                </a>
              ) : null}
              <button
                type="button"
                className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-transparent px-3 text-xs font-medium text-muted-foreground hover:bg-muted/60 hover:text-foreground"
              >
                <MessageSquare className="h-3.5 w-3.5" />
                Message
              </button>
              <button
                type="button"
                className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-transparent px-3 text-xs font-medium text-muted-foreground hover:bg-muted/60 hover:text-foreground"
              >
                <Bell className="h-3.5 w-3.5" />
                Reminder
              </button>
              <button
                type="button"
                className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-transparent px-3 text-xs font-medium text-muted-foreground hover:bg-muted/60 hover:text-foreground"
              >
                <Plus className="h-3.5 w-3.5" />
                Note
              </button>
              <button
                type="button"
                className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-transparent px-3 text-xs font-medium text-muted-foreground hover:bg-muted/60 hover:text-foreground"
              >
                <PhoneCall className="h-3.5 w-3.5" />
                Log call
              </button>
              {primaryLead ? (
                <Button size="sm" className="ml-auto h-9 gap-1.5 bg-[#0A1128] text-xs text-white hover:bg-[#1a2a53] shadow-sm" asChild>
                  <Link href={`/leads/${primaryLead.id}`}>
                    Open lead
                    <ArrowRight className="h-3.5 w-3.5" />
                  </Link>
                </Button>
              ) : null}
            </div>
          </div>
        </div>
      </div>

      <div className="space-y-6">
        <div className={cn(cardShell, "p-2")}>
          <div
            role="tablist"
            aria-label="Contact"
            className="flex flex-wrap gap-1 rounded-lg bg-muted/70 p-1 dark:bg-muted/40"
          >
            {pageTabs.map((t) => (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={activeTab === t.id}
                onClick={() => setActiveTab(t.id)}
                className={cn(
                  segmentClass,
                  activeTab === t.id
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:bg-background/60 hover:text-foreground",
                )}
              >
                {t.label}
                {t.count != null ? (
                  <span className="ml-1 tabular-nums text-muted-foreground">({t.count})</span>
                ) : null}
              </button>
            ))}
          </div>
        </div>

        {activeTab === "overview" ? (
          <div className="space-y-6">
            {/* KPI strip */}
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Card className={cn(cardShell, "shadow-none")}>
                <CardContent className="p-4">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                      Related leads
                    </span>
                    <Briefcase className="h-4 w-4 text-muted-foreground" />
                  </div>
                  <p className="mt-2 text-2xl font-semibold tabular-nums text-[#0A1128] dark:text-foreground">
                    {contactLeads.length}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">Company + primary contact</p>
                </CardContent>
              </Card>
              <Card className={cn(cardShell, "shadow-none")}>
                <CardContent className="p-4">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                      Opportunities
                    </span>
                    <Layers className="h-4 w-4 text-muted-foreground" />
                  </div>
                  <p className="mt-2 text-2xl font-semibold tabular-nums text-[#0A1128] dark:text-foreground">
                    {opportunityCount}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">Marked as opportunity</p>
                </CardContent>
              </Card>
              <Card className={cn(cardShell, "shadow-none")}>
                <CardContent className="p-4">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                      Pipeline (est.)
                    </span>
                    <DollarSign className="h-4 w-4 text-muted-foreground" />
                  </div>
                  <p className="mt-2 text-2xl font-semibold tabular-nums text-[#0A1128] dark:text-foreground">
                    {contactLeads.length ? formatMoney(pipelineTotal, primaryLead?.currency) : "—"}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">Sum of related deal values</p>
                </CardContent>
              </Card>
              <Card className={cn(cardShell, "shadow-none")}>
                <CardContent className="p-4">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                      Next follow-up
                    </span>
                    <CalendarClock className="h-4 w-4 text-muted-foreground" />
                  </div>
                  <p className="mt-2 text-base font-semibold text-[#0A1128] dark:text-foreground">
                    {primaryLead?.next_followup_date
                      ? safeFormatDate(primaryLead.next_followup_date, "EEE, MMM d")
                      : "None set"}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">From primary / first related lead</p>
                </CardContent>
              </Card>
            </div>

            <div className="grid gap-6 lg:grid-cols-3">
              <div className="space-y-6 lg:col-span-2">
                <Card className={cardShell}>
                  <CardHeader className="flex flex-row items-center gap-3 border-b border-border/60 pb-4">
                    <div className="relative h-12 w-12 shrink-0 overflow-hidden rounded-xl border border-border/60 bg-muted/40">
                      {company?.logo_url ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={company.logo_url} alt="" className="h-full w-full object-cover" />
                      ) : (
                        <div className="flex h-full w-full items-center justify-center text-sm font-bold text-muted-foreground">
                          {companyInitial}
                        </div>
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <CardTitle className="text-base font-semibold">Company</CardTitle>
                      <p className="text-sm text-muted-foreground">{company?.name ?? "—"}</p>
                    </div>
                    {company?.linkedin_url ? (
                      <a
                        href={
                          company.linkedin_url.startsWith("http")
                            ? company.linkedin_url
                            : `https://${company.linkedin_url}`
                        }
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex h-9 shrink-0 items-center gap-1 rounded-lg border border-border/70 px-3 text-xs font-medium hover:bg-muted/50"
                      >
                        <Linkedin className="h-3.5 w-3.5" />
                        Page
                      </a>
                    ) : null}
                  </CardHeader>
                  <CardContent className="p-0 text-[13px]">
                    <div className="grid sm:grid-cols-2">
                      <div className="border-b border-border/40 px-4 py-3 sm:border-r">
                        <p className="text-muted-foreground">Industry</p>
                        <p className="mt-0.5 font-medium text-foreground">{company?.industry || "—"}</p>
                      </div>
                      <div className="border-b border-border/40 px-4 py-3">
                        <p className="text-muted-foreground">Segment</p>
                        <p className="mt-0.5 font-medium capitalize text-foreground">{company?.segment || "—"}</p>
                      </div>
                      <div className="border-b border-border/40 px-4 py-3 sm:border-r">
                        <p className="text-muted-foreground">Size</p>
                        <p className="mt-0.5 font-medium text-foreground">{company?.size || "—"}</p>
                      </div>
                      <div className="border-b border-border/40 px-4 py-3">
                        <p className="text-muted-foreground">Location</p>
                        <p className="mt-0.5 font-medium text-foreground">{company?.location || "—"}</p>
                      </div>
                      <div className="border-b border-border/40 px-4 py-3 sm:border-r">
                        <p className="text-muted-foreground">City</p>
                        <p className="mt-0.5 font-medium text-foreground">{city}</p>
                      </div>
                      <div className="border-b border-border/40 px-4 py-3">
                        <p className="text-muted-foreground">Country</p>
                        <p className="mt-0.5 font-medium text-foreground">{country}</p>
                      </div>
                      <div className="px-4 py-3 sm:col-span-2">
                        <p className="text-muted-foreground">Website</p>
                        <p className="mt-0.5 font-medium text-foreground break-all">
                          {company?.website ? (
                            <a
                              href={company.website.startsWith("http") ? company.website : `https://${company.website}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-[#0B7FB3] hover:underline"
                            >
                              {company.website.replace(/^https?:\/\//, "")}
                            </a>
                          ) : (
                            "—"
                          )}
                        </p>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                <Card className={cardShell}>
                  <CardHeader className="border-b border-border/60 pb-4">
                    <CardTitle className="text-base font-semibold">Contact record</CardTitle>
                    <p className="text-xs font-normal text-muted-foreground">How to reach them & CRM metadata</p>
                  </CardHeader>
                  <CardContent className="p-0 text-[13px]">
                    <div className="grid sm:grid-cols-2">
                      <div className="border-b border-border/40 px-4 py-3 sm:border-r">
                        <p className="text-muted-foreground">Email</p>
                        <p className="mt-0.5 break-all font-medium text-foreground">
                          {contact.email ? (
                            <a href={`mailto:${contact.email}`} className="text-[#0B7FB3] hover:underline">
                              {contact.email}
                            </a>
                          ) : (
                            "—"
                          )}
                        </p>
                      </div>
                      <div className="border-b border-border/40 px-4 py-3">
                        <p className="text-muted-foreground">Phone</p>
                        <p className="mt-0.5 font-medium text-foreground">
                          {contact.phone ? (
                            <a href={`tel:${contact.phone.replace(/\s/g, "")}`} className="hover:underline">
                              {contact.phone}
                            </a>
                          ) : (
                            "—"
                          )}
                        </p>
                      </div>
                      <div className="border-b border-border/40 px-4 py-3 sm:col-span-2 sm:border-r-0">
                        <p className="text-muted-foreground">LinkedIn</p>
                        <p className="mt-0.5 font-medium break-all text-foreground">
                          {contact.linkedin_url ? (
                            <a
                              href={
                                contact.linkedin_url.startsWith("http")
                                  ? contact.linkedin_url
                                  : `https://${contact.linkedin_url}`
                              }
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-[#0B7FB3] hover:underline"
                            >
                              {contact.linkedin_url}
                            </a>
                          ) : (
                            "—"
                          )}
                        </p>
                      </div>
                      <div className="px-4 py-3 sm:col-span-2">
                        <p className="text-muted-foreground">In CRM since</p>
                        <p className="mt-0.5 font-medium text-foreground">
                          {safeFormatDate(contact.created_at, "MMMM d, yyyy")}
                        </p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>

              <div className="space-y-6">
                <Card className={cardShell}>
                  <CardHeader className="flex flex-row items-center justify-between border-b border-border/60 pb-3">
                    <CardTitle className="text-base font-semibold">Deals & pipeline</CardTitle>
                    <Sparkles className="h-4 w-4 text-muted-foreground" />
                  </CardHeader>
                  <CardContent className="space-y-3 pt-4">
                    {contactLeads.length === 0 ? (
                      <p className="text-sm text-muted-foreground">No leads linked to this contact or company.</p>
                    ) : (
                      <ul className="space-y-2">
                        {contactLeads.slice(0, 5).map((lead) => (
                          <li key={lead.id}>
                            <Link
                              href={`/leads/${lead.id}`}
                              className="block rounded-lg border border-border/60 bg-muted/20 p-3 transition-colors hover:bg-muted/40"
                            >
                              <div className="flex items-start justify-between gap-2">
                                <span className="text-sm font-medium text-foreground capitalize">
                                  {humanizeUnderscore(lead.project_type)}
                                </span>
                                <Badge variant="outline" className="shrink-0 text-[10px] capitalize">
                                  {humanizeUnderscore(lead.stage)}
                                </Badge>
                              </div>
                              <p className="mt-1 text-xs text-muted-foreground">
                                {formatMoney(lead.estimated_value, lead.currency)} · {scoreTier(lead.priority_score)}{" "}
                                · {humanizeUnderscore(lead.lead_source)}
                              </p>
                              {lead.primary_contact_id === id ? (
                                <span className="mt-2 inline-block text-[10px] font-medium uppercase tracking-wide text-[#0B7FB3]">
                                  Primary on deal
                                </span>
                              ) : null}
                            </Link>
                          </li>
                        ))}
                      </ul>
                    )}
                    {contactLeads.length > 5 ? (
                      <p className="text-center text-xs text-muted-foreground">+{contactLeads.length - 5} more</p>
                    ) : null}
                  </CardContent>
                </Card>

                <Card className={cardShell}>
                  <CardHeader className="border-b border-border/60 pb-3">
                    <CardTitle className="text-base font-semibold">360° shortcuts</CardTitle>
                    <p className="text-xs font-normal text-muted-foreground">Jump to detailed streams</p>
                  </CardHeader>
                  <CardContent className="flex flex-col gap-2 pt-4">
                    <button
                      type="button"
                      onClick={() => setActiveTab("notes")}
                      className="flex items-center justify-between rounded-lg border border-border/50 px-3 py-2.5 text-left text-sm font-medium hover:bg-muted/50"
                    >
                      Notes & reviews
                      <ChevronRight className="h-4 w-4 text-muted-foreground" />
                    </button>
                    <button
                      type="button"
                      onClick={() => setActiveTab("timeline")}
                      className="flex items-center justify-between rounded-lg border border-border/50 px-3 py-2.5 text-left text-sm font-medium hover:bg-muted/50"
                    >
                      Lead interactions
                      <ChevronRight className="h-4 w-4 text-muted-foreground" />
                    </button>
                    <button
                      type="button"
                      onClick={() => setActiveTab("reminders")}
                      className="flex items-center justify-between rounded-lg border border-border/50 px-3 py-2.5 text-left text-sm font-medium hover:bg-muted/50"
                    >
                      Reminders & uploads
                      <ChevronRight className="h-4 w-4 text-muted-foreground" />
                    </button>
                  </CardContent>
                </Card>
              </div>
            </div>

            {/* Activity snapshot */}
            <Card className={cardShell}>
              <CardHeader className="flex flex-row items-center justify-between border-b border-border/60 pb-3">
                <div>
                  <CardTitle className="text-base font-semibold">Activity snapshot</CardTitle>
                  <p className="text-xs font-normal text-muted-foreground">Latest signals across this contact</p>
                </div>
                <Button variant="outline" size="sm" className="h-8 text-xs" onClick={() => setActiveTab("timeline")}>
                  View interactions
                  <ArrowRight className="ml-1 h-3.5 w-3.5" />
                </Button>
              </CardHeader>
              <CardContent className="pt-4">
                    {contactLeads[0] ? (
                      <div className="rounded-lg border border-border/50 bg-muted/15 p-3">
                        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                          <Globe className="h-3.5 w-3.5" />
                          Lead
                        </div>
                        <p className="mt-2 text-sm font-medium text-foreground capitalize">
                          {humanizeUnderscore(contactLeads[0].stage)}
                        </p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          {humanizeUnderscore(contactLeads[0].project_type)} ·{" "}
                          {safeFormatDate(contactLeads[0].updated_at, "MMM d")}
                        </p>
                      </div>
                    ) : (
                      <div className="rounded-lg border border-dashed border-border/60 p-3 text-sm text-muted-foreground">
                        No lead movement yet.
                      </div>
                    )}
                    <div className="rounded-lg border border-dashed border-border/60 p-3 text-sm text-muted-foreground flex items-center justify-center">
                      <p className="text-xs italic">Awaiting more signals...</p>
                    </div>
                </CardContent>
              </Card>
          </div>
        ) : (
          <div className="space-y-6">
            <h3 className="text-lg font-semibold text-foreground">
              {pageTabs.find((t) => t.id === activeTab)?.label ?? "History"}
            </h3>

            {showConversationsOnly ? (
              <p className="text-sm text-muted-foreground">No conversations logged for this contact yet.</p>
            ) : showReview ? (
              <p className="text-sm text-muted-foreground">No notes or reviews have been added for this contact.</p>
            ) : activeTab === "reminders" ? (
              <Card className={cn(cardShell, "overflow-hidden")}>
                <CardHeader className="flex flex-row items-center justify-between border-b border-border/60 bg-muted/5 py-3">
                  <div className="flex items-center gap-4">
                    <h4 className="text-sm font-semibold">{format(currentDate, "MMMM yyyy")}</h4>
                    <div className="flex items-center gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7"
                        onClick={() => setCurrentDate(subMonths(currentDate, 1))}
                      >
                        <ChevronLeft className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7"
                        onClick={() => setCurrentDate(addMonths(currentDate, 1))}
                      >
                        <ChevronRight className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                  <Button variant="outline" size="sm" className="h-8 gap-1.5 text-xs" onClick={() => setCurrentDate(new Date())}>
                    Today
                  </Button>
                </CardHeader>
                <CardContent className="p-0">
                  <div className="grid grid-cols-7 border-b border-border/50 bg-muted/10">
                    {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((day) => (
                      <div key={day} className="py-2 text-center text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                        {day}
                      </div>
                    ))}
                  </div>
                  <div className="grid grid-cols-7 border-l border-t border-border/30">
                    {(() => {
                      const monthStart = startOfMonth(currentDate);
                      const monthEnd = endOfMonth(monthStart);
                      const startDate = startOfWeek(monthStart);
                      const endDate = endOfWeek(monthEnd);
                      const calendarDays = eachDayOfInterval({ start: startDate, end: endDate });

                      return calendarDays.map((day) => {
                        const dayTasks = tasks.filter((t) => isSameDay(parseISO(t.due_at), day));
                        const dayMeetings = meetings.filter((m) => isSameDay(parseISO(m.scheduled_at), day));
                        const hasItems = dayTasks.length > 0 || dayMeetings.length > 0;

                        return (
                          <div
                            key={day.toString()}
                            className={cn(
                              "min-h-[100px] border-b border-r border-border/30 p-2 transition-colors",
                              !isSameMonth(day, monthStart) && "bg-muted/5 opacity-40",
                              isSameDay(day, new Date()) && "bg-blue-50/30 dark:bg-blue-900/10"
                            )}
                          >
                            <span
                              className={cn(
                                "inline-flex h-6 w-6 items-center justify-center rounded-full text-xs font-medium",
                                isSameDay(day, new Date()) && "bg-blue-600 text-white shadow-sm"
                              )}
                            >
                              {format(day, "d")}
                            </span>
                            <div className="mt-1 space-y-1">
                              {dayMeetings.map((m) => (
                                <div
                                  key={m.id}
                                  className="truncate rounded bg-purple-100 px-1.5 py-0.5 text-[10px] font-medium text-purple-700 dark:bg-purple-900/40 dark:text-purple-200"
                                  title={`Meeting: ${m.title}`}
                                >
                                  {m.title}
                                </div>
                              ))}
                              {dayTasks.map((t) => (
                                <div
                                  key={t.id}
                                  className={cn(
                                    "truncate rounded px-1.5 py-0.5 text-[10px] font-medium",
                                    t.status === "completed"
                                      ? "bg-slate-100 text-slate-500 line-through dark:bg-slate-800"
                                      : "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-200"
                                  )}
                                  title={`Task: ${t.title}`}
                                >
                                  {t.title}
                                </div>
                              ))}
                            </div>
                          </div>
                        );
                      });
                    })()}
                  </div>
                </CardContent>
              </Card>
            ) : (
              <div className="relative space-y-6 before:absolute before:inset-0 before:ml-4 before:-translate-x-px before:h-full before:w-0.5 before:bg-border/50 md:before:mx-auto md:before:translate-x-0">
                {showLeadEvents
                  ? contactLeads.map((lead) => (
                      <div
                        key={lead.id}
                        className="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group"
                      >
                        <div className="z-10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border-2 border-white bg-orange-100 text-orange-500 shadow-sm dark:border-card md:absolute md:left-1/2 md:-ml-4">
                          <Globe className="h-3.5 w-3.5" />
                        </div>
                        <Card className="w-[calc(100%-3rem)] p-4 shadow-sm md:w-[calc(50%-2rem)]">
                          <div className="flex flex-col gap-1">
                            <div className="flex items-start justify-between">
                              <p className="text-sm font-medium text-foreground">
                                Triggered an event{" "}
                                <span className="font-normal text-orange-500">lead-stage-change</span>
                              </p>
                              <span className="shrink-0 text-[11px] text-muted-foreground">
                                {new Date(lead.created_at).toLocaleString()}
                              </span>
                            </div>
                            <div className="mt-2 border-l-2 border-orange-200 pl-3 text-xs text-muted-foreground">
                              <span className="font-semibold text-foreground">source</span> {lead.lead_source}
                              <br />
                              <span className="font-semibold text-foreground">stage</span> {lead.stage}
                            </div>
                            <div className="mt-3 flex items-center gap-1.5">
                              <div className="flex h-5 w-5 items-center justify-center rounded-full bg-slate-200 text-[9px] font-bold text-slate-600">
                                {initials}
                              </div>
                              <span className="text-xs text-muted-foreground">Triggered by: {contact.full_name}</span>
                            </div>
                          </div>
                        </Card>
                      </div>
                    ))
                  : null}

                {activeTab === "timeline" && contactLeads.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No lead interactions yet.</p>
                ) : null}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
