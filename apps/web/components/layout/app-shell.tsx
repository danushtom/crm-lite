"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  KanbanSquare,
  Briefcase,
  UsersRound,
  FileText,
  CalendarDays,
  BarChart3,
  Settings,
  LogOut,
  PanelLeftClose,
  PanelLeft,
  Building2,
  ChevronDown,
  ChevronRight,
  BadgeCheck,
  Search,
  Users,
  Target,
} from "lucide-react";
import { Button, cn, Input } from "@dracara/ui";
import { createClient } from "@/lib/supabase/client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AppTopBar } from "@/components/layout/app-top-bar";

const nav = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/contacts", label: "Contacts", icon: UsersRound },
  { href: "/leads", label: "Leads", icon: Target },
  { href: "/opportunities", label: "Opportunities", icon: KanbanSquare },
  { href: "/companies", label: "Companies", icon: Briefcase },
  { href: "/follow-ups", label: "Follow-ups", icon: FileText },
  { href: "/calendar", label: "Calendar", icon: CalendarDays },
  { href: "/reports", label: "Reports", icon: BarChart3 },
  { href: "/agents", label: "Agents", icon: Users },
];

export function AppShell({
  children,
  user,
}: {
  children: React.ReactNode;
  user: { email: string; id: string };
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    try {
      const v = localStorage.getItem("dracara-sidebar-collapsed");
      if (v === "1") setCollapsed(true);
    } catch {
      /* ignore */
    }
  }, []);

  function persistCollapsed(next: boolean) {
    setCollapsed(next);
    try {
      localStorage.setItem("dracara-sidebar-collapsed", next ? "1" : "0");
    } catch {
      /* ignore */
    }
  }

  async function signOut() {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/login");
    router.refresh();
  }

  const displayName =
    user.email?.split("@")[0]?.replace(/\./g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) ?? "User";

  return (
    <div className="flex min-h-screen bg-[hsl(var(--canvas))]">
      <aside
        className={cn(
          "sticky top-0 hidden h-screen shrink-0 flex-col border-r border-border bg-card shadow-[2px_0_24px_-12px_rgba(15,23,42,0.06)] md:flex",
          collapsed ? "w-[72px]" : "w-64 lg:w-[260px]"
        )}
      >
        <div className="flex h-[52px] items-center justify-between gap-2 border-b border-border px-3 lg:h-14 lg:px-4">
          {!collapsed ? (
            <Link href="/dashboard" className="min-w-0 flex-1">
              <span className="block text-[15px] font-semibold tracking-tight text-[#0A1128] dark:text-foreground">
                Dracara
              </span>
              <span className="block text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                CR Management
              </span>
            </Link>
          ) : (
            <Link href="/dashboard" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[#0A1128] text-[11px] font-bold text-white">
              D
            </Link>
          )}
          <button
            type="button"
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className="hidden shrink-0 rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground lg:flex"
            onClick={() => persistCollapsed(!collapsed)}
          >
            {collapsed ? <PanelLeft className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
          </button>
        </div>

        <div className="border-b border-border/80 px-3 py-2 lg:px-4">
          <details className="group">
            <summary className="flex cursor-pointer list-none items-center gap-2 rounded-lg border border-border bg-muted/40 px-2.5 py-2 text-sm font-medium text-foreground outline-none ring-offset-background transition hover:bg-muted/70 [&::-webkit-details-marker]:hidden">
              <Building2 className="h-4 w-4 shrink-0 text-muted-foreground" />
              {!collapsed ? (
                <>
                  <span className="flex-1 truncate text-left">Mesh</span>
                  <ChevronDown className="h-4 w-4 shrink-0 opacity-50 group-open:rotate-180" />
                </>
              ) : null}
            </summary>
            {!collapsed ? (
              <div className="mt-1 rounded-lg border border-dashed border-border px-2 py-2 text-xs text-muted-foreground">
                Workspace settings coming soon.
              </div>
            ) : null}
          </details>
        </div>

        <nav className="flex flex-1 flex-col gap-0.5 overflow-y-auto p-3 lg:p-4">
          {nav.map(({ href, label, icon: Icon }) => {
            const active = pathname === href || pathname.startsWith(href + "/");
            return (
              <Link
                key={href}
                href={href}
                title={collapsed ? label : undefined}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                  active
                    ? "bg-[hsl(var(--accent))] text-[hsl(var(--accent-foreground))]"
                    : "text-muted-foreground hover:bg-muted/80 hover:text-foreground",
                  collapsed && "justify-center px-2"
                )}
              >
                <Icon className={cn("h-[18px] w-[18px] shrink-0", active ? "text-[hsl(var(--primary))]" : "")} aria-hidden />
                {!collapsed ? label : null}
              </Link>
            );
          })}
        </nav>

        {!collapsed ? (
          <div className="border-t border-border/80 px-4 py-2 space-y-0.5">
            <Link
              href="/settings"
              className="flex w-full items-center justify-between rounded-lg px-2 py-2 text-left text-sm font-medium text-muted-foreground hover:bg-muted/70 hover:text-foreground"
            >
              <span>Settings</span>
              <ChevronRight className="h-4 w-4 opacity-50" />
            </Link>
            <Link
              href="/reports"
              className="flex w-full items-center justify-between rounded-lg px-2 py-2 text-left text-sm font-medium text-muted-foreground hover:bg-muted/70 hover:text-foreground"
            >
              <span>Help Center</span>
              <ChevronRight className="h-4 w-4 opacity-50" />
            </Link>
          </div>
        ) : null}

        {!collapsed ? (
          <div className="mx-3 mb-3 rounded-xl border border-border bg-muted/30 p-3 lg:mx-4">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-xs font-medium text-muted-foreground">Cloud Storage</span>
              <span className="text-xs font-semibold text-[#0A1128] dark:text-foreground">90%</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-muted">
              <div className="h-full w-[90%] rounded-full bg-gradient-to-r from-amber-400 to-orange-500" />
            </div>
            <p className="mt-2 text-[11px] leading-snug text-muted-foreground">1.8 GB of 2 GB used</p>
            <Button
              variant="ghost"
              size="sm"
              className="mt-2 h-8 w-full justify-between px-2 text-xs font-semibold text-[hsl(var(--primary))]"
              type="button"
            >
              Upgrade Storage
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        ) : null}

        <div className="mt-auto border-t border-border p-3 lg:p-4">
          {!collapsed ? (
            <div className="flex items-start gap-3 rounded-xl bg-muted/40 p-3">
              <div className="relative">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-[hsl(var(--primary))] to-blue-700 text-sm font-semibold text-white">
                  {displayName.slice(0, 1)}
                </div>
              </div>
              <div className="min-w-0 flex-1">
                <p className="flex items-center gap-1 truncate text-sm font-semibold text-[#0A1128] dark:text-foreground">
                  {displayName}
                  <BadgeCheck className="h-4 w-4 shrink-0 text-[hsl(var(--primary))]" aria-label="Verified" />
                </p>
                <p className="truncate text-xs text-muted-foreground">{user.email}</p>
              </div>
            </div>
          ) : (
            <div className="flex justify-center">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-[hsl(var(--primary))] to-blue-700 text-sm font-semibold text-white">
                {displayName.slice(0, 1)}
              </div>
            </div>
          )}
          {!collapsed ? (
            <Button variant="ghost" size="sm" className="mt-3 w-full justify-start gap-2 text-muted-foreground" onClick={() => signOut()}>
              <LogOut className="h-4 w-4" />
              Sign out
            </Button>
          ) : (
            <Button variant="ghost" size="icon" className="mt-2 w-full" onClick={() => signOut()} title="Sign out">
              <LogOut className="h-4 w-4" />
            </Button>
          )}
        </div>
      </aside>

      <div className="flex min-h-screen min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-border bg-card/95 px-4 backdrop-blur md:hidden">
          <Link href="/dashboard" className="font-semibold text-[#0A1128] dark:text-foreground">
            Dracara
          </Link>
          <MobileNav pathname={pathname} />
        </header>

        <div className="hidden md:block">
          <AppTopBar />
        </div>

        <div className="border-b border-border bg-card/95 px-4 py-2.5 backdrop-blur md:hidden">
          <AppTopBarMobile />
        </div>

        <main className="flex-1 px-4 pb-5 pt-3 lg:px-6 lg:pb-6 lg:pt-4">{children}</main>
      </div>
    </div>
  );
}

