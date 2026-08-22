"use client";

import { usePathname } from "next/navigation";
import { ChevronDown, Download, Search, Share2 } from "lucide-react";
import { Button, Input } from "@dracara/ui";
import { useEffect, useState } from "react";
import { NotificationBell } from "@/components/layout/notification-bell";

const TITLE_MAP: { prefix: string; title: string }[] = [
  { prefix: "/dashboard", title: "Dashboard" },
  { prefix: "/opportunities", title: "Opportunities" },
  { prefix: "/pipeline", title: "Opportunities" },
  { prefix: "/companies", title: "Companies" },
  { prefix: "/contacts", title: "Contacts" },
  { prefix: "/follow-ups", title: "Follow-ups" },
  { prefix: "/calendar", title: "Calendar" },
  { prefix: "/agents", title: "Agents" },
  { prefix: "/reports", title: "Reports" },
  { prefix: "/settings", title: "Settings" },
  { prefix: "/leads", title: "Leads" },
];

function pageTitle(pathname: string): string {
  const hit = TITLE_MAP.find((t) => pathname === t.prefix || pathname.startsWith(t.prefix + "/"));
  return hit?.title ?? "Dracara";
}

export function AppTopBar() {
  const pathname = usePathname();
  const title = pageTitle(pathname);
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
            <div className="relative min-w-[180px] flex-1 md:min-w-[240px] lg:w-72 xl:w-80">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input placeholder="Search something…" className="h-9 rounded-lg border-border bg-muted/30 pl-9 shadow-inner" />
            </div>
            <Button variant="outline" size="sm" className="h-9 gap-1.5 rounded-lg">
              <Share2 className="h-3.5 w-3.5" />
              Share
            </Button>
            <Button variant="outline" size="sm" className="h-9 gap-1 rounded-lg px-2">
              Imports
              <ChevronDown className="h-4 w-4 opacity-60" />
            </Button>
            <Button
              size="sm"
              className="h-9 gap-1 rounded-lg bg-[#0A1128] px-3 text-white hover:bg-[#151f3d]"
            >
              <Download className="h-3.5 w-3.5" />
              Exports
            </Button>
          </div>
        </div>
      </div>
    </header>
  );
}
