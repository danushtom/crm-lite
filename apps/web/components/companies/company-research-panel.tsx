"use client";

/**
 * AI company research: a cited profile from the public web, plus suggested edits.
 *
 * Nothing here writes to the company on its own. Suggestions are checkboxes; applying them goes
 * through the ordinary `PATCH /companies/{id}` with `If-Match`, so a concurrent edit is caught
 * the same way it is in the company drawer. Filling a blank field is pre-checked; overwriting
 * something a person typed is not.
 *
 * Every fact links to the page it came from. A web page is not a trusted source, and the UI
 * should never present one as if it were.
 */

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge, Button, cardShell, cn } from "@dracara/ui";
import { AlertTriangle, ExternalLink, RefreshCw, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { ApiError, apiFetch } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { humanizeEnum } from "@/lib/forms";

type CitedFact = { value: string; source_url: string };
type Suggestion = {
  field: "industry" | "size" | "segment" | "location" | "linkedin_url";
  current: string | null;
  suggested: string;
  source_url: string;
  overwrites: boolean;
};
type Research = {
  research_id: string;
  company_version: number;
  profile: {
    description: CitedFact | null;
    recent_news: CitedFact[];
    tech_signals: CitedFact[];
    sources: { index: number; title: string; url: string }[];
    suspicious_content: boolean;
    note: string | null;
  };
  suggestions: Suggestion[];
  researched_at: string | null;
  from_cache: boolean;
};

function hostOf(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "source";
  }
}

function SourceLink({ url }: { url: string }) {
  return (
    <a
      href={url}
      target="_blank"
      // noreferrer: the page we cite should not learn which CRM record linked to it.
      rel="noopener noreferrer nofollow"
      className="inline-flex items-center gap-0.5 text-[11px] text-muted-foreground hover:text-foreground hover:underline"
    >
      {hostOf(url)}
      <ExternalLink className="h-2.5 w-2.5" />
    </a>
  );
}

