"use client";

import type { CallSummary } from "@dracara/types";
import { Badge, Button, Card, CardContent, Skeleton, cn } from "@dracara/ui";
import { useQuery } from "@tanstack/react-query";
import { PhoneIncoming, PhoneOutgoing } from "lucide-react";
import { useState } from "react";
import { apiPage } from "@/lib/api";
import { CALL_STATUS_LABEL, CALL_STATUS_TONE } from "@/lib/calls";
import { formatDateTime, formatDuration } from "@/lib/format";
import { CallDetailDrawer } from "@/components/voice-agents/call-detail-drawer";

const PAGE_SIZE = 15;

/** One agent's own calls, newest first -- the "what has this employee been doing" view. */
export function AgentCallLog({ agentId }: { agentId: string }) {
  const [page, setPage] = useState(0);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["voice-agents", "calls", agentId, page],
    queryFn: () =>
      apiPage<CallSummary>(
        `/voice-agents/calls?voice_agent_id=${agentId}&limit=${PAGE_SIZE}&offset=${page * PAGE_SIZE}`
      ),
    retry: false,
  });

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-14 w-full" />
        ))}
      </div>
    );
  }
  if (isError) {
    return <p className="text-sm text-destructive">Could not load this agent&apos;s calls.</p>;
  }
  if (!data?.items.length) {
    return (
      <Card>
        <CardContent className="py-10 text-center text-sm text-muted-foreground">
          {page === 0 ? "This agent has not made or taken a call yet." : "No more calls."}
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      <Card>
        <CardContent className="p-0">
          <ul className="divide-y divide-border/60">
            {data.items.map((call) => {
              const Icon = call.direction === "outbound" ? PhoneOutgoing : PhoneIncoming;
              return (
                <li key={call.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                  <Icon className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium tabular-nums">
                      {call.direction === "outbound" ? call.to_number : call.from_number}
                    </p>
                    <p className="truncate text-xs text-muted-foreground">
                      {formatDateTime(call.created_at)}
                      {call.duration_seconds ? ` · ${formatDuration(call.duration_seconds)}` : ""}
                      {call.outcome ? ` · ${call.outcome}` : ""}
                    </p>
                  </div>
                  <Badge
                    className={cn("h-5 shrink-0 rounded-md px-2 text-[10px] font-semibold", CALL_STATUS_TONE[call.status])}
                  >
                    {CALL_STATUS_LABEL[call.status] ?? call.status}
                  </Badge>
                  <CallDetailDrawer
                    callId={call.id}
                    trigger={
                      <Button variant="ghost" size="sm" className="h-8 shrink-0 text-xs">
                        Open
                      </Button>
                    }
                  />
                </li>
              );
            })}
          </ul>
        </CardContent>
      </Card>

      {page > 0 || data.page.has_more ? (
        <div className="flex justify-between">
          <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
            Newer
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={!data.page.has_more}
            onClick={() => setPage((p) => p + 1)}
          >
            Older
          </Button>
        </div>
      ) : null}
    </div>
  );
}
