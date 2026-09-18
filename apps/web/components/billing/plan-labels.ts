import type { BillingOverview } from "@dracara/types";

const STATUS_LABELS: Record<string, string> = {
  trialing: "Free trial",
  active: "Active",
  past_due: "Payment failed — retrying",
  on_hold: "On hold",
  paused: "Paused",
  cancelled: "Cancelled",
  failed: "Payment failed",
  expired: "Expired",
  pending: "Awaiting payment",
};

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

/** "Growth", "Free trial", or "Read-only" -- what the organization is on right now. */
export function planLabel(billing: BillingOverview): string {
  if (billing.access === "read_only") return "Read-only";
  if (billing.access === "trial") return `Free trial · ${billing.trial_days_left}d left`;
  return billing.plans.find((p) => p.id === billing.plan)?.name ?? billing.plan;
}
