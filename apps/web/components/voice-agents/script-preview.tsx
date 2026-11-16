"use client";

import type { ScriptPreview, VoiceAgentDataAccess, VoiceScript } from "@dracara/types";
import { Badge, Skeleton, cn } from "@dracara/ui";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, Database, MessageSquare, ShieldCheck, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

/**
 * "What will this agent actually do?" -- answered by the server, from the draft on screen.
 *
 * The walkthrough and the compiled prompt both come from POST /voice-agents/script-preview,
 * which runs the same compiler the agent is briefed with. A preview built in the browser would
 * be a second description of the behaviour, and the two would drift the first time either
 * changed.
 */

const ICONS = {
  says: MessageSquare,
  asks: MessageSquare,
  does: Database,
  guardrail: ShieldCheck,
} as const;

const TONE = {
  says: "text-foreground",
  asks: "text-foreground",
  does: "text-sky-700 dark:text-sky-300",
  guardrail: "text-emerald-700 dark:text-emerald-300",
} as const;

/** Debounced so typing in the builder does not fire a request per keystroke. */
function useDebounced<T>(value: T, ms: number): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setSettled(value), ms);
    return () => window.clearTimeout(timer);
  }, [value, ms]);
  return settled;
}

export function ScriptPreviewPanel({
  name,
  personaName,
  roleTitle,
  script,
  dataAccess,
}: {
  name: string;
  personaName: string;
  roleTitle: string;
  script: VoiceScript;
  dataAccess: VoiceAgentDataAccess;
}) {
  const draft = useDebounced(
    JSON.stringify({ name, persona_name: personaName, role_title: roleTitle, script, data_access: dataAccess }),
    500
  );
  const [showPrompt, setShowPrompt] = useState(false);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["voice-agents", "script-preview", draft],
    queryFn: () => apiFetch<ScriptPreview>("/voice-agents/script-preview", { method: "POST", body: draft }),
    // Keep the last good preview on screen while the next one loads, so the panel does not
    // flash empty on every edit.
    placeholderData: (previous) => previous,
    retry: false,
  });

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Sparkles className="h-4 w-4 text-[hsl(var(--primary))]" aria-hidden />
        <h3 className="text-sm font-semibold">How the call will go</h3>
      </div>

      {isError ? (
        <p className="text-xs text-destructive">Could not build a preview for this script.</p>
      ) : isLoading && !data ? (
        <div className="space-y-2">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      ) : data ? (
        <>
          <ol className="relative space-y-3 border-l border-border pl-4">
            {data.preview.map((step, index) => {
              const Icon = ICONS[step.kind];
              return (
                <li key={index} className="relative">
                  <span
                    className={cn(
                      "absolute -left-[22px] flex h-4 w-4 items-center justify-center rounded-full bg-card ring-1 ring-border",
                      step.kind === "guardrail" && "ring-emerald-500/50"
                    )}
                    aria-hidden
                  >
                    <Icon className={cn("h-2.5 w-2.5", TONE[step.kind])} />
                  </span>
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                    {step.label}
                  </p>
                  <p className={cn("text-sm", TONE[step.kind])}>{step.detail}</p>
                </li>
              );
            })}
          </ol>

          <div className="rounded-lg border border-border/60 bg-muted/20">
            <button
              type="button"
              className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left"
              aria-expanded={showPrompt}
              onClick={() => setShowPrompt((open) => !open)}
            >
              <span className="text-xs font-medium">
                Exactly what the AI is told
                <span className="ml-1.5 font-normal text-muted-foreground">
                  ({data.system_prompt.split(/\s+/).length} words)
                </span>
              </span>
              <ChevronDown className={cn("h-4 w-4 shrink-0 transition-transform", showPrompt && "rotate-180")} />
            </button>
            {showPrompt ? (
              <pre className="max-h-80 overflow-auto whitespace-pre-wrap border-t border-border/60 px-3 py-2 font-mono text-[11px] leading-relaxed text-muted-foreground">
                {data.system_prompt}
              </pre>
            ) : null}
          </div>

          {/* A div, not a p: Badge renders a div, and a div inside a p is invalid HTML that
              React reports as a hydration error. */}
          <div className="flex items-start gap-1.5 text-[11px] text-muted-foreground">
            <Badge variant="outline" className="shrink-0 text-[10px]">
              Fixed
            </Badge>
            <span>
              Every call opens with the recording disclosure above. It is not editable, and it
              plays before anything in your script.
            </span>
          </div>
        </>
      ) : null}
    </div>
  );
}
