"use client";

import { usePathname, useRouter } from "next/navigation";
import { Search } from "lucide-react";
import { Button, Input } from "@dracara/ui";
import { useEffect, useState } from "react";
import { NotificationBell } from "@/components/layout/notification-bell";
import { ExportButton } from "@/components/layout/export-button";
import { ImportButton } from "@/components/layout/import-button";

const TITLE_MAP: { prefix: string; title: string }[] = [
  { prefix: "/dashboard", title: "Dashboard" },
  { prefix: "/opportunities", title: "Opportunities" },
  { prefix: "/pipeline", title: "Opportunities" },
  { prefix: "/companies", title: "Companies" },
  { prefix: "/contacts", title: "Contacts" },
  { prefix: "/follow-ups", title: "Follow-ups" },
  { prefix: "/calendar", title: "Calendar" },
  { prefix: "/voice-agents", title: "AI Agents" },
  { prefix: "/agents", title: "User management" },
  { prefix: "/reports", title: "Reports" },
  { prefix: "/settings", title: "Settings" },
  { prefix: "/import", title: "Import" },
  { prefix: "/recently-deleted", title: "Recently deleted" },
  { prefix: "/leads", title: "Leads" },
];

/** List pages that read `?q=` to seed their own search box. */
const SEARCHABLE_LISTS = ["/contacts", "/leads", "/companies"];

function pageTitle(pathname: string): string {
  const hit = TITLE_MAP.find((t) => pathname === t.prefix || pathname.startsWith(t.prefix + "/"));
  return hit?.title ?? "Dracara";
}

/**
 * Where a global search lands. There is no cross-entity search endpoint, so rather than
 * pretend otherwise this searches the list you are already on, and falls back to Contacts.
 */
function searchTarget(pathname: string): string {
  return SEARCHABLE_LISTS.find((p) => pathname.startsWith(p)) ?? "/contacts";
}

export function AppTopBar() {
  const pathname = usePathname();
  const router = useRouter();
  const title = pageTitle(pathname);
  const [query, setQuery] = useState("");
  const [updatedLabel, setUpdatedLabel] = useState("—");

  useEffect(() => {
    const now = new Date();
    setUpdatedLabel(now.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }));
  }, []);

  return (
    <header className="sticky top-0 z-20 border-b border-border/80 bg-card/90 backdrop-blur-md">
      <div className="flex flex-col gap-3 px-4 py-3 lg:flex-row lg:items-center lg:justify-between lg:px-6 lg:py-3.5">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-[hsl(var(--foreground))] lg:text-[1.75rem]">{title}</h1>
        </div>

        <div className="flex flex-wrap items-center gap-2 lg:flex-col lg:items-end xl:flex-row xl:items-center">
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground lg:order-last xl:order-none">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500" aria-hidden />
            Last updated <span suppressHydrationWarning>{updatedLabel}</span>
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <NotificationBell />
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const term = query.trim();
                if (!term) return;
                router.push(`${searchTarget(pathname)}?q=${encodeURIComponent(term)}`);
              }}
              className="relative min-w-[180px] flex-1 md:min-w-[240px] lg:w-72 xl:w-80"
            >
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search contacts, leads, companies…"
                aria-label="Search"
                className="h-9 rounded-lg border-border bg-muted/30 pl-9 shadow-inner"
              />
            </form>
            <ImportButton />
            <ExportButton />
          </div>
        </div>
      </div>
    </header>
  );
}
