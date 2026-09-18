"use client";

import { Button, Input } from "@dracara/ui";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiFetch, apiList } from "@/lib/api";
import { selectClass } from "@/components/shared/entity-drawer";
import {
  BulkActionBar,
  BulkDeleteButton,
  useBulkAction,
  type RowSelection,
} from "@/components/shared/bulk-actions";

type Me = { id: string; is_admin?: boolean };
type Teammate = { id: string; full_name: string | null; email: string | null; is_active: boolean };

/** Reassign (full-access roles only, as the API enforces), tag, and delete the selected leads. */
export function LeadBulkActions({ selection }: { selection: RowSelection }) {
  const bulk = useBulkAction("leads", selection, "lead");
  const [tag, setTag] = useState("");

  const { data: me } = useQuery({ queryKey: ["me"], queryFn: () => apiFetch<Me>("/auth/me") });
  const { data: team = [] } = useQuery({
    queryKey: ["agents", "bulk-reassign"],
    queryFn: () => apiList<Teammate>("/agents?limit=200"),
    enabled: Boolean(me?.is_admin) && selection.count > 0,
  });

  const tags = tag
    .split(/[;,]/)
    .map((t) => t.trim())
    .filter(Boolean);

  return (
    <BulkActionBar count={selection.count} noun="lead" onClear={selection.clear}>
      {me?.is_admin ? (
        <select
          aria-label="Reassign selected leads to"
          className={`${selectClass} h-8 w-44 text-sm`}
          value=""
          disabled={bulk.isPending}
          onChange={(e) => e.target.value && bulk.mutate({ action: "reassign", owner_id: e.target.value })}
        >
          <option value="">Reassign to…</option>
          {team
            .filter((t) => t.is_active)
            .map((t) => (
              <option key={t.id} value={t.id}>
                {t.full_name || t.email}
              </option>
            ))}
        </select>
      ) : null}
      <form
        className="flex items-center gap-1"
        onSubmit={(e) => {
          e.preventDefault();
          if (tags.length) bulk.mutate({ action: "add_tags", tags }, { onSuccess: () => setTag("") });
        }}
      >
        <Input
          aria-label="Tags to add or remove"
          placeholder="Tag"
          className="h-8 w-28 text-sm"
          value={tag}
          onChange={(e) => setTag(e.target.value)}
        />
        <Button type="submit" size="sm" variant="outline" disabled={!tags.length || bulk.isPending}>
          Add tag
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          disabled={!tags.length || bulk.isPending}
          onClick={() => bulk.mutate({ action: "remove_tags", tags }, { onSuccess: () => setTag("") })}
        >
          Remove
        </Button>
      </form>
      <BulkDeleteButton
        count={selection.count}
        pending={bulk.isPending}
        onConfirm={() => bulk.mutate({ action: "delete" })}
      />
    </BulkActionBar>
  );
}
