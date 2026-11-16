"use client";

import type { ScriptGoal, ScriptTone, VoiceScript } from "@dracara/types";
import { Badge, Button, Input, cn } from "@dracara/ui";
import { GripVertical, Plus, X } from "lucide-react";
import { Field, TextareaField, labelClass } from "@/components/shared/entity-drawer";
import { GOALS, TONES } from "@/lib/voice-agents";

/**
 * The script editor. A client fills this in; the server compiles it into the agent's prompt
 * (see dracara_ai.voice_script), which is why nothing here is free-form prompt text except the
 * clearly-labelled notes box at the end.
 *
 * Controlled: the page that owns the save button owns the state, so an unsaved script is
 * obvious and the preview beside it can re-render as the client types.
 */

export const EMPTY_SCRIPT: VoiceScript = {
  goal: "qualify",
  tone: "warm",
  opening: "",
  talking_points: [],
  questions: [],
  objections: [],
  must: [],
  never: [],
  closing: "",
  handoff: "",
  extra: "",
  max_minutes: null,
};

type Props = {
  script: VoiceScript;
  onChange: (next: VoiceScript) => void;
};

/** A section of the builder, with its own heading and why-it-matters line. */
function Block({
  title,
  description,
  children,
  count,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
  count?: number;
}) {
  return (
    <section className="space-y-3 border-t border-border/60 pt-5 first:border-0 first:pt-0">
      <div className="flex items-baseline justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">{title}</h3>
          <p className="text-xs text-muted-foreground">{description}</p>
        </div>
        {count ? (
          <Badge variant="secondary" className="shrink-0 tabular-nums">
            {count}
          </Badge>
        ) : null}
      </div>
      {children}
    </section>
  );
}

/** A reorderable-by-buttons list of one-line entries. */
function LineList({
  label,
  lines,
  onChange,
  placeholder,
  addLabel,
  tone,
}: {
  label: string;
  lines: string[];
  onChange: (next: string[]) => void;
  placeholder: string;
  addLabel: string;
  tone?: "danger";
}) {
  const set = (index: number, value: string) =>
    onChange(lines.map((line, i) => (i === index ? value : line)));
  const remove = (index: number) => onChange(lines.filter((_, i) => i !== index));
  const move = (index: number, by: number) => {
    const next = [...lines];
    const target = index + by;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
  };

  return (
    <div className="space-y-2">
      <span className={cn("sr-only", labelClass)}>{label}</span>
      {lines.map((line, index) => (
        <div key={index} className="flex items-start gap-1.5">
          <div className="flex flex-col pt-1.5">
            <button
              type="button"
              aria-label={`Move ${label} ${index + 1} up`}
              className="text-muted-foreground/60 hover:text-foreground disabled:opacity-30"
              disabled={index === 0}
              onClick={() => move(index, -1)}
            >
              <GripVertical className="h-3.5 w-3.5" />
            </button>
          </div>
          <Input
            value={line}
            placeholder={placeholder}
            aria-label={`${label} ${index + 1}`}
            className={cn("flex-1", tone === "danger" && "border-destructive/30")}
            onChange={(e) => set(index, e.target.value)}
          />
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-9 w-9 shrink-0 text-muted-foreground hover:text-destructive"
            aria-label={`Remove ${label} ${index + 1}`}
            onClick={() => remove(index)}
          >
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
      ))}
      <Button type="button" variant="outline" size="sm" onClick={() => onChange([...lines, ""])}>
        <Plus className="h-3.5 w-3.5" />
        {addLabel}
      </Button>
    </div>
  );
}

