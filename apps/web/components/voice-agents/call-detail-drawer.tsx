"use client";

import {
  Badge,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
  Skeleton,
  cn,
  fieldLabel,
} from "@dracara/ui";
import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { apiFetch } from "@/lib/api";
import { formatDateTime, formatDuration } from "@/lib/format";
import { CALL_STATUS_LABEL, CALL_STATUS_TONE } from "@/lib/calls";
import type { Call } from "@dracara/types";

/**
 * Read-only call detail: transcript, recording, summary and the agent's suggested next action.
 *
 * `GET /voice-agents/calls/{id}` returns all of this and had no caller in the frontend at all --
 * the call log showed six columns and there was no way to open one. Fetched only while open so
 * the log does not turn into one request per row.
 */
export function CallDetailDrawer({ callId, trigger }: { callId: string; trigger: ReactNode }) {
  const [open, setOpen] = useState(false);

  const { data: call, isLoading, error } = useQuery({
    queryKey: ["voice-agents", "call", callId],
    queryFn: () => apiFetch<Call>(`/voice-agents/calls/${callId}`),
    enabled: open,
    retry: false,
  });

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>{trigger}</SheetTrigger>
      <SheetContent
        side="right"
        className="flex w-[400px] flex-col overflow-y-auto border-l border-border/60 sm:w-[600px]"
      >
        <SheetHeader className="border-b border-border/50 pb-4">
          <SheetTitle className="text-xl">Call detail</SheetTitle>
          <SheetDescription>
            {call ? `${call.from_number} → ${call.to_number}` : "Loading the transcript…"}
          </SheetDescription>
        </SheetHeader>

        {error ? (
          <p className="py-6 text-sm text-destructive">{(error as Error).message}</p>
        ) : isLoading || !call ? (
          <div className="space-y-3 py-6">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-4 w-64" />
            <Skeleton className="h-32 w-full" />
          </div>
        ) : (
          <div className="space-y-5 py-6">
            <div className="grid grid-cols-2 gap-x-4 gap-y-3">
              <Detail label="Status">
                <Badge
                  className={cn(
                    "h-5 rounded-md px-2 text-[10px] font-semibold",
                    CALL_STATUS_TONE[call.status]
                  )}
                >
                  {CALL_STATUS_LABEL[call.status] ?? call.status}
                </Badge>
              </Detail>
              <Detail label="Direction">
                <span className="capitalize">{call.direction}</span>
              </Detail>
              <Detail label="Started">{formatDateTime(call.started_at)}</Detail>
              <Detail label="Duration">{formatDuration(call.duration_seconds)}</Detail>
              <Detail label="Outcome">{call.outcome ?? "—"}</Detail>
              <Detail label="Ended">{formatDateTime(call.ended_at)}</Detail>
            </div>

            {call.recording_url ? (
              <section className="space-y-2">
                <p className={fieldLabel}>Recording</p>
                {/* eslint-disable-next-line jsx-a11y/media-has-caption -- a phone recording has
                    no caption track; the transcript below is the accessible equivalent. */}
                <audio controls src={call.recording_url} className="w-full" />
              </section>
            ) : null}

            {call.summary ? (
              <section className="space-y-1.5">
                <p className={fieldLabel}>Summary</p>
                <p className="text-sm text-foreground">{call.summary}</p>
              </section>
            ) : null}

            {call.suggested_next_action ? (
              <section className="space-y-1.5 rounded-lg border border-border/60 bg-muted/20 p-3">
                <p className={fieldLabel}>Suggested next action</p>
                <p className="text-sm text-foreground">{call.suggested_next_action}</p>
              </section>
            ) : null}

            <section className="space-y-1.5">
              <p className={fieldLabel}>Transcript</p>
              {call.transcript ? (
                <pre className="max-h-[420px] overflow-y-auto whitespace-pre-wrap rounded-lg border border-border/60 bg-muted/20 p-3 font-sans text-sm leading-relaxed text-foreground">
                  {call.transcript}
                </pre>
              ) : (
                <p className="text-sm text-muted-foreground">
                  No transcript yet. It arrives from the voice platform once the call ends.
                </p>
              )}
            </section>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}

function Detail({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <p className={fieldLabel}>{label}</p>
      <div className="text-sm text-foreground">{children}</div>
    </div>
  );
}
