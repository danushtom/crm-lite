import type { BillingOverview, PlanFeature } from "@dracara/types";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

export const BILLING_QUERY_KEY = ["billing"] as const;

/** The organization's plan. Shared by the billing page, the plan banner and feature checks. */
export function useBilling() {
  return useQuery({
    queryKey: BILLING_QUERY_KEY,
    queryFn: () => apiFetch<BillingOverview>("/billing"),
    staleTime: 60_000,
  });
}

/** True while loading, so affordances do not flash away before the plan is known. */
export function useHasFeature(feature: PlanFeature): boolean {
  const { data } = useBilling();
  return data ? data.features.includes(feature) : true;
}

export const FEATURE_LABELS: Record<PlanFeature, string> = {
  ai: "AI assistant, call notes, proposal drafting, deal health & research",
  voice_agents: "AI voice agents with a document knowledge base",
};
