"use client";

import type { LeadStage, OpportunityRow } from "@dracara/types";
import { Button, Input } from "@dracara/ui";
import { useQueryClient } from "@tanstack/react-query";
import { KanbanSquare, Pencil, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { apiFetch } from "@/lib/api";
import { CURRENCY_OPTIONS, LEAD_STAGE_OPTIONS, compactPayload } from "@/lib/forms";
import { useApiMutation } from "@/lib/use-api-mutation";
import { EntityDrawer, SelectField, TextField } from "@/components/shared/entity-drawer";

const STATUS_OPTIONS = [
  { value: "active", label: "Active" },
  { value: "won", label: "Won" },
  { value: "lost", label: "Lost" },
  { value: "on_hold", label: "On hold" },
];

const EMPTY = {
  title: "",
  stage: "prospect" as LeadStage | string,
  status: "active",
  quoted_value: "",
  currency: "INR",
  deal_probability: "50",
  timeline_weeks: "",
  tech_stack: "",
};

type Form = typeof EMPTY;

function toForm(o: OpportunityRow): Form {
  return {
    title: o.title ?? "",
    stage: o.stage,
    status: o.status,
    quoted_value: o.quoted_value == null ? "" : String(o.quoted_value),
    currency: o.currency ?? "INR",
    deal_probability: String(o.deal_probability ?? 50),
    timeline_weeks: o.timeline_weeks == null ? "" : String(o.timeline_weeks),
    tech_stack: o.tech_stack ?? "",
  };
}

/**
 * Create or edit a pursuit.
 *
 * With `leadId` this opens a further pursuit against that lead — the retainer after the
 * build. With `opportunity` it edits an existing one. A lead may hold only one *active*
 * pursuit at a time; the API says so plainly if you try to open a second.
 */
export function OpportunityDrawer({
  opportunity,
  leadId,
  trigger,
}: {
  opportunity?: OpportunityRow;
  leadId?: string;
  trigger?: React.ReactNode;
}) {
  const editing = Boolean(opportunity);
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<Form>(opportunity ? toForm(opportunity) : EMPTY);

  useEffect(() => {
    if (open && opportunity) setForm(toForm(opportunity));
  }, [open, opportunity]);

  const set = <K extends keyof Form>(key: K, value: string) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["opportunities"] });
    qc.invalidateQueries({ queryKey: ["opportunity"] });
    qc.invalidateQueries({ queryKey: ["opportunity-by-lead"] });
    qc.invalidateQueries({ queryKey: ["leads"] });
    qc.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const probability = Number(form.deal_probability);
  const probabilityError =
    form.deal_probability !== "" && (Number.isNaN(probability) || probability < 0 || probability > 100)
      ? "Must be between 0 and 100."
      : null;

  const save = useApiMutation({
    errorTitle: editing ? "Could not save opportunity" : "Could not open opportunity",
    mutationFn: () => {
      const body = compactPayload({
        title: form.title.trim(),
        stage: form.stage,
        currency: form.currency,
        quoted_value: form.quoted_value ? Number(form.quoted_value) : "",
        deal_probability: form.deal_probability ? Number(form.deal_probability) : "",
        timeline_weeks: form.timeline_weeks ? Number(form.timeline_weeks) : "",
        tech_stack: form.tech_stack,
        ...(editing ? { status: form.status } : {}),
      });

      if (!editing) {
        return apiFetch<OpportunityRow>(`/leads/${leadId}/opportunities`, {
          method: "POST",
          body: JSON.stringify(body),
        });
      }
      return apiFetch<OpportunityRow>(`/opportunities/${opportunity!.id}`, {
        method: "PATCH",
        headers: { "If-Match": `"${opportunity!.version}"` },
        body: JSON.stringify(body),
      });
    },
    onSuccess: (saved) => {
      invalidate();
      toast.success(editing ? "Opportunity updated" : "Opportunity opened", {
        description: saved.title,
      });
      setOpen(false);
    },
  });

  const remove = useApiMutation({
    errorTitle: "Could not delete opportunity",
    mutationFn: () =>
      apiFetch(`/opportunities/${opportunity!.id}`, {
        method: "DELETE",
        headers: { "If-Match": `"${opportunity!.version}"` },
      }),
    onSuccess: () => {
      invalidate();
      toast.success("Opportunity deleted", { description: "Restore it from Settings → Recently deleted." });
      setOpen(false);
    },
  });

  const defaultTrigger = (
    <Button variant="ghost" size="icon" className="h-8 w-8" aria-label="Edit opportunity">
      <Pencil className="h-3.5 w-3.5" />
    </Button>
  );

  return (
    <EntityDrawer
      open={open}
      onOpenChange={setOpen}
      trigger={trigger ?? defaultTrigger}
      icon={KanbanSquare}
      title={editing ? "Edit opportunity" : "Open an opportunity"}
      description={
        editing
          ? "Stage, value and probability all feed the priority score, which is recalculated on save."
          : "A further pursuit against this lead — the retainer after the build. Only one may be active at a time."
      }
      submitLabel={editing ? "Save changes" : "Open opportunity"}
      pendingLabel={editing ? "Saving…" : "Opening…"}
      canSubmit={Boolean(form.title.trim()) && !probabilityError}
      isPending={save.isPending || remove.isPending}
      onSubmit={() => save.mutate()}
      destructiveAction={
        editing ? (
          <Button
            type="button"
            variant="ghost"
            className="gap-1.5 text-destructive hover:bg-destructive/10 hover:text-destructive"
            disabled={remove.isPending}
            onClick={() => remove.mutate()}
          >
            <Trash2 className="h-4 w-4" />
            Delete
          </Button>
        ) : undefined
      }
    >
      <TextField
        id="opp-title"
        label="Title"
        required
        placeholder="MVP build"
        value={form.title}
        onChange={(v) => set("title", v)}
      />

      <div className="grid grid-cols-2 gap-4">
        <SelectField
          id="opp-stage"
          label="Stage"
          value={String(form.stage)}
          onChange={(v) => set("stage", v)}
          options={LEAD_STAGE_OPTIONS}
        />
        {editing ? (
          <SelectField
            id="opp-status"
            label="Status"
            value={form.status}
            onChange={(v) => set("status", v)}
            options={STATUS_OPTIONS}
            hint="Closing frees the lead to open another."
          />
        ) : (
          <div />
        )}
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div className="col-span-2">
          <TextField
            id="opp-value"
            label="Quoted value"
            type="number"
            min={0}
            step="1000"
            inputMode="numeric"
            placeholder="1500000"
            value={form.quoted_value}
            onChange={(v) => set("quoted_value", v)}
          />
        </div>
        <SelectField
          id="opp-currency"
          label="Currency"
          value={form.currency}
          onChange={(v) => set("currency", v)}
          options={CURRENCY_OPTIONS.map((c) => ({ value: c, label: c }))}
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <TextField
          id="opp-probability"
          label="Probability (%)"
          type="number"
          min={0}
          max={100}
          inputMode="numeric"
          value={form.deal_probability}
          onChange={(v) => set("deal_probability", v)}
          error={probabilityError}
        />
        <TextField
          id="opp-timeline"
          label="Timeline (weeks)"
          type="number"
          min={0}
          inputMode="numeric"
          placeholder="12"
          value={form.timeline_weeks}
          onChange={(v) => set("timeline_weeks", v)}
        />
      </div>

      <TextField
        id="opp-stack"
        label="Tech stack"
        placeholder="Next.js, FastAPI, Postgres"
        value={form.tech_stack}
        onChange={(v) => set("tech_stack", v)}
      />
    </EntityDrawer>
  );
}
