"use client";

/**
 * The two-minute read before a call: who they are, why now, what to say, what to ask.
 *
 * Built from the lead's CRM facts plus public research on its company. The brief is stored, so
 * opening the lead again shows the last one instantly; "Refresh" writes a new one.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, CardContent, CardHeader, CardTitle, cn } from "@dracara/ui";
import { PhoneCall, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { ApiError, apiFetch } from "@/lib/api";
import { formatDate } from "@/lib/format";

type Brief = {
  brief_id: string;
  brief: {
    summary: string;
    why_now: string;
    talking_points: string[];
    questions_to_ask: string[];
    risks: string[];
  };
  created_at: string | null;
};

function List({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div className="space-y-1">
      <h4 className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{title}</h4>
      <ul className="list-disc space-y-1 pl-4 text-sm leading-relaxed text-foreground">
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

export function PreCallBrief({ leadId }: { leadId: string }) {
  const qc = useQueryClient();

  const { data: status } = useQuery({
    queryKey: ["ai", "status"],
    queryFn: () => apiFetch<{ research_configured: boolean }>("/ai/status"),
    staleTime: 5 * 60 * 1000,
  });

  const { data: brief } = useQuery({
    queryKey: ["ai", "brief", leadId],
    queryFn: () => apiFetch<Brief | null>(`/ai/leads/${leadId}/brief`),
    enabled: Boolean(status?.research_configured),
  });

  const run = useMutation({
    mutationFn: () => apiFetch<Brief>(`/ai/leads/${leadId}/brief`, { method: "POST" }),
    onSuccess: (data) => qc.setQueryData(["ai", "brief", leadId], data),
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.message : "Could not write the brief. Please try again."),
  });

  if (!status?.research_configured) return null;

  return (
    <Card className="rounded-xl border border-border/70 bg-card shadow-[0_1px_3px_rgba(15,23,42,0.06)]">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 border-b border-border/50 pb-3">
        <CardTitle className="flex items-center gap-2 text-base font-semibold">
          <PhoneCall className="h-4 w-4 text-muted-foreground" />
          Pre-call brief
        </CardTitle>
        <Button
          size="sm"
          variant={brief ? "ghost" : "default"}
          disabled={run.isPending}
          onClick={() => run.mutate()}
          className="gap-1.5"
        >
          {brief && <RefreshCw className={cn("h-3.5 w-3.5", run.isPending && "animate-spin")} />}
          {run.isPending ? "Writing…" : brief ? "Refresh" : "Write brief"}
        </Button>
      </CardHeader>
      <CardContent className="space-y-3 pt-4">
        {!brief ? (
          <p className="text-sm text-muted-foreground">
            A quick read before you call: who they are, why now, and what to ask. Uses this lead&apos;s
            notes plus public research on the company.
          </p>
        ) : (
          <>
            <p className="text-sm leading-relaxed text-foreground">{brief.brief.summary}</p>
            {brief.brief.why_now && (
              <p className="rounded-lg bg-primary/5 px-3 py-2 text-sm text-foreground">
                <span className="font-medium">Why now: </span>
                {brief.brief.why_now}
              </p>
            )}
            <List title="Talking points" items={brief.brief.talking_points} />
            <List title="Questions to ask" items={brief.brief.questions_to_ask} />
            <List title="Risks" items={brief.brief.risks} />
            {brief.created_at && (
              <p className="text-[11px] text-muted-foreground">Written {formatDate(brief.created_at)}</p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
