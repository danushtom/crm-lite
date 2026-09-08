"use client";

import { cn } from "@dracara/ui";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ProposalRow } from "@dracara/types";
import { apiList } from "@/lib/api";

/**
 * Sub-route navigation for an opportunity.
 *
 * Two things were wrong with this. It used an underline-tab treatment found nowhere else in
 * the app -- the contact detail page, which is the design reference, uses a segmented pill
 * group -- so the two detail pages read as different products. And the Proposals badge was the
 * literal `1`, shown whether the opportunity had none, one or nine.
 */
export function OpportunitySubnav({ id }: { id: string }) {
  const pathname = usePathname();

  const { data: proposals } = useQuery({
    queryKey: ["opportunities", id, "proposals"],
    queryFn: () => apiList<ProposalRow>(`/opportunities/${id}/proposals`),
  });

  const tabs: { href: string; label: string; count: number | null }[] = [
    { href: `/opportunities/${id}`, label: "Overview", count: null },
    // Undefined while loading, so the badge stays absent rather than flashing a zero.
    { href: `/opportunities/${id}/proposals`, label: "Proposals", count: proposals?.length ?? null },
    { href: `/opportunities/${id}/notes`, label: "Notes", count: null },
    { href: `/opportunities/${id}/timeline`, label: "Timeline", count: null },
    { href: `/opportunities/${id}/reminders`, label: "Reminders", count: null },
  ];

  return (
    <div
      role="tablist"
      aria-label="Opportunity"
      className="flex flex-wrap gap-1 rounded-lg bg-muted/70 p-1 dark:bg-muted/40"
    >
      {tabs.map((tab) => {
        const isActive = pathname === tab.href;
        return (
          <Link
            key={tab.href}
            href={tab.href}
            role="tab"
            aria-selected={isActive}
            className={cn(
              "rounded-md px-3 py-2 text-sm font-medium outline-none transition-all focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
              isActive
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:bg-background/60 hover:text-foreground"
            )}
          >
            {tab.label}
            {tab.count != null ? (
              <span className="ml-1 tabular-nums text-muted-foreground">({tab.count})</span>
            ) : null}
          </Link>
        );
      })}
    </div>
  );
}
