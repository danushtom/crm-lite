import type { BillingOverview } from "@dracara/types";
import { describe, expect, it } from "vitest";
import { planLabel, statusLabel } from "@/components/billing/plan-labels";

const base: BillingOverview = {
  plan: "trial",
  status: "trialing",
  access: "trial",
  features: ["ai", "voice_agents"],
  trial_ends_at: null,
  trial_days_left: 6,
  current_period_end: null,
  cancel_at_period_end: false,
  seats: null,
  seat_limit: 5,
  seats_used: 2,
  has_subscription: false,
  can_manage: true,
  configured: true,
  plans: [
    { id: "starter", name: "Starter", price_per_seat_usd: 19, features: [], description: "", available: true },
    { id: "growth", name: "Growth", price_per_seat_usd: 49, features: ["ai"], description: "", available: true },
  ],
};

describe("planLabel", () => {
  it("shows the trial countdown", () => {
    expect(planLabel(base)).toBe("Free trial · 6d left");
  });

  it("names the paid plan", () => {
    expect(planLabel({ ...base, access: "paid", plan: "growth", status: "active" })).toBe("Growth");
  });

  it("says read-only once access has lapsed, whatever the plan", () => {
    expect(planLabel({ ...base, access: "read_only", plan: "growth", status: "expired" })).toBe("Read-only");
  });
});

it("labels unknown provider statuses verbatim rather than hiding them", () => {
  expect(statusLabel("past_due")).toMatch(/failed/i);
  expect(statusLabel("something_new")).toBe("something_new");
});
