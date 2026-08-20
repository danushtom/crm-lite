"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@dracara/ui";

const tabs = (id: string) =>
  [
    { href: `/leads/${id}`, label: "Overview", count: null },
    { href: `/leads/${id}/notes`, label: "Notes", count: 1 },
    { href: `/leads/${id}/conversations`, label: "Conversations", count: 0 },
    { href: `/leads/${id}/opportunities`, label: "Opportunities", count: 1 },
    { href: `/leads/${id}/timeline`, label: "Timeline", count: 1 },
    { href: `/leads/${id}/reminders`, label: "Reminders", count: 1 },
  ] as const;

const cardShell = "rounded-xl border border-border/70 bg-card shadow-[0_1px_3px_rgba(15,23,42,0.06)]";

export function LeadSubnav({ id }: { id: string }) {
  const pathname = usePathname();

  return (
    <div className={cn(cardShell, "p-2")}>
      <nav className="flex flex-wrap gap-1 rounded-lg bg-muted/70 p-1 dark:bg-muted/40" role="tablist">
        {tabs(id).map((t) => {
          const isOverview = t.href === `/leads/${id}`;
          const active = isOverview ? pathname === t.href : pathname === t.href || pathname.startsWith(`${t.href}/`);
          return (
            <Link
              key={t.href}
              href={t.href}
              className={cn(
                "rounded-md px-3 py-2 text-sm font-medium transition-all outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                active
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:bg-background/60 hover:text-foreground",
              )}
            >
              {t.label}
              {t.count !== null && (
                <span className="ml-1.5 rounded-full bg-muted-foreground/10 px-1.5 py-0.5 text-[10px] font-bold text-muted-foreground tabular-nums">
                  {t.count}
                </span>
              )}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
