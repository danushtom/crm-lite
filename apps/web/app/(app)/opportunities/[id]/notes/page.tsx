"use client";

import { Button, Card, CardContent, CardHeader, CardTitle } from "@dracara/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useApiMutation } from "@/lib/use-api-mutation";
import { useParams } from "next/navigation";
import { useState } from "react";
import { apiFetch } from "@/lib/api";
import { Info, Save } from "lucide-react";

export default function OpportunityNotesPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();

  const { data: opp, isLoading } = useQuery({
    queryKey: ["opportunity", id],
    queryFn: () => apiFetch<any>(`/opportunities/${id}`),
  });

  const [form, setForm] = useState<Record<string, string>>({});

  const save = useApiMutation({
    errorTitle: "Could not save changes",    mutationFn: () => apiFetch(`/opportunities/${id}`, { method: "PATCH", body: JSON.stringify(form) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["opportunity", id] }),
  });

  if (isLoading || !opp) return <p className="text-sm text-muted-foreground animate-pulse">Loading notes…</p>;

  const technicalFields = [
    { key: "tech_stack", label: "Tech Stack", placeholder: "e.g. Next.js, FastAPI, Postgres" },
    { key: "architecture_notes", label: "Architecture Notes", placeholder: "e.g. Serverless, Microservices, Event-driven" },
    { key: "requirements_doc", label: "Requirements Document", placeholder: "Paste or link requirements summary here..." },
  ] as const;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">Technical & Strategic Notes</h2>
        <p className="mt-1 text-sm text-muted-foreground">Deep context for the solution design and delivery transition.</p>
      </div>

      <div className="grid gap-6">
        {technicalFields.map((field) => (
          <div key={field.key} className="space-y-2">
            <label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">{field.label}</label>
            <textarea
              className="min-h-[120px] w-full rounded-xl border border-border/70 bg-card p-4 text-sm shadow-sm transition-all focus:border-[#0B7FB3] focus:ring-2 focus:ring-[#0B7FB3]/20"
              defaultValue={String(opp[field.key] ?? "")}
              placeholder={field.placeholder}
              onChange={(e) => setForm((f) => ({ ...f, [field.key]: e.target.value }))}
            />
          </div>
        ))}
      </div>

      <div className="flex items-center justify-between border-t border-border/50 pt-6">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Info className="h-3.5 w-3.5" />
          Changes are not autosaved in this view.
        </div>
        <Button 
          onClick={() => save.mutate()} 
          disabled={save.isPending || Object.keys(form).length === 0}
          className="gap-2 bg-[#0B7FB3] hover:bg-[#096892]"
        >
          <Save className="h-4 w-4" />
          {save.isPending ? "Saving..." : "Save Technical Context"}
        </Button>
      </div>
    </div>
  );
}
