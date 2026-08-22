"use client";

import { Badge, Button, Card, CardContent } from "@dracara/ui";
import { scoreTier, type CompanyRow, type ContactRow, type OpportunitySummaryRow } from "@dracara/types";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useApiMutation } from "@/lib/use-api-mutation";
import Link from "next/link";
import { apiFetch, apiFetchOptional } from "@/lib/api";
import { ArrowRight, ChevronRight, Layers, Mail, MapPin, Sparkles, UserCircle } from "lucide-react";

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

export function LeadHero({ id }: { id: string }) {
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["lead", id],
    queryFn: () => apiFetch<{ lead: Record<string, unknown>; lead_intelligence: Record<string, unknown> | null }>(`/leads/${id}?include_related=true`),
  });

  const lead = data?.lead;

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

  const { data: opportunity = null } = useQuery({
    queryKey: ["opportunity-by-lead", id],
    queryFn: () =>
      apiFetchOptional<OpportunitySummaryRow>(`/opportunities/by-lead/${encodeURIComponent(id)}`),
    enabled: !!id,
  });

  const opportunityId = opportunity ? String(opportunity.id) : null;

  const convert = useApiMutation({
    errorTitle: "Could not convert lead",    mutationFn: () => apiFetch(`/leads/${id}/convert`, { method: "POST", body: "{}" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["lead", id] });
      qc.invalidateQueries({ queryKey: ["opportunity-by-lead", id] });
    },
  });

  if (isLoading || !data) {
    return <div className="h-36 rounded-xl bg-muted/80 animate-pulse" />;
  }

  const score = Number(lead?.priority_score ?? 0);
  const tier = scoreTier(score);
  const stageRaw = String(lead?.stage ?? "prospect");
  const pipelineLabel = humanizeUnderscore(stageRaw);
  const bucket = leadStageToCompanyStage(stageRaw);
  const projectType = humanizeUnderscore(String(lead?.project_type ?? "other"));
  const source = humanizeUnderscore(String(lead?.lead_source ?? "other"));
  const isOpportunity = Boolean(lead?.is_opportunity);

  const companyInitial = (company?.name ?? "?").trim().slice(0, 1).toUpperCase();

  const tierClass =
    tier === "Hot"
      ? "bg-orange-100 text-orange-800 dark:bg-orange-900/35 dark:text-orange-200"
      : tier === "Warm"
        ? "bg-amber-100 text-amber-800 dark:bg-amber-900/35 dark:text-amber-200"
        : "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200";

  return (
    <Card className="overflow-hidden rounded-xl border border-border/70 shadow-[0_1px_3px_rgba(15,23,42,0.06)]">
      <CardContent className="p-0">
        <div className="flex flex-col gap-4 p-4 sm:p-5 md:flex-row md:items-start">
          <div className="relative h-16 w-16 shrink-0 overflow-hidden rounded-xl border border-border/60 bg-gradient-to-br from-teal-50 to-teal-100/80 dark:from-teal-950/50 dark:to-teal-900/30">
            {company?.logo_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={company.logo_url} alt="" className="h-full w-full object-cover" />
            ) : (
              <div className="flex h-full w-full items-center justify-center text-2xl font-bold text-teal-800 dark:text-teal-200">
                {companyInitial}
              </div>
            )}
          </div>
          <div className="min-w-0 flex-1 space-y-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-[10px] font-bold uppercase tracking-widest text-[#0B7FB3]">Project Lead</p>
                <div className="mt-0.5 flex flex-wrap items-center gap-2">
                  <h1 className="text-xl font-bold tracking-tight text-[#0A1128] dark:text-foreground sm:text-2xl">
                    {company?.name ?? "Unknown company"}
                  </h1>
                </div>
                <div className="mt-1 flex flex-col gap-2 text-sm text-muted-foreground sm:flex-row sm:flex-wrap sm:items-center sm:gap-x-4 sm:gap-y-1">
                  <span className="inline-flex items-center gap-1.5">
                    <UserCircle className="h-4 w-4 shrink-0 opacity-70" />
                    <span className="text-foreground">{contact?.full_name ?? "No primary contact"}</span>
                    {contact?.email ? (
                      <a href={`mailto:${contact.email}`} className="inline-flex items-center gap-1 text-[#0B7FB3] hover:underline">
                        <Mail className="h-3.5 w-3.5" />
                        {contact.email}
                      </a>
                    ) : null}
                  </span>
                  {company?.location ? (
                    <span className="inline-flex items-center gap-1.5">
                      <MapPin className="h-4 w-4 shrink-0 opacity-70" />
                      {company.location}
                    </span>
                  ) : null}
                  <span className="inline-flex items-center gap-1.5">
                    <Layers className="h-4 w-4 shrink-0 opacity-70" />
                    <span className="text-foreground">Stage:</span> {pipelineLabel}
                  </span>
                </div>
              </div>
              
              <div className="flex flex-col items-end gap-1 text-right">
                <div className="flex flex-wrap items-center justify-end gap-2">
                  <Badge variant="outline" className="font-semibold text-foreground bg-muted/20 border-border/70">{projectType}</Badge>
                  <Badge variant="outline" className="font-normal">{source}</Badge>
                  <Badge className={`font-medium ${STAGE_VARIANTS[bucket]}`}>{bucket}</Badge>
                  <Badge className={`font-semibold ${tierClass}`}>{tier} · {score}</Badge>
                </div>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2 border-t border-border/50 pt-3">
              <Button variant="outline" size="sm" className="h-9 rounded-md border-border/70 text-xs font-medium" asChild>
                <Link href={`/leads/${id}/timeline`}>
                  Full timeline
                  <ArrowRight className="ml-1 h-3.5 w-3.5" />
                </Link>
              </Button>
              {isOpportunity && opportunityId ? (
                <Button size="sm" className="ml-auto h-9 gap-1.5 bg-[#0A1128] text-xs font-semibold text-white hover:bg-[#1a2a53] shadow-sm" asChild>
                  <Link href={`/opportunities/${opportunityId}`}>
                    Open opportunity
                    <ChevronRight className="h-4 w-4" />
                  </Link>
                </Button>
              ) : (
                <Button
                  size="sm"
                  className="ml-auto h-9 gap-1.5 bg-[#0A1128] text-xs font-semibold text-white hover:bg-[#1a2a53] shadow-sm"
                  disabled={convert.isPending}
                  onClick={() => convert.mutate()}
                >
                  <Sparkles className="h-3.5 w-3.5" />
                  {convert.isPending ? "Converting…" : "Activate as opportunity"}
                </Button>
              )}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
