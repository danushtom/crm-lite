"use client";

import type { BillingOverview, PlanId, PlanInfo } from "@dracara/types";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Skeleton,
  cn,
} from "@dracara/ui";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, ExternalLink, Loader2, Minus, Plus } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { toast } from "sonner";
import { apiFetch } from "@/lib/api";
import { BILLING_QUERY_KEY, FEATURE_LABELS, useBilling } from "@/lib/billing";
import { useApiMutation } from "@/lib/use-api-mutation";
import { planLabel, statusLabel } from "@/components/billing/plan-labels";

const formatDate = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "—";

export default function BillingPage() {
  return (
    <Suspense fallback={<Skeleton className="h-64 w-full max-w-5xl" />}>
      <BillingInner />
    </Suspense>
  );
}

function BillingInner() {
  const qc = useQueryClient();
  const params = useSearchParams();
  const { data, isLoading, isError } = useBilling();
  const returnedFromCheckout = params.get("checkout") === "success";

  // The subscription is recorded by Dodo's webhook, which can land a few seconds after the
  // customer is redirected back here. Poll briefly so the page catches up on its own.
  const [awaitingWebhook, setAwaitingWebhook] = useState(returnedFromCheckout);
  useEffect(() => {
    if (!awaitingWebhook) return;
    if (data?.has_subscription) {
      setAwaitingWebhook(false);
      toast.success("You're subscribed. Thank you!");
      return;
    }
    let tries = 0;
    const timer = window.setInterval(() => {
      tries += 1;
      qc.invalidateQueries({ queryKey: BILLING_QUERY_KEY });
      if (tries >= 10) setAwaitingWebhook(false);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [awaitingWebhook, data?.has_subscription, qc]);

  return (
    <div className="max-w-5xl space-y-6">
      <div className="space-y-1">
        <Link href="/settings" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-3.5 w-3.5" /> Settings
        </Link>
        <h1 className="text-xl font-semibold tracking-tight">Plan &amp; billing</h1>
        <p className="text-sm text-muted-foreground">
          Priced per active user, billed monthly. Payments are processed by Dodo Payments, which
          also handles sales tax and invoices.
        </p>
      </div>

      {isLoading ? (
        <Skeleton className="h-40 w-full" />
      ) : isError || !data ? (
        <Card>
          <CardContent className="py-6 text-sm text-destructive">Could not load billing details.</CardContent>
        </Card>
      ) : (
        <>
          {awaitingWebhook ? (
            <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/50 px-4 py-3 text-sm">
              <Loader2 className="h-4 w-4 animate-spin" /> Confirming your payment…
            </div>
          ) : null}
          <CurrentPlanCard billing={data} />
          {!data.configured ? (
            <Card>
              <CardContent className="py-5 text-sm text-muted-foreground">
                Billing is not configured on this server yet (DODO_PAYMENTS_API_KEY and
                DODO_PAYMENTS_WEBHOOK_SECRET on the API).
              </CardContent>
            </Card>
          ) : (
            <PlanPicker billing={data} />
          )}
        </>
      )}
    </div>
  );
}

function CurrentPlanCard({ billing }: { billing: BillingOverview }) {
  const openPortal = useApiMutation({
    mutationFn: () => apiFetch<{ url: string }>("/billing/portal", { method: "POST" }),
    onSuccess: ({ url }) => {
      window.location.href = url;
    },
    errorTitle: "Could not open the billing portal",
  });

  const seatPct = billing.seat_limit ? Math.min(100, (billing.seats_used / billing.seat_limit) * 100) : 100;

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <CardDescription>Current plan</CardDescription>
          <CardTitle className="flex items-center gap-2 text-lg">
            {planLabel(billing)}
            <Badge variant={billing.access === "read_only" ? "destructive" : "secondary"}>
              {statusLabel(billing.status)}
            </Badge>
          </CardTitle>
        </div>
        {billing.can_manage && billing.has_subscription ? (
          <Button variant="outline" size="sm" onClick={() => openPortal.mutate()} disabled={openPortal.isPending}>
            {openPortal.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <ExternalLink className="h-4 w-4" />}
            Invoices &amp; payment method
          </Button>
        ) : null}
      </CardHeader>
      <CardContent className="grid gap-6 sm:grid-cols-3">
        <div className="space-y-2">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Seats</p>
          <p className="text-sm">
            <span className="text-lg font-semibold tabular-nums">{billing.seats_used}</span>
            <span className="text-muted-foreground"> of {billing.seat_limit} in use</span>
          </p>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
            <div
              className={cn("h-full rounded-full", seatPct >= 100 ? "bg-amber-500" : "bg-[hsl(var(--primary))]")}
              style={{ width: `${seatPct}%` }}
            />
          </div>
        </div>
        <div className="space-y-2">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {billing.access === "trial" ? "Trial ends" : billing.cancel_at_period_end ? "Access ends" : "Renews"}
          </p>
          <p className="text-sm font-medium">
            {billing.access === "trial"
              ? formatDate(billing.trial_ends_at)
              : billing.access === "paid"
                ? formatDate(billing.current_period_end)
                : "—"}
          </p>
        </div>
        <div className="space-y-2">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Included</p>
          <ul className="space-y-1 text-sm">
            <li className="flex gap-1.5">
              <Check className="mt-0.5 h-3.5 w-3.5 shrink-0" /> Core CRM
            </li>
            {billing.features.map((f) => (
              <li key={f} className="flex gap-1.5">
                <Check className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {FEATURE_LABELS[f]}
              </li>
            ))}
          </ul>
        </div>
      </CardContent>
    </Card>
  );
}

function PlanPicker({ billing }: { billing: BillingOverview }) {
  const qc = useQueryClient();
  const minSeats = Math.max(1, billing.seats_used);
  const [seats, setSeats] = useState(() => Math.max(minSeats, billing.seats ?? minSeats));

  const checkout = useApiMutation({
    mutationFn: (plan: PlanId) =>
      apiFetch<{ checkout_url: string }>("/billing/checkout", {
        method: "POST",
        body: JSON.stringify({ plan, seats }),
      }),
    onSuccess: ({ checkout_url }) => {
      window.location.href = checkout_url;
    },
    errorTitle: "Could not start checkout",
  });

  const changePlan = useApiMutation({
    mutationFn: (plan: PlanId) =>
      apiFetch<{ accepted: boolean }>("/billing/change-plan", {
        method: "POST",
        body: JSON.stringify({ plan, seats }),
      }),
    onSuccess: () => {
      toast.success("Plan change requested", { description: "Your plan updates here within a few seconds." });
      window.setTimeout(() => qc.invalidateQueries({ queryKey: BILLING_QUERY_KEY }), 4000);
    },
    errorTitle: "Could not change plan",
  });

  const pending = checkout.isPending || changePlan.isPending;
  const isCurrent = (plan: PlanInfo) =>
    billing.has_subscription && billing.plan === plan.id && billing.seats === seats;

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-base font-semibold">{billing.has_subscription ? "Change plan or seats" : "Choose a plan"}</h2>
          <p className="text-sm text-muted-foreground">
            {billing.has_subscription
              ? "Changes are prorated immediately against your saved payment method."
              : billing.access === "trial"
                ? `Subscribe now and you still keep the ${billing.trial_days_left} trial day${billing.trial_days_left === 1 ? "" : "s"} you have left.`
                : "Pick a plan to unlock your workspace again. Your data is all still here."}
          </p>
        </div>
        {billing.can_manage ? (
          <div className="flex items-center gap-2">
            <label htmlFor="seats" className="text-sm font-medium">
              Seats
            </label>
            <div className="flex items-center rounded-lg border border-input">
              <Button
                variant="ghost"
                size="icon"
                className="h-9 w-9 rounded-r-none"
                onClick={() => setSeats((s) => Math.max(minSeats, s - 1))}
                disabled={seats <= minSeats}
                aria-label="Fewer seats"
              >
                <Minus className="h-4 w-4" />
              </Button>
              <Input
                id="seats"
                type="number"
                inputMode="numeric"
                min={minSeats}
                max={1000}
                value={seats}
                onChange={(e) => {
                  const n = Number.parseInt(e.target.value, 10);
                  if (Number.isFinite(n)) setSeats(Math.min(1000, Math.max(1, n)));
                }}
                onBlur={() => setSeats((s) => Math.max(minSeats, s))}
                className="h-9 w-16 rounded-none border-0 text-center tabular-nums"
              />
              <Button
                variant="ghost"
                size="icon"
                className="h-9 w-9 rounded-l-none"
                onClick={() => setSeats((s) => Math.min(1000, s + 1))}
                aria-label="More seats"
              >
                <Plus className="h-4 w-4" />
              </Button>
            </div>
          </div>
        ) : null}
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {billing.plans.map((plan) => {
          const current = isCurrent(plan);
          const onPlan = billing.has_subscription && billing.plan === plan.id;
          return (
            <Card key={plan.id} className={cn("flex flex-col", onPlan && "border-[hsl(var(--primary))] ring-1 ring-[hsl(var(--primary))]")}>
              <CardHeader className="space-y-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">{plan.name}</CardTitle>
                  {onPlan ? <Badge>Current</Badge> : plan.id === "growth" ? <Badge variant="secondary">Popular</Badge> : null}
                </div>
                <p>
                  <span className="text-2xl font-semibold tabular-nums">${plan.price_per_seat_usd}</span>
                  <span className="text-sm text-muted-foreground"> / seat / month</span>
                </p>
                <CardDescription>{plan.description}</CardDescription>
              </CardHeader>
              <CardContent className="mt-auto space-y-3">
                <p className="text-sm text-muted-foreground">
                  {seats} seat{seats === 1 ? "" : "s"} ·{" "}
                  <span className="font-medium text-foreground tabular-nums">
                    ${(plan.price_per_seat_usd * seats).toLocaleString()}
                  </span>{" "}
                  / month
                </p>
                {billing.can_manage ? (
                  <Button
                    className="w-full"
                    variant={onPlan ? "outline" : "default"}
                    disabled={pending || current || !plan.available}
                    onClick={() => (billing.has_subscription ? changePlan : checkout).mutate(plan.id)}
                  >
                    {!plan.available
                      ? "Unavailable"
                      : current
                        ? "Current plan"
                        : billing.has_subscription
                          ? onPlan
                            ? "Update seats"
                            : `Switch to ${plan.name}`
                          : `Choose ${plan.name}`}
                  </Button>
                ) : null}
              </CardContent>
            </Card>
          );
        })}
      </div>
      {!billing.can_manage ? (
        <p className="text-sm text-muted-foreground">Only a workspace admin can change the plan.</p>
      ) : null}
    </section>
  );
}
