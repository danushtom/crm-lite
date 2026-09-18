"use client";

/**
 * "Draft with AI" on the proposals page.
 *
 * Deliberately not a one-click "generate and save". The backend writes the draft as a new
 * proposal version, and this shows the founder what it wrote before they go and edit it — a
 * proposal is a commercial document with a price in it, and the product claim is "3x faster to a
 * first draft", not "proposals nobody read".
 *
 * Hidden entirely when AI is not configured, so the button never sits there returning a 501.
 */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Badge } from "@dracara/ui";
import { Sparkles, X, Copy, Check } from "lucide-react";
import { toast } from "sonner";
import { ApiError, apiFetch } from "@/lib/api";

type AiStatus = { enabled: boolean; configured: boolean; detail: string };

type DraftResponse = {
  proposal_id: string;
  version: number;
  title: string;
  markdown: string;
  tokens_used: number;
};

export function DraftWithAiButton({ opportunityId }: { opportunityId: string }) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<DraftResponse | null>(null);
  const [copied, setCopied] = useState(false);

  const { data: status } = useQuery({
    queryKey: ["ai", "status"],
    queryFn: () => apiFetch<AiStatus>("/ai/status"),
    // The deployment's configuration does not change between page views.
    staleTime: 5 * 60 * 1000,
  });

  const mutation = useMutation({
    mutationFn: () =>
      apiFetch<DraftResponse>(`/ai/proposals/${opportunityId}/draft`, {
        method: "POST",
        body: JSON.stringify({}),
      }),
    onSuccess: (data) => {
      setDraft(data);
      // The draft is a real proposal version, so the list behind this panel is now stale.
      void queryClient.invalidateQueries({ queryKey: ["opportunity", opportunityId] });
      toast.success(`Draft saved as version ${data.version}`);
    },
    onError: (err) => {
      toast.error(
        err instanceof ApiError ? err.message : "Could not draft this proposal. Please try again.",
      );
    },
  });

  if (!status?.configured) return null;

  const copy = async () => {
    if (!draft) return;
    await navigator.clipboard.writeText(draft.markdown);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <>
      <Button
        variant="outline"
        onClick={() => mutation.mutate()}
        disabled={mutation.isPending}
        className="gap-2"
      >
        <Sparkles className="h-4 w-4" />
        {mutation.isPending ? "Drafting…" : "Draft with AI"}
      </Button>

      {draft && (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm"
            onClick={() => setDraft(null)}
          />
          <div className="fixed inset-y-0 right-0 z-50 flex w-full max-w-2xl flex-col border-l border-border bg-card shadow-2xl">
            <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
              <div>
                <h2 className="text-sm font-semibold text-foreground">{draft.title}</h2>
                <div className="mt-1 flex items-center gap-2">
                  <Badge variant="secondary" className="text-[11px]">
                    Version {draft.version} · draft
                  </Badge>
                  <span className="text-[11px] text-muted-foreground">
                    {draft.tokens_used.toLocaleString()} tokens
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-1">
                <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => void copy()}>
                  {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8"
                  onClick={() => setDraft(null)}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            </div>

            <div className="border-b border-border bg-muted/40 px-5 py-2.5">
              <p className="text-[11px] leading-relaxed text-muted-foreground">
                A first draft, saved as a new version. Anything in{" "}
                <code className="rounded bg-muted px-1">[CONFIRM: …]</code> is a gap the AI would
                not guess at — fill those in before this goes anywhere near a client.
              </p>
            </div>

            <div className="flex-1 overflow-y-auto p-5">
              <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-relaxed text-foreground">
                {draft.markdown}
              </pre>
            </div>
          </div>
        </>
      )}
    </>
  );
}
