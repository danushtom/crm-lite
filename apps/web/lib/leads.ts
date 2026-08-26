import type { LeadOpportunityRow, LeadStage, LeadWithOpportunities } from "@dracara/types";

/**
 * Reading a lead's pipeline position.
 *
 * Leads and opportunities used to duplicate stage, value, probability and score between them,
 * kept in step by a database trigger. They no longer do: a lead is a qualification record and
 * each pursuit against it owns its own commercials. A lead can therefore have several
 * pursuits over time — the build, then the retainer — of which at most one is active.
 *
 * These helpers are the single place that decides which pursuit represents a lead "right
 * now", so every screen answers that question the same way.
 */

/** The pursuit a lead should be judged by: the active one, else the most recent. */
export function primaryPursuit(lead: LeadWithOpportunities): LeadOpportunityRow | null {
  const pursuits = lead.opportunities ?? [];
  if (pursuits.length === 0) return null;
  return pursuits.find((o) => o.status === "active") ?? pursuits[0];
}

/** Current pipeline stage, or null for a lead with no pursuit yet. */
export function leadStage(lead: LeadWithOpportunities): LeadStage | null {
  return primaryPursuit(lead)?.stage ?? null;
}

/** Value of the pursuit in play. Not summed across pursuits: they may differ in currency. */
export function leadValue(lead: LeadWithOpportunities): number {
  const value = primaryPursuit(lead)?.quoted_value;
  return value == null ? 0 : Number(value);
}

export function leadCurrency(lead: LeadWithOpportunities): string {
  return primaryPursuit(lead)?.currency ?? "INR";
}

export function leadScore(lead: LeadWithOpportunities): number {
  return primaryPursuit(lead)?.priority_score ?? 0;
}

export function leadProbability(lead: LeadWithOpportunities): number {
  return primaryPursuit(lead)?.deal_probability ?? 0;
}

/** True once a lead has a pursuit past the earliest stages. */
export function isQualified(lead: LeadWithOpportunities): boolean {
  const stage = leadStage(lead);
  return stage != null && stage !== "prospect" && stage !== "contacting";
}

/**
 * Total pipeline value across leads, grouped by currency.
 *
 * Deliberately not a single number: summing across currencies produces a figure that looks
 * authoritative and means nothing, which is exactly the bug the dashboard used to have.
 */
export function pipelineByCurrency(leads: LeadWithOpportunities[]): Record<string, number> {
  const totals: Record<string, number> = {};
  for (const lead of leads) {
    const pursuit = primaryPursuit(lead);
    if (!pursuit?.quoted_value) continue;
    totals[pursuit.currency] = (totals[pursuit.currency] ?? 0) + Number(pursuit.quoted_value);
  }
  return totals;
}

/** Convenience for the common single-currency case; returns 0 when currencies are mixed. */
export function singleCurrencyTotal(leads: LeadWithOpportunities[]): {
  total: number;
  currency: string;
  mixed: boolean;
} {
  const totals = pipelineByCurrency(leads);
  const currencies = Object.keys(totals);
  if (currencies.length === 1) {
    return { total: totals[currencies[0]], currency: currencies[0], mixed: false };
  }
  if (currencies.length === 0) return { total: 0, currency: "INR", mixed: false };
  return {
    total: Object.values(totals).reduce((a, b) => a + b, 0),
    currency: currencies[0],
    mixed: true,
  };
}
