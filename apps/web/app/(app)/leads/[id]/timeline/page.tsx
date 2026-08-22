"use client";

import { Button, Card, CardContent } from "@dracara/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useApiMutation } from "@/lib/use-api-mutation";
import { useParams } from "next/navigation";
import { useState } from "react";
import { apiFetch, apiList } from "@/lib/api";

export default function TimelinePage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();

  const { data: rows = [], isLoading } = useQuery({
    queryKey: ["activities", id],
    queryFn: () => apiList<Record<string, unknown>>(`/leads/${id}/activities`),
  });

  const [description, setDescription] = useState("");
  const [type, setType] = useState("note");

  const create = useApiMutation({
    errorTitle: "Could not log activity",    mutationFn: () =>
      apiFetch(`/leads/${id}/activities`, {
        method: "POST",
        body: JSON.stringify({ type, description }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["activities", id] });
      setDescription("");
    },
  });

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">Interactions</h2>
        <p className="mt-1 text-sm text-muted-foreground">Full history of touchpoints and system events for this lead.</p>
      </div>

      <Card>
        <CardContent className="space-y-3 p-4">
          <div className="flex flex-wrap gap-2">
            <select className="rounded-md border border-input px-2 py-1 text-sm" value={type} onChange={(e) => setType(e.target.value)}>
              <option value="note">Note</option>
              <option value="call">Call</option>
              <option value="email">Email</option>
              <option value="meeting">Meeting</option>
            </select>
            <input
              className="min-w-[240px] flex-1 rounded-md border border-input px-3 py-1 text-sm"
              placeholder="What happened?"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
            <Button size="sm" disabled={!description} onClick={() => create.mutate()}>
              Log
            </Button>
          </div>
        </CardContent>
      </Card>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : (
        <ul className="space-y-3">
          {rows.map((a) => (
            <li key={String(a.id)} className="rounded-lg border border-border/80 bg-card p-4 text-sm">
              <div className="flex flex-wrap justify-between gap-2">
                <span className="font-medium capitalize">{String(a.type)}</span>
                <span className="text-xs text-muted-foreground">{String(a.performed_at ?? "")}</span>
              </div>
              <p className="mt-2 whitespace-pre-wrap">{String(a.description ?? "")}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
