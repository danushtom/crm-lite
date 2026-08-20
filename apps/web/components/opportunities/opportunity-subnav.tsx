"use client";

import { cn } from "@dracara/ui";
import Link from "next/link";
import { usePathname } from "next/navigation";

const tabs = (id: string) =>
  [
    { href: `/opportunities/${id}`, label: "Overview", count: null },
    { href: `/opportunities/${id}/proposals`, label: "Proposals", count: 1 },
    { href: `/opportunities/${id}/notes`, label: "Notes", count: null },
    { href: `/opportunities/${id}/timeline`, label: "Timeline", count: null },
    { href: `/opportunities/${id}/reminders`, label: "Reminders", count: null },
  ] as const;

export function OpportunitySubnav({ id }: { id: string }) {
  const pathname = usePathname();

  return (
    <div className="flex items-center border-b border-border/50 px-2 overflow-x-auto no-scrollbar">
      {tabs(id).map((tab) => {
        const isActive = pathname === tab.href;
        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={cn(
              "relative flex items-center gap-2 px-4 py-3 text-sm font-medium transition-colors hover:text-foreground",
              isActive ? "text-indigo-600" : "text-muted-foreground"
            )}
          >
            {tab.label}
            {tab.count !== null && (
              <span
                className={cn(
                  "flex h-4.5 min-w-[1.125rem] items-center justify-center rounded-full px-1 text-[10px] font-bold ring-1 ring-inset",
                  isActive
                    ? "bg-indigo-50 text-indigo-700 ring-indigo-200"
                    : "bg-muted/50 text-muted-foreground ring-border"
                )}
              >
                {tab.count}
              </span>
            )}
            {isActive && (
              <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-indigo-600" />
            )}
          </Link>
        );
      })}
    </div>
  );
}
