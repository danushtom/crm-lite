"use client";

import type { CompanyRow, ContactRow } from "@dracara/types";
import { Button } from "@dracara/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Trash2, UserPlus } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { apiFetch, apiListAll } from "@/lib/api";
import { LEAD_SOURCE_OPTIONS, compactPayload } from "@/lib/forms";
import { useApiMutation } from "@/lib/use-api-mutation";
import { EntityDrawer, SelectField, TextField } from "@/components/shared/entity-drawer";

const EMPTY = {
  full_name: "",
  email: "",
  phone: "",
  linkedin_url: "",
  company_id: "",
  role: "",
  source: "",
};

type Form = typeof EMPTY;

function toForm(contact: ContactRow): Form {
  return {
    full_name: contact.full_name ?? "",
    email: contact.email ?? "",
    phone: contact.phone ?? "",
    linkedin_url: contact.linkedin_url ?? "",
    company_id: contact.company_id ?? "",
    role: contact.role ?? "",
    source: contact.source ?? "",
  };
}

/**
 * Create or edit a contact.
 *
 * Pass `contact` to edit; omit it to create. Optional fields are omitted rather than sent as
 * empty strings — the API validates strictly, and `source: ""` is not a valid enum value.
 */
export function ContactDrawer({ contact }: { contact?: ContactRow }) {
  const editing = Boolean(contact);
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<Form>(contact ? toForm(contact) : EMPTY);

  useEffect(() => {
    if (open && contact) setForm(toForm(contact));
  }, [open, contact]);

  const set = <K extends keyof Form>(key: K, value: string) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const { data: companies = [] } = useQuery({
    queryKey: ["companies", "contact-drawer"],
    queryFn: () => apiListAll<CompanyRow>("/companies"),
    enabled: open,
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["contacts"] });
    qc.invalidateQueries({ queryKey: ["leads"] });
  };

  const save = useApiMutation({
    errorTitle: editing ? "Could not save contact" : "Could not create contact",
    mutationFn: () => {
      const payload = compactPayload(form);
      if (!editing) {
        return apiFetch<ContactRow>("/contacts", {
          method: "POST",
          body: JSON.stringify(payload),
        });
      }
      // company_id is fixed once a contact exists; moving someone between companies would
      // silently rewrite which leads can see them.
      const { company_id: _ignored, ...editable } = payload;
      return apiFetch<ContactRow>(`/contacts/${contact!.id}`, {
        method: "PATCH",
        headers: { "If-Match": `"${contact!.version}"` },
        body: JSON.stringify(editable),
      });
    },
    onSuccess: (saved) => {
      invalidate();
      toast.success(editing ? "Contact updated" : "Contact created", {
        description: saved.full_name,
      });
      if (!editing) setForm(EMPTY);
      setOpen(false);
    },
  });

  const remove = useApiMutation({
    errorTitle: "Could not delete contact",
    mutationFn: () =>
      apiFetch(`/contacts/${contact!.id}`, {
        method: "DELETE",
        headers: { "If-Match": `"${contact!.version}"` },
      }),
    onSuccess: () => {
      invalidate();
      toast.success("Contact deleted", { description: "Their history is kept." });
      setOpen(false);
    },
  });

  const trigger = editing ? (
    <Button variant="outline" size="sm" className="h-8 gap-1.5 text-xs">
      <Pencil className="h-3.5 w-3.5" />
      Edit
    </Button>
  ) : (
    <Button
      size="sm"
      className="h-8 gap-1.5 rounded-md bg-[#0A1128] px-3 text-xs font-semibold text-white hover:bg-[#1a2a53]"
    >
      <Plus className="h-3.5 w-3.5" />
      Add Contact
    </Button>
  );

  return (
    <EntityDrawer
      open={open}
      onOpenChange={setOpen}
      trigger={trigger}
      icon={editing ? Pencil : UserPlus}
      title={editing ? "Edit contact" : "Add a contact"}
      description={
        editing
          ? "A contact who is the primary contact on a lead cannot be deleted until that lead is reassigned."
          : "People at the companies you work with."
      }
      submitLabel={editing ? "Save changes" : "Create contact"}
      pendingLabel={editing ? "Saving…" : "Creating…"}
      canSubmit={Boolean(form.full_name.trim() && form.company_id)}
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
        id="contact-name"
        label="Full name"
        required
        placeholder="Jane Doe"
        value={form.full_name}
        onChange={(v) => set("full_name", v)}
      />

      <SelectField
        id="contact-company"
        label="Company"
        required
        placeholder="Select a company"
        value={form.company_id}
        onChange={(v) => set("company_id", v)}
        options={companies.map((c) => ({ value: c.id, label: c.name }))}
        disabled={editing}
        hint={editing ? "A contact stays with the company they were created against." : undefined}
      />

      <div className="grid grid-cols-2 gap-4">
        <TextField
          id="contact-email"
          label="Email"
          type="email"
          placeholder="jane@example.com"
          value={form.email}
          onChange={(v) => set("email", v)}
        />
        <TextField
          id="contact-phone"
          label="Phone"
          placeholder="+91 99887 76655"
          value={form.phone}
          onChange={(v) => set("phone", v)}
        />
      </div>

      <TextField
        id="contact-role"
        label="Role"
        placeholder="CTO / Founder"
        value={form.role}
        onChange={(v) => set("role", v)}
      />

      <SelectField
        id="contact-source"
        label="Source"
        placeholder="Not set"
        value={form.source}
        onChange={(v) => set("source", v)}
        options={LEAD_SOURCE_OPTIONS}
      />

      <TextField
        id="contact-linkedin"
        label="LinkedIn"
        placeholder="https://linkedin.com/in/jane-doe"
        value={form.linkedin_url}
        onChange={(v) => set("linkedin_url", v)}
      />
    </EntityDrawer>
  );
}
