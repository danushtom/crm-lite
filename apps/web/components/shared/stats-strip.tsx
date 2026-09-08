"use client";

import { Badge, Button, Card, CardContent, cn } from "@dracara/ui";
import { ChevronDown } from "lucide-react";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";

/** Shared key so every list page's stats strip collapses and expands together. */
const STATS_COLLAPSED_KEY = "crm-stats-collapsed";

export type StatTile = {
  label: string;
  value: string;
  hint?: ReactNode;
  /** Highlights the leading tile. */
  emphasis?: boolean;
  /**
   * Bar colour for this tile, as a bg-* class. Pass it where the tile means something with its
   * own identity -- an acquisition channel, say, which should read the same colour on every
   * page. Omit it and tiles fall back to position-based colours.
   */
  tone?: string;
};

/** Bar colours for the tile row, in order. */
const BAR_COLORS = ["bg-[#18395B]", "bg-[#2FA8E8]", "bg-[#45B2F0]", "bg-[#E2E8F0]"];

/**
 * The collapsible headline + tile row that sits above a list table.
 *
 * The collapse state persists to localStorage, which the Contacts page did and the Companies
 * copy of it did not -- its Collapse button had no handler at all.
 */
export function StatsStrip({
  headline,
  headlineSuffix,
  headlineLabel,
  badge,
  emphasisLabel = "Most effective",
  tiles,
}: {
  headline: string;
  /** Smaller text after the headline, e.g. "across 14 leads". */
  headlineSuffix?: string;
  headlineLabel?: string;
  badge?: { text: string; tone: "positive" | "negative" };
  /** Badge shown on the emphasised tile -- "Highest value", "Largest group". */
  emphasisLabel?: string;
  tiles: StatTile[];
}) {
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    try {
      setCollapsed(localStorage.getItem(STATS_COLLAPSED_KEY) === "true");
    } catch {
      // Private mode or blocked storage: default to expanded.
    }
  }, []);

  const toggle = () => {
    setCollapsed((previous) => {
      const next = !previous;
      try {
        localStorage.setItem(STATS_COLLAPSED_KEY, String(next));
      } catch {
        // Non-fatal: the toggle still works for this session.
      }
      return next;
    });
  };

  return (
    <Card className="overflow-hidden">
      <CardContent className="space-y-4 pt-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="flex items-center gap-2">
              {headlineLabel ? (
                <p className="text-sm font-semibold text-foreground">{headlineLabel}</p>
              ) : null}
              {badge ? (
                <Badge
                  className={cn(
                    "h-5 rounded-md px-1.5 text-[10px] font-semibold",
                    badge.tone === "positive"
                      ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300"
                      : "bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300"
                  )}
                >
                  {badge.text}
                </Badge>
              ) : null}
            </div>
            <p className="mt-2 text-[38px] font-semibold leading-none tracking-tight text-[#0A1128] dark:text-foreground">
              {headline}
              {headlineSuffix ? (
                <span className="ml-2 text-sm font-medium text-muted-foreground">
                  {headlineSuffix}
                </span>
              ) : null}
            </p>
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={toggle}
            aria-expanded={!collapsed}
            className="h-8 gap-1 rounded-md border-border/70 px-3 text-xs font-semibold"
          >
            {collapsed ? "Expand" : "Collapse"}
            <ChevronDown
              className={cn(
                "h-3.5 w-3.5 text-muted-foreground transition-transform",
                collapsed && "rotate-180"
              )}
            />
          </Button>
        </div>

        {collapsed || tiles.length === 0 ? null : (
          <div className="grid gap-2 md:grid-cols-4">
            {tiles.map((tile, index) => (
              <div
                key={tile.label}
                className="rounded-sm border border-border/70 bg-white px-3 pb-2 pt-3 dark:bg-card"
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="text-[22px] font-semibold text-[#0A1128] dark:text-foreground">
                    {tile.value}
                  </p>
                  {tile.emphasis ? (
                    <Badge className="h-5 rounded-md bg-emerald-100 px-2 text-[10px] font-semibold text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300">
                      {emphasisLabel}
                    </Badge>
                  ) : null}
                </div>
                {tile.hint ? (
                  <p className="mt-1 text-xs text-muted-foreground">{tile.hint}</p>
                ) : null}
                <div
                  className={cn(
                    "mt-2 h-1 w-full rounded",
                    tile.tone ?? BAR_COLORS[index % BAR_COLORS.length]
                  )}
                />
                <p className="mt-2 flex items-center gap-1.5 text-sm font-medium text-foreground">
                  <span
                    className={cn(
                      "inline-block h-2 w-2 rounded-sm",
                      tile.tone ?? BAR_COLORS[index % BAR_COLORS.length]
                    )}
                  />
                  {tile.label}
                </p>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
