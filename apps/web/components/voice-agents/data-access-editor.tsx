"use client";

import type { LeadField, VoiceAgentDataAccess, VoiceTool } from "@dracara/types";
import { Badge, cn } from "@dracara/ui";
import { Lock, PencilLine, ShieldCheck } from "lucide-react";
import { ALWAYS_ON_TOOLS, LEAD_FIELDS, OPTIONAL_TOOLS } from "@/lib/voice-agents";

/**
 * What the organization shares with this agent.
 *
 * Every switch here is enforced on the server, in the tool dispatcher -- not in the browser and
 * not only in the tool list handed to the voice platform, because a tool call can arrive for a
 * tool that was never offered. Turning something off here means the agent is refused if it
 * tries, which is the sentence this screen is allowed to make.
 */

function Toggle({
  checked,
  onChange,
  label,
  blurb,
  badge,
  sensitive,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  blurb: string;
  badge?: React.ReactNode;
  sensitive?: boolean;
}) {
  return (
    <label
      className={cn(
        "flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition",
        checked ? "border-[hsl(var(--primary))]/40 bg-[hsl(var(--primary))]/5" : "border-border hover:bg-muted/40"
      )}
    >
      <input
        type="checkbox"
        className="mt-0.5 h-4 w-4 shrink-0 rounded border-border"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center gap-1.5">
          <span className="text-sm font-medium">{label}</span>
          {badge}
          {sensitive && checked ? (
            <Badge variant="outline" className="border-amber-500/50 text-[10px] text-amber-700 dark:text-amber-400">
              Sensitive
            </Badge>
          ) : null}
        </span>
        <span className="mt-0.5 block text-xs text-muted-foreground">{blurb}</span>
      </span>
    </label>
  );
}

export function DataAccessEditor({
  value,
  onChange,
}: {
  value: VoiceAgentDataAccess;
  onChange: (next: VoiceAgentDataAccess) => void;
}) {
  const tools = value.tools ?? {};
  const fields = value.lead_fields ?? [];
  const readsCrm = tools.get_lead_context === true;

  const setTool = (tool: VoiceTool, on: boolean) =>
    onChange({ ...value, tools: { ...tools, [tool]: on } });

  const setField = (field: LeadField, on: boolean) =>
    onChange({
      ...value,
      lead_fields: on ? [...fields, field] : fields.filter((f) => f !== field),
    });

  return (
    <div className="space-y-7">
      <section className="space-y-3">
        <div>
          <h3 className="text-sm font-semibold">What it can do</h3>
          <p className="text-xs text-muted-foreground">
            Switched off means refused: if the agent tries anyway, it is told it cannot and offers a
            callback instead.
          </p>
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          {OPTIONAL_TOOLS.map((tool) => (
            <Toggle
              key={tool.value}
              checked={tools[tool.value] === true}
              onChange={(on) => setTool(tool.value, on)}
              label={tool.label}
              blurb={tool.blurb}
              badge={
                tool.writes ? (
                  <Badge variant="outline" className="gap-1 text-[10px]">
                    <PencilLine className="h-2.5 w-2.5" />
                    Writes to your CRM
                  </Badge>
                ) : null
              }
            />
          ))}
        </div>
        <div className="rounded-lg border border-border/60 bg-muted/30 p-3">
          <p className="flex items-center gap-1.5 text-xs font-medium">
            <Lock className="h-3.5 w-3.5 text-muted-foreground" />
            Always on, for every agent
          </p>
          <ul className="mt-1.5 space-y-0.5">
            {ALWAYS_ON_TOOLS.map((tool) => (
              <li key={tool.label} className="text-xs text-muted-foreground">
                <span className="font-medium text-foreground">{tool.label}</span> — {tool.blurb}
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="space-y-3 border-t border-border/60 pt-5">
        <div>
          <h3 className="text-sm font-semibold">What it may know about the lead</h3>
          <p className="text-xs text-muted-foreground">
            Background for better questions. The agent is told never to read these out, and anything
            unticked is never sent to it at all.
          </p>
        </div>
        {!readsCrm ? (
          <p className="rounded-lg border border-border/60 bg-muted/30 p-3 text-xs text-muted-foreground">
            This agent cannot read CRM data, so none of these apply. Turn on{" "}
            <span className="font-medium text-foreground">Read CRM data about the lead</span> above to
            choose fields.
          </p>
        ) : (
          <div className="grid gap-2 sm:grid-cols-2">
            {LEAD_FIELDS.map((field) => (
              <Toggle
                key={field.value}
                checked={fields.includes(field.value)}
                onChange={(on) => setField(field.value, on)}
                label={field.label}
                blurb={field.blurb}
                sensitive={field.sensitive}
              />
            ))}
          </div>
        )}
      </section>

      <section className="flex items-start gap-2 rounded-lg border border-emerald-500/30 bg-emerald-50/60 p-3 dark:bg-emerald-950/20">
        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
        <p className="text-xs text-emerald-900 dark:text-emerald-200">
          Whatever you choose here, every agent is told it must say it is an AI if asked, must never
          quote a figure it cannot look up, and must stop if the person asks not to be called again.
          Those rules cannot be switched off from a script.
        </p>
      </section>
    </div>
  );
}
