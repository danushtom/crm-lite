"use client";

import { cn } from "@dracara/ui";
import { AlertTriangle, Clock } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useBilling } from "@/lib/billing";

/**
 * One line above every page when the plan needs attention: trial countdown, read-only mode,
 * a failing card. Silent for a paid plan in good standing, and on the billing page itself.
 */
export function PlanBanner() {
  const pathname = usePathname();
  const { data } = useBilling();
  if (!data || pathname.startsWith("/settings/billing")) return null;

  const cta = data.can_manage ? (
    <Link href="/settings/billing" className="shrink-0 font-semibold underline underline-offset-4">
      {data.access === "read_only" ? "Choose a plan" : "View plans"}
    </Link>
  ) : null;

  let tone: "info" | "warn" | "danger";
  let message: string;
  if (data.access === "read_only") {
    tone = "danger";
    message = data.can_manage
      ? "Your free trial has ended, so this workspace is read-only. Choose a plan to keep working."
      : "This workspace is read-only until an admin chooses a plan.";
  } else if (data.status === "past_due") {
    tone = "warn";
    message = "Your last payment failed. Update your payment method to avoid losing access.";
  } else if (data.access === "trial") {
    tone = data.trial_days_left <= 3 ? "warn" : "info";
    message = `${data.trial_days_left} day${data.trial_days_left === 1 ? "" : "s"} left in your free trial.`;
  } else {
    return null;
  }

  const Icon = tone === "info" ? Clock : AlertTriangle;
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      className={cn(
        "flex items-center gap-2 border-b px-4 py-2 text-sm lg:px-6",
        tone === "info" && "border-border bg-muted/60 text-foreground",
        tone === "warn" && "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/40 dark:text-amber-200",
        tone === "danger" && "border-red-200 bg-red-50 text-red-900 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-200"
      )}
    >
      <Icon className="h-4 w-4 shrink-0" aria-hidden />
      <span className="min-w-0 flex-1">{message}</span>
      {cta}
    </div>
  );
}