/** Compact search strip for small screens — mirrors desktop top bar intent */
function AppTopBarMobile() {
  return (
    <div className="relative min-w-0 flex-1">
      <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
      <Input placeholder="Search…" className="h-8 rounded-lg pl-8 text-sm" />
    </div>
  );
}

function MobileNav({ pathname }: { pathname: string }) {
  return (
    <details className="relative">
      <summary className="cursor-pointer list-none rounded-lg border border-border bg-card px-3 py-1.5 text-sm font-medium shadow-sm">
        Menu
      </summary>
      <div className="absolute right-0 z-40 mt-2 max-h-[70vh] w-64 overflow-auto rounded-xl border border-border bg-card p-2 shadow-xl">
        {nav.map(({ href, label }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "block rounded-lg px-3 py-2 text-sm font-medium",
              pathname === href || pathname.startsWith(href + "/")
                ? "bg-[hsl(var(--accent))] text-[hsl(var(--accent-foreground))]"
                : "hover:bg-muted"
            )}
          >
            {label}
          </Link>
        ))}
        <Link
          href="/settings"
          className={cn(
            "mt-1 flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium hover:bg-muted",
            pathname.startsWith("/settings") ? "bg-[hsl(var(--accent))]" : ""
          )}
        >
          <Settings className="h-4 w-4" />
          Settings
        </Link>
      </div>
    </details>
  );
}
