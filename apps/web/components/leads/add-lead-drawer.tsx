"use client";

import type { CompanyRow, ContactRow, LeadRow } from "@dracara/types";

/** POST /leads returns the lead together with the pursuit it opened. */
type LeadCreated = { lead: LeadRow; opportunities: { id: string }[] };
import {
  Button,
  Input,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@dracara/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Plus, Target } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { apiFetch, apiListAll } from "@/lib/api";
import { describeError } from "@/lib/use-api-mutation";
import {
  CURRENCY_OPTIONS,
  LEAD_SOURCE_OPTIONS,
  LEAD_STAGE_OPTIONS,
  PROJECT_TYPE_OPTIONS,
  compactPayload,
  parseTags,
} from "@/lib/forms";

const selectClass =
  "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50";

const labelClass = "text-xs font-bold uppercase tracking-widest text-muted-foreground";

const EMPTY_FORM = {
  company_id: "",
  primary_contact_id: "",
  project_type: "",
  lead_source: "",
  stage: "prospect",
  quoted_value: "",
  currency: "INR",
  deal_probability: "50",
  next_followup_date: "",
  tags: "",
};

export function AddLeadDrawer() {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const qc = useQueryClient();

  const set = <K extends keyof typeof EMPTY_FORM>(key: K, value: string) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const { data: companies = [] } = useQuery({
    queryKey: ["companies", "add-lead"],
    queryFn: () => apiListAll<CompanyRow>("/companies"),
    enabled: open,
  });

  const { data: contacts = [] } = useQuery({
    queryKey: ["contacts", "add-lead"],
    queryFn: () => apiListAll<ContactRow>("/contacts"),
    enabled: open,
  });

  // A lead's primary contact must belong to the selected company.
  const companyContacts = useMemo(
    () => contacts.filter((c) => c.company_id === form.company_id),
    [contacts, form.company_id]
  );

  const createLead = useMutation({
    mutationFn: () => {
      // The lead carries qualification data; stage and commercials belong to the pursuit
      // opened alongside it, which the API creates in the same call.
      const payload = compactPayload({
        company_id: form.company_id,
        primary_contact_id: form.primary_contact_id,
        project_type: form.project_type,
        lead_source: form.lead_source,
        next_followup_date: form.next_followup_date,
        tags: parseTags(form.tags),
      });
      const opportunity = compactPayload({
        stage: form.stage,
        currency: form.currency,
        quoted_value: form.quoted_value ? Number(form.quoted_value) : "",
        deal_probability: form.deal_probability ? Number(form.deal_probability) : "",
      });
      return apiFetch<LeadCreated>("/leads", {
        method: "POST",
        body: JSON.stringify({ ...payload, opportunity }),
      });
    },
    onSuccess: (created) => {
      // The lead's opportunity and intelligence rows are created by database triggers,
      // so the pipeline and dashboard views are stale too.
      qc.invalidateQueries({ queryKey: ["leads"] });
      qc.invalidateQueries({ queryKey: ["opportunities"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success("Lead created", {
        description: companies.find((c) => c.id === created.lead.company_id)?.name ?? undefined,
      });
      setForm(EMPTY_FORM);
      setOpen(false);
    },
    onError: (error: Error) =>
      toast.error("Could not create lead", { description: describeError(error) }),
  });

  const probability = Number(form.deal_probability);
  const probabilityInvalid =
    form.deal_probability !== "" && (Number.isNaN(probability) || probability < 0 || probability > 100);

  const canSubmit =
    Boolean(form.company_id && form.project_type && form.lead_source) &&
    !probabilityInvalid &&
    !createLead.isPending;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    createLead.mutate();
  };

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button
          size="sm"
          className="h-8 gap-1.5 rounded-md bg-[#0A1128] px-3 text-xs font-semibold text-white hover:bg-[#1a2a53]"
        >
          <Plus className="h-3.5 w-3.5" />
          Add Lead
        </Button>
      </SheetTrigger>

      <SheetContent
        side="right"
        className="w-[400px] overflow-y-auto border-l border-border/60 sm:w-[540px]"
      >
        <SheetHeader className="border-b border-border/50 pb-4">
          <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-indigo-50 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-400">
            <Target className="h-5 w-5" />
          </div>
          <SheetTitle className="text-xl">Add New Lead</SheetTitle>
          <SheetDescription>
            Creates the lead plus its pipeline card and CRM intelligence panel.
          </SheetDescription>
        </SheetHeader>

        <form onSubmit={handleSubmit} className="space-y-6 py-6">
          <div className="space-y-4">
            <div className="space-y-2">
              <label htmlFor="lead-company" className={labelClass}>
                Company <span className="text-destructive">*</span>
              </label>
              <select
                id="lead-company"
                className={selectClass}
                value={form.company_id}
                onChange={(e) => {
                  set("company_id", e.target.value);
                  set("primary_contact_id", "");
                }}
                required
              >
                <option value="">Select a company</option>
                {companies.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-2">
              <label htmlFor="lead-contact" className={labelClass}>
                Primary Contact
              </label>
              <select
                id="lead-contact"
                className={selectClass}
                value={form.primary_contact_id}
                onChange={(e) => set("primary_contact_id", e.target.value)}
                disabled={!form.company_id}
              >
                <option value="">
                  {!form.company_id
                    ? "Select a company first"
                    : companyContacts.length === 0
                      ? "No contacts at this company"
                      : "Select a contact"}
                </option>
                {companyContacts.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.full_name}
                    {c.role ? ` — ${c.role}` : ""}
                  </option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <label htmlFor="lead-project-type" className={labelClass}>
                  Project Type <span className="text-destructive">*</span>
                </label>
                <select
                  id="lead-project-type"
                  className={selectClass}
                  value={form.project_type}
                  onChange={(e) => set("project_type", e.target.value)}
                  required
                >
                  <option value="">Select type</option>
                  {PROJECT_TYPE_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-2">
                <label htmlFor="lead-source" className={labelClass}>
                  Source <span className="text-destructive">*</span>
                </label>
                <select
                  id="lead-source"
                  className={selectClass}
                  value={form.lead_source}
                  onChange={(e) => set("lead_source", e.target.value)}
                  required
                >
                  <option value="">Select source</option>
                  {LEAD_SOURCE_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="space-y-2">
              <label htmlFor="lead-stage" className={labelClass}>
                Stage
              </label>
              <select
                id="lead-stage"
                className={selectClass}
                value={form.stage}
                onChange={(e) => set("stage", e.target.value)}
              >
                {LEAD_STAGE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-3 gap-4">
              <div className="col-span-2 space-y-2">
                <label htmlFor="lead-value" className={labelClass}>
                  Estimated Value
                </label>
                <Input
                  id="lead-value"
                  type="number"
                  min={0}
                  step="1000"
                  inputMode="numeric"
                  placeholder="1500000"
                  value={form.quoted_value}
                  onChange={(e) => set("quoted_value", e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <label htmlFor="lead-currency" className={labelClass}>
                  Currency
                </label>
                <select
                  id="lead-currency"
                  className={selectClass}
                  value={form.currency}
                  onChange={(e) => set("currency", e.target.value)}
                >
                  {CURRENCY_OPTIONS.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <label htmlFor="lead-probability" className={labelClass}>
                  Probability (%)
                </label>
                <Input
                  id="lead-probability"
                  type="number"
                  min={0}
                  max={100}
                  inputMode="numeric"
                  value={form.deal_probability}
                  onChange={(e) => set("deal_probability", e.target.value)}
                  aria-invalid={probabilityInvalid}
                />
                {probabilityInvalid ? (
                  <p className="text-xs text-destructive">Must be between 0 and 100.</p>
                ) : null}
              </div>
              <div className="space-y-2">
                <label htmlFor="lead-followup" className={labelClass}>
                  Next Follow-up
                </label>
                <Input
                  id="lead-followup"
                  type="date"
                  value={form.next_followup_date}
                  onChange={(e) => set("next_followup_date", e.target.value)}
                />
              </div>
            </div>

            <div className="space-y-2">
              <label htmlFor="lead-tags" className={labelClass}>
                Tags
              </label>
              <Input
                id="lead-tags"
                placeholder="enterprise, inbound, q3"
                value={form.tags}
                onChange={(e) => set("tags", e.target.value)}
              />
              <p className="text-xs text-muted-foreground">Separate with commas.</p>
            </div>
          </div>

          <SheetFooter className="border-t border-border/50 pt-6">
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              type="submit"
              className="bg-[#0A1128] text-white hover:bg-[#1a2a53]"
              disabled={!canSubmit}
            >
              {createLead.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Creating…
                </>
              ) : (
                "Create Lead"
              )}
            </Button>
          </SheetFooter>
        </form>
      </SheetContent>
    </Sheet>
  );
}
