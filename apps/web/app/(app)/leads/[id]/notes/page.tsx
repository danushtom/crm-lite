"use client";

import { Button, Card, CardContent, CardHeader, CardTitle } from "@dracara/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useApiMutation } from "@/lib/use-api-mutation";
import { useParams } from "next/navigation";
import { useState } from "react";
import { apiFetch } from "@/lib/api";

export default function IntelligencePage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();

  const { data: bundle } = useQuery({
    queryKey: ["lead", id],
    queryFn: () =>
      apiFetch<{ lead: Record<string, unknown>; lead_intelligence: Record<string, unknown> | null }>(`/leads/${id}`),
  });

  const intel = bundle?.lead_intelligence;

  const fields = [
    "pain_points",
    "tech_stack",
    "budget_hints",
    "decision_makers",
    "competitors_involved",
    "objections_raised",
    "strategic_notes",
  ] as const;

  const [form, setForm] = useState<Record<string, string>>({});

  const save = useApiMutation({
    errorTitle: "Could not save intelligence",    mutationFn: () => apiFetch(`/leads/${id}/intelligence`, { method: "PATCH", body: JSON.stringify(form) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["lead", id] }),
  });

  if (!bundle) return <p className="text-sm text-muted-foreground">Loading…</p>;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">Notes & Intelligence</h2>
        <p className="mt-1 text-sm text-muted-foreground">Detailed context and internal notes for this lead.</p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Communication preference</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          {["email", "linkedin", "phone", "whatsapp", "call"].map((p) => (
            <label key={p} className="flex items-center gap-2 text-sm capitalize">
              <input
                type="radio"
                name="comm"
                defaultChecked={(intel?.comm_preference as string) === p}
                onChange={() => setForm((f) => ({ ...f, comm_preference: p }))}
              />
              {p}
            </label>
          ))}
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        {fields.map((key) => (
          <div key={key} className="space-y-2">
            <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{key.replace(/_/g, " ")}</label>
            <textarea
              className="min-h-[96px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm"
              defaultValue={String(intel?.[key] ?? "")}
              onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
            />
          </div>
        ))}
      </div>
      <Button onClick={() => save.mutate()} disabled={save.isPending}>
        Save intelligence
      </Button>
      {save.isError ? <p className="text-sm text-destructive">{(save.error as Error).message}</p> : null}
    </div>
  );
}
