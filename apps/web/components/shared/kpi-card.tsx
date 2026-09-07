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
  icon: Icon,
  className,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
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
        {hint ? <p className="mt-1 text-xs text-muted-foreground">{hint}</p> : null}
      </CardContent>
    </Card>
  );
}