export function ScriptBuilder({ script, onChange }: Props) {
  const patch = (changes: Partial<VoiceScript>) => onChange({ ...script, ...changes });

  return (
    <div className="space-y-6">
      <Block title="What is this call for?" description="Sets the agent's objective and the way it steers the conversation.">
        <div className="grid gap-2 sm:grid-cols-2" role="radiogroup" aria-label="Call goal">
          {GOALS.map((goal) => (
            <button
              key={goal.value}
              type="button"
              role="radio"
              aria-checked={script.goal === goal.value}
              onClick={() => patch({ goal: goal.value as ScriptGoal })}
              className={cn(
                "rounded-lg border px-3 py-2.5 text-left transition hover:border-[hsl(var(--primary))]",
                script.goal === goal.value
                  ? "border-[hsl(var(--primary))] bg-[hsl(var(--primary))]/5 ring-1 ring-[hsl(var(--primary))]"
                  : "border-border"
              )}
            >
              <p className="text-sm font-medium">{goal.label}</p>
              <p className="text-xs text-muted-foreground">{goal.blurb}</p>
            </button>
          ))}
        </div>
      </Block>

      <Block title="How should it sound?" description="Delivery only. What it may say is set by the sections below.">
        <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Tone">
          {TONES.map((tone) => (
            <button
              key={tone.value}
              type="button"
              role="radio"
              aria-checked={script.tone === tone.value}
              onClick={() => patch({ tone: tone.value as ScriptTone })}
              className={cn(
                "rounded-full border px-3.5 py-1.5 text-sm transition",
                script.tone === tone.value
                  ? "border-[hsl(var(--primary))] bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))]"
                  : "border-border hover:border-[hsl(var(--primary))]"
              )}
              title={tone.blurb}
            >
              {tone.label}
            </button>
          ))}
        </div>
      </Block>

      <Block
        title="How it opens"
        description="The recording disclosure is spoken first, automatically. This is what comes next."
      >
        <TextareaField
          id="script-opening"
          label="Opening"
          rows={3}
          value={script.opening}
          onChange={(opening) => patch({ opening })}
          placeholder="Say you are following up on their enquiry, and ask if now is a good moment."
          hint="Describe it rather than writing a line to read out -- it will put this in its own words."
        />
      </Block>

      <Block
        title="What to cover"
        description="Points it should work in when the conversation allows."
        count={script.talking_points.length}
      >
        <LineList
          label="Talking point"
          lines={script.talking_points}
          onChange={(talking_points) => patch({ talking_points })}
          placeholder="We work in fixed-scope phases, so you know the cost up front."
          addLabel="Add a talking point"
        />
      </Block>

      <Block
        title="What to find out"
        description="Asked one at a time. Mark a question required and it will not end the call without an answer."
        count={script.questions.length}
      >
        <div className="space-y-3">
          {script.questions.map((question, index) => (
            <div key={index} className="space-y-2 rounded-lg border border-border/70 bg-muted/20 p-3">
              <div className="flex items-start gap-2">
                <Input
                  value={question.ask}
                  aria-label={`Question ${index + 1}`}
                  placeholder="What are you trying to build?"
                  className="flex-1"
                  onChange={(e) =>
                    patch({
                      questions: script.questions.map((q, i) =>
                        i === index ? { ...q, ask: e.target.value } : q
                      ),
                    })
                  }
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-9 w-9 shrink-0 text-muted-foreground hover:text-destructive"
                  aria-label={`Remove question ${index + 1}`}
                  onClick={() => patch({ questions: script.questions.filter((_, i) => i !== index) })}
                >
                  <X className="h-3.5 w-3.5" />
                </Button>
              </div>
              <Input
                value={question.why}
                aria-label={`Why question ${index + 1} matters`}
                placeholder="Why it matters — shapes how it follows up (optional)"
                className="text-xs"
                onChange={(e) =>
                  patch({
                    questions: script.questions.map((q, i) =>
                      i === index ? { ...q, why: e.target.value } : q
                    ),
                  })
                }
              />
              <label className="flex items-center gap-2 text-xs text-muted-foreground">
                <input
                  type="checkbox"
                  className="h-3.5 w-3.5 rounded border-border"
                  checked={question.required}
                  onChange={(e) =>
                    patch({
                      questions: script.questions.map((q, i) =>
                        i === index ? { ...q, required: e.target.checked } : q
                      ),
                    })
                  }
                />
                Must get an answer before the call ends
              </label>
            </div>
          ))}
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() =>
              patch({ questions: [...script.questions, { ask: "", why: "", required: false }] })
            }
          >
            <Plus className="h-3.5 w-3.5" />
            Add a question
          </Button>
        </div>
      </Block>

      <Block
        title="Expected objections"
        description="What it should say when it hears the usual pushback. Without these it improvises."
        count={script.objections.length}
      >
        <div className="space-y-3">
          {script.objections.map((objection, index) => (
            <div key={index} className="space-y-2 rounded-lg border border-border/70 bg-muted/20 p-3">
              <div className="flex items-start gap-2">
                <Input
                  value={objection.objection}
                  aria-label={`Objection ${index + 1}`}
                  placeholder={'If they say "it is too expensive"...'}
                  className="flex-1"
                  onChange={(e) =>
                    patch({
                      objections: script.objections.map((o, i) =>
                        i === index ? { ...o, objection: e.target.value } : o
                      ),
                    })
                  }
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-9 w-9 shrink-0 text-muted-foreground hover:text-destructive"
                  aria-label={`Remove objection ${index + 1}`}
                  onClick={() => patch({ objections: script.objections.filter((_, i) => i !== index) })}
                >
                  <X className="h-3.5 w-3.5" />
                </Button>
              </div>
              <textarea
                value={objection.response}
                aria-label={`Response to objection ${index + 1}`}
                rows={2}
                placeholder="...ask which part surprised them and offer to phase the work. Do not offer a discount."
                className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                onChange={(e) =>
                  patch({
                    objections: script.objections.map((o, i) =>
                      i === index ? { ...o, response: e.target.value } : o
                    ),
                  })
                }
              />
            </div>
          ))}
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => patch({ objections: [...script.objections, { objection: "", response: "" }] })}
          >
            <Plus className="h-3.5 w-3.5" />
            Add an objection
          </Button>
        </div>
      </Block>

      <Block title="Your own rules" description="Added on top of the safety rules every agent follows.">
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Always" hint="Things it must do on every call.">
            <LineList
              label="Always rule"
              lines={script.must}
              onChange={(must) => patch({ must })}
              placeholder="Confirm the best email before finishing."
              addLabel="Add"
            />
          </Field>
          <Field label="Never" hint="Your own limits, beyond the built-in ones.">
            <LineList
              label="Never rule"
              lines={script.never}
              onChange={(never) => patch({ never })}
              placeholder="Promise a delivery date."
              addLabel="Add"
              tone="danger"
            />
          </Field>
        </div>
      </Block>

      <Block title="How it finishes" description="How to wrap up, and when to get a person involved instead.">
        <div className="space-y-4">
          <TextareaField
            id="script-closing"
            label="Closing"
            rows={2}
            value={script.closing}
            onChange={(closing) => patch({ closing })}
            placeholder="If it is a fit, book thirty minutes with a consultant and confirm the time out loud."
          />
          <TextareaField
            id="script-handoff"
            label="Hand over to a person when"
            rows={2}
            value={script.handoff}
            onChange={(handoff) => patch({ handoff })}
            placeholder="They want to talk contracts or pricing, or they are unhappy."
          />
          <Field label="Call length" htmlFor="script-minutes" hint="Leave blank for no target.">
            <div className="flex items-center gap-2">
              <Input
                id="script-minutes"
                type="number"
                min={1}
                max={120}
                className="w-24"
                value={script.max_minutes ?? ""}
                onChange={(e) =>
                  patch({ max_minutes: e.target.value ? Number(e.target.value) : null })
                }
              />
              <span className="text-sm text-muted-foreground">minutes</span>
            </div>
          </Field>
        </div>
      </Block>

      <Block title="Anything else" description="Free text, passed to the agent as notes from your team.">
        <TextareaField
          id="script-extra"
          label="Notes"
          rows={4}
          value={script.extra}
          onChange={(extra) => patch({ extra })}
          placeholder="Mention the fintech case study if they ask who else we have worked with."
          hint="The safety rules still apply to anything written here."
        />
      </Block>
    </div>
  );
}