export function CompanyResearchPanel({ companyId }: { companyId: string }) {
  const qc = useQueryClient();
  const [selected, setSelected] = useState<Record<string, boolean>>({});

  const { data: status } = useQuery({
    queryKey: ["ai", "status"],
    queryFn: () => apiFetch<{ research_configured: boolean }>("/ai/status"),
    staleTime: 5 * 60 * 1000,
  });

  const { data: research, isLoading } = useQuery({
    queryKey: ["ai", "research", companyId],
    queryFn: () => apiFetch<Research | null>(`/ai/companies/${companyId}/research`),
    enabled: Boolean(status?.research_configured),
  });

  // Default: fill blanks, never silently overwrite what a person typed.
  useEffect(() => {
    if (!research) return;
    setSelected(Object.fromEntries(research.suggestions.map((s) => [s.field, !s.overwrites])));
  }, [research]);

  const run = useMutation({
    mutationFn: (force: boolean) =>
      apiFetch<Research>(`/ai/companies/${companyId}/research`, {
        method: "POST",
        body: JSON.stringify({ force }),
      }),
    onSuccess: (data) => qc.setQueryData(["ai", "research", companyId], data),
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.message : "Research failed. Please try again."),
  });

  const apply = useMutation({
    mutationFn: async () => {
      const fields = research!.suggestions.filter((s) => selected[s.field]);
      const body = Object.fromEntries(fields.map((s) => [s.field, s.suggested]));
      return apiFetch(`/companies/${companyId}`, {
        method: "PATCH",
        headers: { "If-Match": `"${research!.company_version}"` },
        body: JSON.stringify(body),
      });
    },
    onSuccess: () => {
      toast.success("Company updated");
      void qc.invalidateQueries({ queryKey: ["companies", companyId] });
      void qc.invalidateQueries({ queryKey: ["ai", "research", companyId] });
    },
    onError: (err) => {
      // A 412 means someone edited the company since this research loaded.
      toast.error(
        err instanceof ApiError && err.status === 412
          ? "This company was edited since the research loaded. Refresh and try again."
          : err instanceof ApiError
            ? err.message
            : "Could not update the company.",
      );
    },
  });

  if (!status?.research_configured) return null;

  const profile = research?.profile;
  const chosen = research?.suggestions.filter((s) => selected[s.field]) ?? [];

  return (
    <section className={cn(cardShell, "space-y-4 p-5")}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <Sparkles className="h-4 w-4 text-primary" />
            Company research
          </h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {research?.researched_at
              ? `From the public web, ${formatDate(research.researched_at)}. Every fact links to its source.`
              : "Search the public web for this company. Only its name and website are sent."}
          </p>
        </div>
        <Button
          size="sm"
          variant={research ? "ghost" : "default"}
          onClick={() => run.mutate(Boolean(research))}
          disabled={run.isPending}
          className="gap-1.5"
        >
          {research ? <RefreshCw className={cn("h-3.5 w-3.5", run.isPending && "animate-spin")} /> : <Sparkles className="h-3.5 w-3.5" />}
          {run.isPending ? "Researching…" : research ? "Refresh" : "Research"}
        </Button>
      </div>

      {isLoading && <p className="text-xs text-muted-foreground">Loading…</p>}

      {profile?.suspicious_content && (
        <div className="flex gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          A source page contained instructions aimed at AI tools. Every fact below is still cited,
          but check them against the linked pages before relying on them.
        </div>
      )}

      {profile?.note && <p className="text-xs text-muted-foreground">{profile.note}</p>}

      {profile?.description && (
        <p className="text-sm leading-relaxed text-foreground">
          {profile.description.value} <SourceLink url={profile.description.source_url} />
        </p>
      )}

      {research && research.suggestions.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Suggested updates
          </h3>
          {research.suggestions.map((s) => (
            <label
              key={s.field}
              className="flex cursor-pointer items-start gap-2.5 rounded-lg border border-border/60 px-3 py-2 hover:bg-muted/40"
            >
              <input
                type="checkbox"
                className="mt-0.5"
                checked={Boolean(selected[s.field])}
                onChange={(e) => setSelected((cur) => ({ ...cur, [s.field]: e.target.checked }))}
              />
              <div className="min-w-0 flex-1 text-xs">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="font-medium text-foreground">{humanizeEnum(s.field)}</span>
                  {s.overwrites && (
                    <Badge variant="outline" className="h-4 px-1 text-[10px]">
                      replaces your value
                    </Badge>
                  )}
                </div>
                <div className="mt-0.5 text-muted-foreground">
                  {s.current ? <span className="line-through">{s.current}</span> : <span>empty</span>}
                  {" → "}
                  <span className="text-foreground">{s.suggested}</span>{" "}
                  <SourceLink url={s.source_url} />
                </div>
              </div>
            </label>
          ))}
          <Button
            size="sm"
            disabled={chosen.length === 0 || apply.isPending}
            onClick={() => apply.mutate()}
          >
            {apply.isPending ? "Applying…" : `Apply ${chosen.length} update${chosen.length === 1 ? "" : "s"}`}
          </Button>
        </div>
      )}

      {profile && profile.recent_news.length > 0 && (
        <div className="space-y-1.5">
          <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Recent news</h3>
          <ul className="space-y-1">
            {profile.recent_news.map((n, i) => (
              <li key={i} className="text-xs leading-relaxed text-foreground">
                {n.value} <SourceLink url={n.source_url} />
              </li>
            ))}
          </ul>
        </div>
      )}

      {profile && profile.tech_signals.length > 0 && (
        <div className="space-y-1.5">
          <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Tech signals</h3>
          <div className="flex flex-wrap gap-1.5">
            {profile.tech_signals.map((t, i) => (
              <a
                key={i}
                href={t.source_url}
                target="_blank"
                rel="noopener noreferrer nofollow"
                className="rounded-full border border-border px-2 py-0.5 text-[11px] text-foreground hover:bg-muted"
              >
                {t.value}
              </a>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
