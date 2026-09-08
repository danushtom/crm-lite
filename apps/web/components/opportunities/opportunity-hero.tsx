"use client";

import { Badge, Card, CardContent } from "@dracara/ui";
import { scoreTier, type CompanyRow, type ContactRow, type LeadRow, type OpportunityRow } from "@dracara/types";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import { Layers, Mail, MapPin, UserCircle } from "lucide-react";

function humanizeUnderscore(s: string): string {
  return s
    .split("_")
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export function OpportunityHero({ id }: { id: string }) {
  const { data: opp, isLoading: oppLoading } = useQuery({
    queryKey: ["opportunity", id],
    queryFn: () => apiFetch<OpportunityRow>(`/opportunities/${id}`),
  });

  const { data: lead } = useQuery({
    queryKey: ["lead", opp?.lead_id],
    queryFn: () => apiFetch<{ lead: LeadRow }>(`/leads/${opp?.lead_id}`),
    enabled: !!opp?.lead_id,
  });

  const { data: company } = useQuery({
    queryKey: ["company", lead?.lead.company_id],
    queryFn: () => apiFetch<CompanyRow>(`/companies/${lead?.lead.company_id}`),
    enabled: !!lead?.lead.company_id,
  });

  const { data: contact } = useQuery({
    queryKey: ["contact", lead?.lead.primary_contact_id],
    queryFn: () => apiFetch<ContactRow>(`/contacts/${lead?.lead.primary_contact_id}`),
    enabled: !!lead?.lead.primary_contact_id,
  });

  if (oppLoading || !opp) {
    return <div className="h-36 rounded-xl bg-muted/80 animate-pulse" />;
  }

  const score = Number(opp.priority_score ?? 0);
  const tier = scoreTier(score);
  const stageLabel = humanizeUnderscore(opp.stage);
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
          <div className="relative h-16 w-16 shrink-0 overflow-hidden rounded-xl border border-border/60 bg-gradient-to-br from-[#0B7FB3]/10 to-[#0B7FB3]/15 dark:from-[#0B7FB3]/25 dark:to-[#0B7FB3]/25">
            {company?.logo_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={company.logo_url} alt="" className="h-full w-full object-cover" />
            ) : (
              <div className="flex h-full w-full items-center justify-center text-2xl font-bold text-[#096892] dark:text-[#4FB8E3]">
                {companyInitial}
              </div>
            )}
          </div>
          <div className="min-w-0 flex-1 space-y-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-[10px] font-bold uppercase tracking-widest text-[#0B7FB3]">Opportunity</p>
                <div className="mt-0.5 flex flex-wrap items-center gap-2">
                  <h1 className="text-xl font-bold tracking-tight text-[#0A1128] dark:text-foreground sm:text-2xl">
                    {opp.title}
                  </h1>
                </div>
                <div className="mt-1 flex flex-col gap-2 text-sm text-muted-foreground sm:flex-row sm:flex-wrap sm:items-center sm:gap-x-4 sm:gap-y-1">
                  <span className="inline-flex items-center gap-1.5 font-medium text-foreground">
                    {company?.name ?? "—"}
                  </span>
                  <span className="hidden h-1 w-1 rounded-full bg-muted-foreground/30 sm:block" />
                  <span className="inline-flex items-center gap-1.5">
                    <UserCircle className="h-4 w-4 shrink-0 opacity-70" />
                    {contact?.full_name ?? "No contact"}
                  </span>
                  {company?.location && (
                    <>
                      <span className="hidden h-1 w-1 rounded-full bg-muted-foreground/30 sm:block" />
                      <span className="inline-flex items-center gap-1.5">
                        <MapPin className="h-4 w-4 shrink-0 opacity-70" />
                        {company.location}
                      </span>
                    </>
                  )}
                </div>
              </div>
              
              <div className="flex flex-col items-end gap-1 text-right">
                <div className="flex flex-wrap items-center justify-end gap-2">
                  <Badge className="bg-[#0B7FB3]/15 text-[#096892] dark:bg-[#0B7FB3]/30 dark:text-[#4FB8E3] font-semibold">
                    {stageLabel}
                  </Badge>
                  <Badge className={`font-semibold ${tierClass}`}>{tier} · {score}</Badge>
                </div>
              </div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
