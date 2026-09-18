"use client";

import type { CompanyRow } from "@dracara/types";
import { Button } from "@dracara/ui";
import { useQueryClient } from "@tanstack/react-query";
import { Building2, Pencil, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { apiFetch } from "@/lib/api";
import { compactPayload } from "@/lib/forms";
import { useApiMutation } from "@/lib/use-api-mutation";
import { EntityDrawer, SelectField, TextField } from "@/components/shared/entity-drawer";

const SEGMENTS = [
  { value: "sme", label: "SME" },
  { value: "startup", label: "Startup" },
  { value: "enterprise", label: "Enterprise" },
];

const EMPTY = {
  name: "",
  industry: "",
  size: "",
  website: "",
  location: "",
  linkedin_url: "",
  segment: "",
};

type Form = typeof EMPTY;

function toForm(company: CompanyRow): Form {
  return {
    name: company.name ?? "",
    industry: company.industry ?? "",
    size: company.size ?? "",
    website: company.website ?? "",
    location: company.location ?? "",
    linkedin_url: company.linkedin_url ?? "",
    segment: company.segment ?? "",
  };
}

/**
 * Create or edit a company.
 *
 * Pass `company` to edit; omit it to create. Editing sends `If-Match` with the row's version,
 * so a stale form is refused with a message rather than quietly overwriting whatever someone
 * else changed in the meantime.
 */
export function CompanyDrawer({ company }: { company?: CompanyRow }) {
  const editing = Boolean(company);
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<Form>(company ? toForm(company) : EMPTY);

  // Reopening after someone else's edit should show the current values, not the stale ones.
  useEffect(() => {
    if (open && company) setForm(toForm(company));
  }, [open, company]);

  const set = <K extends keyof Form>(key: K, value: string) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["companies"] });
    qc.invalidateQueries({ queryKey: ["leads"] });
  };

  const save = useApiMutation({
    errorTitle: editing ? "Could not save company" : "Could not create company",
    mutationFn: () => {
      const payload = compactPayload(form);
      if (!editing) {
        return apiFetch<CompanyRow>("/companies", {
          method: "POST",
          body: JSON.stringify(payload),
        });
      }
      return apiFetch<CompanyRow>(`/companies/${company!.id}`, {
        method: "PATCH",
        headers: { "If-Match": `"${company!.version}"` },
        body: JSON.stringify(payload),
      });
    },
    onSuccess: (saved) => {
      invalidate();
      toast.success(editing ? "Company updated" : "Company created", {
        description: saved.name,
      });
      if (!editing) setForm(EMPTY);
      setOpen(false);
    },
  });

  const remove = useApiMutation({
    errorTitle: "Could not delete company",
    mutationFn: () =>
      apiFetch(`/companies/${company!.id}`, {
        method: "DELETE",
        headers: { "If-Match": `"${company!.version}"` },
      }),
    onSuccess: () => {
      invalidate();
      toast.success("Company deleted", { description: "Restore it from Settings → Recently deleted." });
      setOpen(false);
    },
  });

  const trigger = editing ? (
    <Button variant="ghost" size="icon" className="h-8 w-8" aria-label={`Edit ${company!.name}`}>
      <Pencil className="h-3.5 w-3.5" />
    </Button>
  ) : (
    <Button
      size="sm"
      className="h-8 gap-1.5 rounded-md bg-[#0A1128] px-3 text-xs font-semibold text-white hover:bg-[#1a2a53]"
    >
      <Plus className="h-3.5 w-3.5" />
      Add Company
    </Button>
  );

  return (
    <EntityDrawer
      open={open}
      onOpenChange={setOpen}
      trigger={trigger}
      icon={Building2}
      title={editing ? "Edit company" : "Add a company"}
      description={
        editing
          ? "Changes are rejected if someone else edited this company since you opened it."
          : "Companies group the contacts and leads you work with."
      }
      submitLabel={editing ? "Save changes" : "Create company"}
      pendingLabel={editing ? "Saving…" : "Creating…"}
      canSubmit={Boolean(form.name.trim())}
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
        id="company-name"
        label="Company name"
        required
        placeholder="Acme Industries"
        value={form.name}
        onChange={(v) => set("name", v)}
      />

      <div className="grid grid-cols-2 gap-4">
        <TextField
          id="company-industry"
          label="Industry"
          placeholder="Logistics"
          value={form.industry}
          onChange={(v) => set("industry", v)}
        />
        <SelectField
          id="company-segment"
          label="Segment"
          placeholder="Not set"
          value={form.segment}
          onChange={(v) => set("segment", v)}
          options={SEGMENTS}
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <TextField
          id="company-size"
          label="Headcount"
          placeholder="11-50"
          value={form.size}
          onChange={(v) => set("size", v)}
        />
        <TextField
          id="company-location"
          label="Location"
          placeholder="Chennai, India"
          value={form.location}
          onChange={(v) => set("location", v)}
        />
      </div>

      <TextField
        id="company-website"
        label="Website"
        placeholder="https://acme.example"
        value={form.website}
        onChange={(v) => set("website", v)}
      />
      <TextField
        id="company-linkedin"
        label="LinkedIn"
        placeholder="https://linkedin.com/company/acme"
        value={form.linkedin_url}
        onChange={(v) => set("linkedin_url", v)}
      />

      {editing ? (
        <p className="text-xs text-muted-foreground">
          Deleting hides the company from every view but keeps its history. A company with
          active leads cannot be deleted until they are reassigned.
        </p>
      ) : null}
    </EntityDrawer>
  );
}
