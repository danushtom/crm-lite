"use client";

import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input } from "@dracara/ui";
import { scoreTier, type CompanyRow, type ContactRow, type LeadRow, type LeadIntelligenceRow, type ActivityRow } from "@dracara/types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { format, parseISO } from "date-fns";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { LeadTasks } from "@/components/leads/lead-tasks";
import { apiFetch } from "@/lib/api";
import {
  Building2,
  Calendar,
  ChevronRight,
  Clock3,
  DollarSign,
  Globe,
  Info,
  Layers,
  Linkedin,
  Mail,
  MapPin,
  Percent,
  Phone,
  Sparkles,
  UserCircle,
} from "lucide-react";

const kpiCardClass =
  "flex h-full flex-col rounded-xl border border-border/70 bg-card shadow-[0_1px_3px_rgba(15,23,42,0.06)]";
const kpiFooterSpacer = "mt-auto min-h-[2.75rem]";

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

function humanizeUnderscore(s: string): string {
  return s
    .split("_")
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function formatActivityWhen(iso: string | undefined): string {
  if (!iso) return "—";
  try {
    return format(parseISO(iso), "MMM d, h:mm a");
  } catch {
    return iso;
  }
}

type LeadDetailResponse = {
  lead: LeadRow;
  lead_intelligence: LeadIntelligenceRow | null;
  activities?: ActivityRow[];
};

export default function LeadOverviewPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["lead", id],
    queryFn: () =>
      apiFetch<LeadDetailResponse>(`/leads/${id}?include_related=true`),
  });

  const lead = data?.lead;
  const intelligence = data?.lead_intelligence;
  const activities = data?.activities ?? [];

  const { data: company } = useQuery({
    queryKey: ["company", lead?.company_id],
    queryFn: () => apiFetch<CompanyRow>(`/companies/${String(lead?.company_id)}`),
    enabled: !!lead?.company_id,
  });

  const { data: contact } = useQuery({
    queryKey: ["contact", lead?.primary_contact_id],
    queryFn: () => apiFetch<ContactRow>(`/contacts/${String(lead?.primary_contact_id)}`),
    enabled: !!lead?.primary_contact_id,
  });

  const { data: oppRows = [] } = useQuery({
    queryKey: ["opportunity-by-lead", id],
    queryFn: () => apiFetch<Record<string, unknown>[]>(`/opportunities?lead_id=${encodeURIComponent(id)}`),
    enabled: !!id,
  });

  const opportunityId = oppRows[0]?.id != null ? String(oppRows[0].id) : null;

  const update = useMutation({
    mutationFn: (patch: Record<string, unknown>) =>
      apiFetch(`/leads/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["lead", id] }),
  });

  const convert = useMutation({
    mutationFn: () => apiFetch(`/leads/${id}/convert`, { method: "POST", body: "{}" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["lead", id] });
      qc.invalidateQueries({ queryKey: ["opportunity-by-lead", id] });
    },
  });

  const [nextFollowup, setNextFollowup] = useState("");

  useEffect(() => {
    const raw = lead?.next_followup_date;
    if (raw != null && String(raw).length > 0) {
      setNextFollowup(String(raw).slice(0, 10));
    }
  }, [lead?.next_followup_date]);

  if (isLoading || !data) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-36 rounded-xl bg-muted/80" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-28 rounded-xl bg-muted/60" />
          ))}
        </div>
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="h-64 rounded-xl bg-muted/60 lg:col-span-2" />
          <div className="h-64 rounded-xl bg-muted/60" />
        </div>
      </div>
    );
  }

  const score = Number(lead?.priority_score ?? 0);
  const tier = scoreTier(score);
  const stageRaw = String(lead?.stage ?? "prospect");
  const pipelineLabel = humanizeUnderscore(stageRaw);

  const tags = Array.isArray(lead?.tags) ? (lead?.tags as unknown[]).map((t) => String(t)) : [];

  const formatCurrency = (val: unknown, curr: unknown) => {
    if (val == null) return "—";
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: String(curr ?? "USD"),
      maximumFractionDigits: 0,
    }).format(Number(val));
  };

  const intelHighlights: { label: string; value: unknown }[] = [
    { label: "Pain points", value: intelligence?.pain_points },
    { label: "Budget hints", value: intelligence?.budget_hints },
    { label: "Decision makers", value: intelligence?.decision_makers },
  ].filter((x) => x.value != null && String(x.value).trim() !== "");

  return (
    <div className="space-y-6">

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4 lg:items-stretch">
        <Card className={kpiCardClass}>
          <CardContent className="flex flex-1 flex-col p-4">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Est. value</span>
              <DollarSign className="h-4 w-4 shrink-0 text-muted-foreground/80" />
            </div>
            <p className="mt-3 text-2xl font-semibold tabular-nums leading-none text-[#0A1128] dark:text-foreground">
              {formatCurrency(lead?.estimated_value, lead?.currency)}
            </p>
            <div className={kpiFooterSpacer} aria-hidden />
          </CardContent>
        </Card>

        <Card className={kpiCardClass}>
          <CardContent className="flex flex-1 flex-col p-4">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Win probability</span>
              <Percent className="h-4 w-4 shrink-0 text-muted-foreground/80" />
            </div>
            <p className="mt-3 text-2xl font-semibold tabular-nums leading-none text-[#0A1128] dark:text-foreground">
              {String(lead?.deal_probability ?? "0")}%
            </p>
            <div className={`${kpiFooterSpacer} flex flex-col justify-end`}>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                <div
                  className={`h-full rounded-full ${
                    Number(lead?.deal_probability) >= 70
                      ? "bg-emerald-500"
                      : Number(lead?.deal_probability) >= 40
                        ? "bg-amber-500"
                        : "bg-rose-500"
                  }`}
                  style={{ width: `${Number(lead?.deal_probability ?? 0)}%` }}
                />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className={kpiCardClass}>
          <CardContent className="flex flex-1 flex-col p-4">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Next follow-up</span>
              <Calendar className="h-4 w-4 shrink-0 text-muted-foreground/80" />
            </div>
            <p
              className={`mt-3 text-2xl font-semibold tabular-nums leading-none ${
                lead?.next_followup_date
                  ? "text-[#0A1128] dark:text-foreground"
                  : "text-muted-foreground"
              }`}
            >
              {lead?.next_followup_date
                ? format(parseISO(String(lead.next_followup_date)), "EEE, MMM d")
                : "Not scheduled"}
            </p>
            <div className={`${kpiFooterSpacer} flex flex-row flex-wrap items-end gap-2`}>
              <Input
                type="date"
                className="h-8 w-[9.5rem] shrink-0 text-xs"
                value={nextFollowup}
                onChange={(e) => setNextFollowup(e.target.value)}
              />
              <Button
                size="sm"
                variant="secondary"
                className="h-8 shrink-0 text-xs"
                disabled={!nextFollowup || update.isPending}
                onClick={() => update.mutate({ next_followup_date: nextFollowup })}
              >
                Save
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card className={kpiCardClass}>
          <CardContent className="flex flex-1 flex-col p-4">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Last contact</span>
              <Clock3 className="h-4 w-4 shrink-0 text-muted-foreground/80" />
            </div>
            <p
              className={`mt-3 text-2xl font-semibold tabular-nums leading-none ${
                lead?.last_contact_date ? "text-[#0A1128] dark:text-foreground" : "text-muted-foreground"
              }`}
            >
              {lead?.last_contact_date
                ? format(parseISO(String(lead.last_contact_date)), "MMM d, yyyy")
                : "Never"}
            </p>
            <div className={kpiFooterSpacer} aria-hidden />
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Left Column: Company & Contact */}
        <div className="space-y-6 lg:col-span-1">
          <Card className="rounded-xl border border-border/70 bg-card shadow-[0_1px_3px_rgba(15,23,42,0.06)]">
            <CardHeader className="border-b border-border/50 pb-3">
              <CardTitle className="flex items-center gap-2 text-base font-semibold">
                <Building2 className="h-4 w-4 text-muted-foreground" />
                Company profile
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-4">
              {company ? (
                <div className="space-y-4">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-border/60 bg-muted/30 text-lg font-bold text-slate-700 dark:text-slate-200">
                      {company.name.charAt(0)}
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-foreground">{company.name}</p>
                      <p className="text-xs text-muted-foreground">{company.website?.replace(/^https?:\/\//, "") || "No website"}</p>
                    </div>
                  </div>
                  <div className="space-y-2.5 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Industry</span>
                      <span className="font-medium text-foreground">{company.industry ? humanizeUnderscore(company.industry) : "—"}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Size</span>
                      <span className="font-medium text-foreground">{company.size || "—"}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Location</span>
                      <span className="font-medium text-foreground">{company.location || "—"}</span>
                    </div>
                  </div>
                  <div className="flex gap-2 pt-2">
                    {company.website && (
                      <Button variant="outline" size="sm" className="h-8 flex-1 gap-1 text-xs" asChild>
                        <a href={company.website.startsWith("http") ? company.website : `https://${company.website}`} target="_blank" rel="noopener noreferrer">
                          <Globe className="h-3 w-3" />
                          Website
                        </a>
                      </Button>
                    )}
                    {company.linkedin_url && (
                      <Button variant="outline" size="sm" className="h-8 flex-1 gap-1 text-xs" asChild>
                        <a href={company.linkedin_url} target="_blank" rel="noopener noreferrer">
                          <Linkedin className="h-3 w-3" />
                          LinkedIn
                        </a>
                      </Button>
                    )}
                  </div>
                </div>
              ) : (
                <div className="py-10 text-center text-sm text-muted-foreground">No company linked.</div>
              )}
            </CardContent>
          </Card>

          <Card className="rounded-xl border border-border/70 bg-card shadow-[0_1px_3px_rgba(15,23,42,0.06)]">
            <CardHeader className="border-b border-border/50 pb-3">
              <CardTitle className="flex items-center gap-2 text-base font-semibold">
                <UserCircle className="h-4 w-4 text-muted-foreground" />
                Primary contact
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-4">
              {contact ? (
                <div className="space-y-4">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-full border border-border/60 bg-blue-50 text-lg font-bold text-blue-700 dark:bg-blue-900/30 dark:text-blue-200">
                      {contact.full_name.charAt(0)}
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-foreground">{contact.full_name}</p>
                      <p className="text-xs text-muted-foreground">{contact.role || "Role unset"}</p>
                    </div>
                  </div>
                  <div className="space-y-2.5 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Email</span>
                      <a href={`mailto:${contact.email}`} className="font-medium text-[#0B7FB3] hover:underline">
                        {contact.email}
                      </a>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Phone</span>
                      <span className="font-medium text-foreground">{contact.phone || "—"}</span>
                    </div>
                  </div>
                  <div className="flex gap-2 pt-2">
                    <Button variant="outline" size="sm" className="h-8 flex-1 gap-1 text-xs" asChild>
                      <a href={`mailto:${contact.email}`}>
                        <Mail className="h-3 w-3" />
                        Email
                      </a>
                    </Button>
                    <Button variant="outline" size="sm" className="h-8 flex-1 gap-1 text-xs" asChild>
                      <a href={`tel:${contact.phone}`}>
                        <Phone className="h-3 w-3" />
                        Call
                      </a>
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="py-10 text-center text-sm text-muted-foreground">No primary contact linked.</div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Middle Column: Intelligence & Context */}
        <div className="space-y-6 lg:col-span-1">
          <Card className="flex h-full flex-col rounded-xl border border-border/70 bg-card shadow-[0_1px_3px_rgba(15,23,42,0.06)]">
            <CardHeader className="flex flex-row items-center justify-between border-b border-border/50 pb-4">
              <CardTitle className="flex items-center gap-2 text-base font-semibold">
                <Sparkles className="h-4 w-4 text-muted-foreground" />
                Sales intelligence
              </CardTitle>
              <Button variant="ghost" size="sm" className="h-8 gap-1 text-xs text-[#0B7FB3]" asChild>
                <Link href={`/leads/${id}/intelligence`}>
                  Manage
                  <ChevronRight className="h-3.5 w-3.5" />
                </Link>
              </Button>
            </CardHeader>
            <CardContent className="flex-1 space-y-4 pt-4">
              {intelHighlights.length > 0 ? (
                intelHighlights.map(({ label, value }) => (
                  <div key={label} className="space-y-1.5 rounded-lg border border-border/60 bg-muted/20 px-3 py-3">
                    <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">{label}</p>
                    <p className="text-sm leading-snug text-foreground">{String(value)}</p>
                  </div>
                ))
              ) : (
                <div className="flex flex-col items-center justify-center py-12 text-center">
                  <div className="rounded-full bg-muted/40 p-3">
                    <Info className="h-6 w-6 text-muted-foreground/60" />
                  </div>
                  <p className="mt-3 text-sm text-muted-foreground">No intelligence data yet.</p>
                  <Button variant="link" size="sm" className="mt-1 h-auto text-xs text-[#0B7FB3]" asChild>
                    <Link href={`/leads/${id}/intelligence`}>Add notes</Link>
                  </Button>
                </div>
              )}

              {intelligence?.comm_preference && (
                <div className="mt-4 border-t border-border/40 pt-4">
                  <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Preferred channel</p>
                  <div className="mt-2 flex items-center gap-2">
                    <Badge variant="secondary" className="bg-blue-50 text-blue-700 dark:bg-blue-900/40 dark:text-blue-200">
                      {String(intelligence.comm_preference).toUpperCase()}
                    </Badge>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

        </div>

        {/* Right Column: Activity Feed */}
        <div className="space-y-6 lg:col-span-1">
          <Card className="flex h-full flex-col rounded-xl border border-border/70 bg-card shadow-[0_1px_3px_rgba(15,23,42,0.06)]">
            <CardHeader className="border-b border-border/50 pb-3">
              <CardTitle className="flex items-center gap-2 text-base font-semibold">
                <Clock3 className="h-4 w-4 text-muted-foreground" />
                Recent activity
              </CardTitle>
            </CardHeader>
            <CardContent className="flex-1 pt-4">
              {activities.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 text-center">
                  <p className="text-sm text-muted-foreground">No activity logged.</p>
                </div>
              ) : (
                <ul className="space-y-4">
                  {activities.slice(0, 6).map((a) => (
                    <li key={String(a.id)} className="relative pl-6 before:absolute before:left-0 before:top-1 before:h-2 before:w-2 before:rounded-full before:bg-blue-500">
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                          {humanizeUnderscore(String(a.type ?? "note"))}
                        </span>
                        <span className="text-[10px] text-muted-foreground">
                          {formatActivityWhen(String(a.performed_at ?? ""))}
                        </span>
                      </div>
                      <p className="mt-1 text-sm leading-snug text-foreground line-clamp-2">
                        {String(a.description ?? "—")}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
              {activities.length > 0 && (
                <Button variant="ghost" size="sm" className="mt-4 w-full h-8 text-xs text-muted-foreground hover:text-foreground" asChild>
                  <Link href={`/leads/${id}/timeline`}>
                    View full timeline
                  </Link>
                </Button>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Left Bottom: Opportunities */}
        <Card className="rounded-xl border border-border/70 bg-card shadow-[0_1px_3px_rgba(15,23,42,0.06)]">
          <CardHeader className="flex flex-row items-center justify-between border-b border-border/50 pb-3">
            <CardTitle className="flex items-center gap-2 text-base font-semibold">
              <Layers className="h-4 w-4 text-muted-foreground" />
              Related opportunities
            </CardTitle>
            <Button variant="ghost" size="sm" className="h-8 gap-1.5 text-xs text-[#0B7FB3]" asChild>
              <Link href={`/leads/${id}/opportunities`}>
                Manage
                <ChevronRight className="h-3.5 w-3.5" />
              </Link>
            </Button>
          </CardHeader>
          <CardContent className="pt-4">
            {oppRows.length > 0 ? (
              <div className="space-y-3">
                {oppRows.slice(0, 3).map((opp) => (
                  <Link
                    key={String(opp.id)}
                    href={`/opportunities/${String(opp.id)}`}
                    className="block rounded-lg border border-border/60 bg-muted/20 p-3 transition-colors hover:bg-muted/40"
                  >
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-medium text-foreground">{String(opp.title || "Untitled Opportunity")}</p>
                      <Badge variant="outline" className="text-[10px] capitalize">
                        {humanizeUnderscore(String(opp.stage))}
                      </Badge>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {formatCurrency(opp.quoted_value, opp.currency)} · {opp.deal_probability}% probability
                    </p>
                  </Link>
                ))}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-10 text-center">
                <p className="text-sm text-muted-foreground">No active opportunities.</p>
                {!lead?.is_opportunity && (
                  <Button
                    size="sm"
                    variant="outline"
                    className="mt-4 h-8 gap-1.5 text-xs"
                    disabled={convert.isPending}
                    onClick={() => convert.mutate()}
                  >
                    <Sparkles className="h-3.5 w-3.5" />
                    Activate pipeline
                  </Button>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Right Bottom: Tasks */}
        <LeadTasks leadId={id} />
      </div>

      <div className="space-y-6">
        {tags.length > 0 ? (
          <Card className="rounded-xl border border-border/70 bg-card shadow-[0_1px_3px_rgba(15,23,42,0.06)]">
            <CardHeader className="border-b border-border/50 pb-3">
              <CardTitle className="text-base font-semibold">Lead tags</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-1.5 pt-4">
              {tags.map((t) => (
                <Badge key={t} variant="secondary" className="font-normal">
                  {t}
                </Badge>
              ))}
            </CardContent>
          </Card>
        ) : null}
      </div>
    </div>
  );
}
