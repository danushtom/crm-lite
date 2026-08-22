"use client";

import {
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  cn,
} from "@dracara/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { formatDistanceToNow, parseISO } from "date-fns";
import { Bell } from "lucide-react";
import { toast } from "sonner";
import { apiFetch, apiList } from "@/lib/api";

type NotificationRow = {
  id: string;
  type: string;
  title: string;
  body: string | null;
  read_at: string | null;
  created_at: string;
};

function relative(iso: string): string {
  try {
    return formatDistanceToNow(parseISO(iso), { addSuffix: true });
  } catch {
    return "";
  }
}

export function NotificationBell() {
  const qc = useQueryClient();

  const { data: notifications = [] } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => apiList<NotificationRow>("/notifications?limit=20"),
    refetchInterval: 60_000,
    // The bell is chrome on every page — a failure here must not surface as a page error.
    retry: 1,
  });

  const unread = notifications.filter((n) => !n.read_at);

  const markRead = useMutation({
    mutationFn: (id: string) =>
      apiFetch(`/notifications/${id}`, { method: "PATCH", body: JSON.stringify({ read: true }) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
    onError: (e: Error) => toast.error(e.message || "Could not update notification"),
  });

  const markAllRead = useMutation({
    mutationFn: () => apiFetch("/notifications/read-all", { method: "POST", body: "{}" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
    onError: (e: Error) => toast.error(e.message || "Could not update notifications"),
  });

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="relative h-9 w-9 shrink-0 text-muted-foreground"
          aria-label={unread.length ? `Notifications (${unread.length} unread)` : "Notifications"}
        >
          <Bell className="h-[18px] w-[18px]" />
          {unread.length > 0 ? (
            <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-bold leading-none text-white">
              {unread.length > 9 ? "9+" : unread.length}
            </span>
          ) : null}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80 p-0">
        <div className="flex items-center justify-between px-3 py-2">
          <DropdownMenuLabel className="p-0 text-sm">Notifications</DropdownMenuLabel>
          {unread.length > 0 ? (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-xs"
              disabled={markAllRead.isPending}
              onClick={() => markAllRead.mutate()}
            >
              Mark all read
            </Button>
          ) : null}
        </div>
        <DropdownMenuSeparator className="my-0" />
        <div className="max-h-96 overflow-y-auto">
          {notifications.length === 0 ? (
            <p className="px-3 py-6 text-center text-sm text-muted-foreground">You&rsquo;re all caught up.</p>
          ) : (
            notifications.map((n) => (
              <button
                key={n.id}
                type="button"
                onClick={() => !n.read_at && markRead.mutate(n.id)}
                className={cn(
                  "block w-full border-b border-border/50 px-3 py-2.5 text-left last:border-b-0 hover:bg-muted/50",
                  !n.read_at && "bg-muted/30"
                )}
              >
                <div className="flex items-start gap-2">
                  {!n.read_at ? (
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#0B7FB3]" aria-hidden />
                  ) : (
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0" aria-hidden />
                  )}
                  <div className="min-w-0 flex-1">
                    <p className={cn("truncate text-sm", !n.read_at && "font-semibold")}>{n.title}</p>
                    {n.body ? <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{n.body}</p> : null}
                    <p className="mt-1 text-[11px] text-muted-foreground">{relative(n.created_at)}</p>
                  </div>
                </div>
              </button>
            ))
          )}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
