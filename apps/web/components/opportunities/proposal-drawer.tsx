"use client";

import { Button } from "@dracara/ui";
import { useQueryClient } from "@tanstack/react-query";
import { FileText, Paperclip, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { apiFetch } from "@/lib/api";
import { compactPayload } from "@/lib/forms";
import { useApiMutation } from "@/lib/use-api-mutation";
import { EntityDrawer, SelectField, TextField } from "@/components/shared/entity-drawer";

export type ProposalSummary = {
  id: string;
  version: number;
  title: string;
  status: string;
  quoted_price: number | null;
  figma_url?: string | null;
  github_url?: string | null;
  loom_url?: string | null;
  change_notes?: string | null;
  row_version?: number;
};

const STATUS_OPTIONS = [
  { value: "draft", label: "Draft" },
  { value: "sent", label: "Sent" },
  { value: "under_review", label: "Under review" },
  { value: "accepted", label: "Accepted" },
  { value: "rejected", label: "Rejected" },
];

const EMPTY = {
  title: "",
  status: "draft",
  quoted_price: "",
  figma_url: "",
  github_url: "",
  loom_url: "",
  change_notes: "",
};

type Form = typeof EMPTY;

/**
 * Create a proposal version, or move an existing one through its lifecycle.
 *
 * The version number is allocated by the server, so two people drafting at once cannot
 * collide. Only a draft can be deleted: once a proposal has been sent it is part of what the
 * client actually received, and removing it would leave a hole in the history.
 */
export function ProposalDrawer({
  opportunityId,
  proposal,
  trigger,
}: {
  opportunityId: string;
  proposal?: ProposalSummary;
  trigger?: React.ReactNode;
}) {
  const editing = Boolean(proposal);
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<Form>(EMPTY);
  const [file, setFile] = useState<File | null>(null);

  useEffect(() => {
    if (!open) return;
    setFile(null);
    setForm(
      proposal
        ? {
            title: proposal.title ?? "",
            status: proposal.status ?? "draft",
            quoted_price: proposal.quoted_price == null ? "" : String(proposal.quoted_price),
            figma_url: proposal.figma_url ?? "",
            github_url: proposal.github_url ?? "",
            loom_url: proposal.loom_url ?? "",
            change_notes: proposal.change_notes ?? "",
          }
        : EMPTY
    );
  }, [open, proposal]);

  const set = <K extends keyof Form>(key: K, value: string) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["opportunity", opportunityId] });
    qc.invalidateQueries({ queryKey: ["proposals", opportunityId] });
    qc.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const save = useApiMutation({
    errorTitle: editing ? "Could not save proposal" : "Could not create proposal",
    mutationFn: () => {
      const body = compactPayload({
        title: form.title.trim(),
        status: form.status,
        quoted_price: form.quoted_price ? Number(form.quoted_price) : "",
        figma_url: form.figma_url,
        github_url: form.github_url,
        loom_url: form.loom_url,
        change_notes: form.change_notes,
      });
      if (!editing) {
        if (file) {
          // The upload endpoint stores the document and records the version in one call, so
          // a failed upload cannot leave a proposal row pointing at nothing.
          const data = new FormData();
          data.append("file", file);
          data.append("title", form.title.trim());
          return apiFetch(`/opportunities/${opportunityId}/proposals/upload`, {
            method: "POST",
            body: data,
          });
        }
        // The server allocates the version number.
        return apiFetch(`/opportunities/${opportunityId}/proposals`, {
          method: "POST",
          body: JSON.stringify(body),
        });
      }
      return apiFetch(`/proposals/${proposal!.id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      });
    },
    onSuccess: () => {
      invalidate();
      toast.success(editing ? "Proposal updated" : "Proposal created");
      setOpen(false);
    },
  });

  const remove = useApiMutation({
    errorTitle: "Could not delete proposal",
    mutationFn: () =>
      apiFetch(`/proposals/${proposal!.id}`, {
        method: "DELETE",
        headers: proposal!.row_version
          ? { "If-Match": `"${proposal!.row_version}"` }
          : undefined,
      }),
    onSuccess: () => {
      invalidate();
      toast.success("Draft deleted");
      setOpen(false);
    },
  });

  const isDraft = proposal?.status === "draft";

  const defaultTrigger = (
    <Button className="gap-2 bg-[#0B7FB3] hover:bg-[#096892]">
      <Plus className="h-4 w-4" />
      New proposal
    </Button>
  );

  return (
    <EntityDrawer
      open={open}
      onOpenChange={setOpen}
      trigger={trigger ?? defaultTrigger}
      icon={FileText}
      title={editing ? `Proposal v${proposal!.version}` : "New proposal version"}
      description={
        editing
          ? "Marking a proposal sent records the moment it went out, which is what the dashboard's pending count reads."
          : "The version number is assigned by the server, so concurrent drafts cannot collide."
      }
      submitLabel={editing ? "Save changes" : "Create proposal"}
      pendingLabel={editing ? "Saving…" : "Creating…"}
      canSubmit={Boolean(form.title.trim())}
      isPending={save.isPending || remove.isPending}
      onSubmit={() => save.mutate()}
      destructiveAction={
        editing ? (
          <Button
            type="button"
            variant="ghost"
            className="gap-1.5 text-destructive hover:bg-destructive/10 hover:text-destructive disabled:opacity-40"
            disabled={!isDraft || remove.isPending}
            title={
              isDraft
                ? undefined
                : "A proposal that has been sent is part of the deal record; mark it rejected instead."
            }
            onClick={() => remove.mutate()}
          >
            <Trash2 className="h-4 w-4" />
            Delete draft
          </Button>
        ) : undefined
      }
    >
      <TextField
        id="proposal-title"
        label="Title"
        required
        placeholder="Scope and commercials"
        value={form.title}
        onChange={(v) => set("title", v)}
      />

      <div className="grid grid-cols-2 gap-4">
        <SelectField
          id="proposal-status"
          label="Status"
          value={form.status}
          onChange={(v) => set("status", v)}
          options={STATUS_OPTIONS}
        />
        <TextField
          id="proposal-price"
          label="Quoted price"
          type="number"
          min={0}
          step="1000"
          inputMode="numeric"
          placeholder="450000"
          value={form.quoted_price}
          onChange={(v) => set("quoted_price", v)}
        />
      </div>

      <TextField
        id="proposal-figma"
        label="Figma"
        placeholder="https://figma.com/file/…"
        value={form.figma_url}
        onChange={(v) => set("figma_url", v)}
      />
      <TextField
        id="proposal-github"
        label="Repository"
        placeholder="https://github.com/…"
        value={form.github_url}
        onChange={(v) => set("github_url", v)}
      />
      <TextField
        id="proposal-loom"
        label="Walkthrough"
        placeholder="https://loom.com/share/…"
        value={form.loom_url}
        onChange={(v) => set("loom_url", v)}
      />
      {!editing ? (
        <div className="space-y-2">
          <label htmlFor="proposal-file" className="text-xs font-bold uppercase tracking-widest text-muted-foreground">
            Document
          </label>
          <div className="flex items-center gap-2">
            <input
              id="proposal-file"
              type="file"
              accept=".pdf,.doc,.docx,.ppt,.pptx,image/*"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-muted file:px-3 file:py-1.5 file:text-xs file:font-semibold hover:file:bg-muted/70"
            />
            {file ? <Paperclip className="h-4 w-4 shrink-0 text-muted-foreground" /> : null}
          </div>
          <p className="text-xs text-muted-foreground">
            Optional. Attaching one stores it and records this version in a single step.
          </p>
        </div>
      ) : null}

      <TextField
        id="proposal-notes"
        label="What changed"
        placeholder="Reduced scope to two integrations"
        value={form.change_notes}
        onChange={(v) => set("change_notes", v)}
        hint="Shown against this version in the history."
      />
    </EntityDrawer>
  );
}
