"use client";

import { Card, CardContent, cn, fieldLabel } from "@dracara/ui";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

/**
 * One KPI tile. Replaces five separate implementations (dashboard, contact detail, lead
 * detail, opportunity detail, reports) that disagreed on label size, value weight, whether
 * numbers were tabular, and whether an icon appeared at all.
 */
export function KpiCard({
  label,
  value,
  hint,
  delta,
  icon: Icon,
  className,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  /**
   * Change against the prior period. Pass `null`/omit when there is nothing real to compare
   * against -- the dashboard used to hardcode "+24 vs last week" on every tile regardless of
   * the data, which is worse than showing no delta at all.
   */
  delta?: { label: string; positive: boolean } | null;
  icon?: LucideIcon;
  className?: string;
}) {
  return (
    <Card className={cn("shadow-none", className)}>
      <CardContent className="p-4">
        <div className="flex items-center justify-between gap-2">
          <p className={fieldLabel}>{label}</p>
          {Icon ? <Icon className="h-4 w-4 text-muted-foreground" /> : null}
        </div>
        <p className="mt-2 text-2xl font-semibold tabular-nums text-[#0A1128] dark:text-foreground">
          {value}
        </p>
        {delta ? (
          <span
            className={cn(
              "mt-2 inline-flex rounded-full px-2 py-0.5 text-xs font-semibold",
              delta.positive
                ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
                : "bg-rose-50 text-rose-700 dark:bg-rose-950 dark:text-rose-300"
            )}
          >
            {delta.label}
          </span>
        ) : null}
        {hint ? <p className="mt-1 text-xs text-muted-foreground">{hint}</p> : null}
      </CardContent>
    </Card>
  );
}
