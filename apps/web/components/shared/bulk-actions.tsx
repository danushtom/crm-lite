"use client";

/**
 * Multi-select for list pages, and the action bar that appears once something is selected.
 *
 * Selection is by id and survives paging and sorting; ids that drop out of the current data
 * (deleted, filtered away by search) are pruned so the count never includes rows the user
 * cannot see. Actions go to POST /bulk/{kind}, which runs them as the user and reports each
 * record separately -- so a partial failure is reported as such, not as success or total failure.
 */

import { Button, cn } from "@dracara/ui";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { apiFetch } from "@/lib/api";
import { useApiMutation } from "@/lib/use-api-mutation";

export type BulkKind = "leads" | "contacts" | "companies";

export type BulkRequest =
  | { action: "delete" }
  | { action: "reassign"; owner_id: string }
  | { action: "add_tags" | "remove_tags"; tags: string[] };

type BulkResult = {
  succeeded: number;
  failed: number;
  results: { id: string; ok: boolean; message: string | null }[];
};

export function useRowSelection(availableIds: string[]) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const available = useMemo(() => new Set(availableIds), [availableIds]);

  useEffect(() => {
    setSelected((current) => {
      const kept = new Set([...current].filter((id) => available.has(id)));
      return kept.size === current.size ? current : kept;
    });
  }, [available]);

  return {
    selected,
    count: selected.size,
    isSelected: (id: string) => selected.has(id),
    toggle: (id: string) =>
      setSelected((current) => {
        const next = new Set(current);
        if (next.has(id)) next.delete(id);
        else next.add(id);
        return next;
      }),
    setMany: (ids: string[], on: boolean) =>
      setSelected((current) => {
        const next = new Set(current);
        for (const id of ids) {
          if (on) next.add(id);
          else next.delete(id);
        }
        return next;
      }),
    clear: () => setSelected(new Set()),
  };
}

export type RowSelection = ReturnType<typeof useRowSelection>;

/** Header checkbox: selects or clears the rows on the current page; indeterminate when partial. */
export function SelectPageCheckbox({ selection, pageIds, label }: { selection: RowSelection; pageIds: string[]; label: string }) {
  const ref = useRef<HTMLInputElement>(null);
  const onPage = pageIds.filter((id) => selection.isSelected(id)).length;
  const all = pageIds.length > 0 && onPage === pageIds.length;
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = onPage > 0 && !all;
  }, [onPage, all]);
  return (
    <input
      ref={ref}
      type="checkbox"
      aria-label={`Select all ${label} on this page`}
      className="h-3.5 w-3.5 rounded border-border"
      checked={all}
      disabled={!pageIds.length}
      onChange={(e) => selection.setMany(pageIds, e.target.checked)}
    />
  );
}

export function RowCheckbox({ selection, id, label }: { selection: RowSelection; id: string; label: string }) {
  return (
    <input
      type="checkbox"
      aria-label={`Select ${label}`}
      className="h-3.5 w-3.5 rounded border-border"
      checked={selection.isSelected(id)}
      onChange={() => selection.toggle(id)}
      onClick={(e) => e.stopPropagation()}
    />
  );
}

export function useBulkAction(kind: BulkKind, selection: RowSelection, noun: string) {
  const qc = useQueryClient();
  return useApiMutation({
    mutationFn: (request: BulkRequest) =>
      apiFetch<BulkResult>(`/bulk/${kind}`, {
        method: "POST",
        body: JSON.stringify({ ...request, ids: [...selection.selected] }),
      }),
    onSuccess: (result, request) => {
      qc.invalidateQueries({ queryKey: [kind] });
      qc.invalidateQueries({ queryKey: ["recently-deleted"] });
      const verb = request.action === "delete" ? "deleted" : request.action === "reassign" ? "reassigned" : "updated";
      const done = `${result.succeeded} ${noun}${result.succeeded === 1 ? "" : "s"} ${verb}`;
      if (!result.failed) {
        toast.success(done);
        selection.clear();
        return;
      }
      // Keep only the failures selected, so the user can see and retry exactly those.
      const failedIds = result.results.filter((r) => !r.ok).map((r) => r.id);
      selection.clear();
      selection.setMany(failedIds, true);
      const reasons = [...new Set(result.results.filter((r) => !r.ok).map((r) => r.message).filter(Boolean))];
      toast.warning(`${done}, ${result.failed} failed`, {
        description: `${reasons.slice(0, 2).join(" · ")}${reasons.length > 2 ? " …" : ""} The failed ones are still selected.`,
      });
    },
    errorTitle: "Bulk action failed",
  });
}

/** The sticky bar shown while rows are selected. `children` are the page's action controls. */
export function BulkActionBar({
  count,
  noun,
  onClear,
  children,
}: {
  count: number;
  noun: string;
  onClear: () => void;
  children: ReactNode;
}) {
  if (!count) return null;
  return (
    <div
      role="toolbar"
      aria-label={`Actions for ${count} selected ${noun}s`}
      className="sticky bottom-4 z-20 mx-auto flex w-fit max-w-full flex-wrap items-center gap-2 rounded-xl border border-border bg-card px-3 py-2 shadow-lg"
    >
      <span className="px-1 text-sm font-medium tabular-nums">
        {count} {noun}
        {count === 1 ? "" : "s"} selected
      </span>
      {children}
      <Button variant="ghost" size="sm" onClick={onClear} aria-label="Clear selection">
        <X className="h-3.5 w-3.5" />
      </Button>
    </div>
  );
}

/** Delete with a second click to confirm -- deleting many rows deserves a beat, not a modal. */
export function BulkDeleteButton({ count, pending, onConfirm }: { count: number; pending: boolean; onConfirm: () => void }) {
  const [armed, setArmed] = useState(false);
  useEffect(() => {
    if (!armed) return;
    const timer = window.setTimeout(() => setArmed(false), 4000);
    return () => window.clearTimeout(timer);
  }, [armed]);
  return (
    <Button
      variant="ghost"
      size="sm"
      disabled={pending}
      className={cn("gap-1.5 text-destructive hover:bg-destructive/10 hover:text-destructive", armed && "bg-destructive/10")}
      onClick={() => {
        if (armed) {
          setArmed(false);
          onConfirm();
        } else {
          setArmed(true);
        }
      }}
    >
      {pending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
      {armed ? `Confirm delete ${count}` : "Delete"}
    </Button>
  );
}

/** For lists whose only bulk action is delete (contacts, companies). */
export function DeleteOnlyBulkActions({ kind, noun, selection }: { kind: BulkKind; noun: string; selection: RowSelection }) {
  const bulk = useBulkAction(kind, selection, noun);
  return (
    <BulkActionBar count={selection.count} noun={noun} onClear={selection.clear}>
      <BulkDeleteButton count={selection.count} pending={bulk.isPending} onConfirm={() => bulk.mutate({ action: "delete" })} />
    </BulkActionBar>
  );
}
