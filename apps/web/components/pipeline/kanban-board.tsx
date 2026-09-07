"use client";

import { DndContext, DragEndEvent, DragOverlay, PointerSensor, closestCorners, useDraggable, useDroppable, useSensor, useSensors } from "@dnd-kit/core";
import { Badge, Card, CardContent, Skeleton, cn } from "@dracara/ui";
import type { LeadRow, OpportunityRow } from "@dracara/types";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useApiMutation } from "@/lib/use-api-mutation";
import { format, parseISO } from "date-fns";
import { BarChart3 } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { apiFetch, apiListAll } from "@/lib/api";
import {
  OPPORTUNITY_KANBAN_COLUMNS,
  columnForStage,
  type OpportunityKanbanColumn,
  type OpportunityKanbanColumnId,
} from "@/lib/opportunities-kanban-columns";

type LeadWithCompany = LeadRow & { companies?: { name?: string | null; logo_url?: string | null } | null };

type OpportunityWithLead = OpportunityRow & {
  leads?: LeadWithCompany | null;
};

const PROJECT_BLURB: Record<string, string> = {
  mvp: "MVP build",
  saas: "SaaS",
  ai: "AI / ML",
  webapp: "Web app",
  erp: "ERP integration",
  other: "Engagement",
};

function formatValueLine(currency: string, value: number | null): string {
  if (value == null) return "—";
  const n = Number(value);
  if (currency === "USD" && n >= 1000) return `$${(n / 1000).toFixed(Number.isInteger(n / 1000) ? 0 : 1)}k`;
  if (currency === "INR" && n >= 100000) return `₹${(n / 100000).toFixed(1)}L`;
  const prefix = currency === "INR" ? "₹" : currency === "USD" ? "$" : `${currency} `;
  return `${prefix}${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function cardSubtitle(opp: OpportunityWithLead): string {
  const lead = opp.leads;
  // Tags categorise the prospect, so they live on the lead; pursuits no longer carry a copy.
  const tag = lead?.tags?.[0] as string | undefined;
  if (tag && tag.length > 0) return tag;
  const pt = lead?.project_type ?? "other";
  return PROJECT_BLURB[pt] ?? String(pt).replace(/_/g, " ");
}

function OpportunityPreview({ opp }: { opp: OpportunityWithLead }) {
  const lead = opp.leads;
  const companyName = lead?.companies?.name ?? "Unknown company";
  const initial = companyName.trim().slice(0, 1).toUpperCase();
  const dateLabel = (() => {
    try {
      return format(parseISO(opp.updated_at), "MMM d");
    } catch {
      return "";
    }
  })();

  const logoUrl = lead?.companies?.logo_url;
  const leadId = lead?.id ?? opp.lead_id;
  const pt = lead?.project_type ?? "other";

  return (
    <Card className="overflow-hidden rounded-xl border-[#E5E7EB] bg-white shadow-[0_1px_2px_rgba(15,23,42,0.05)] dark:border-border dark:bg-card">
      <CardContent className="p-3">
        <div className="flex gap-3">
          <div className="relative h-11 w-11 shrink-0 overflow-hidden rounded-lg border border-[#E5E7EB] bg-muted/40 dark:border-border">
            {logoUrl ? (
              // eslint-disable-next-line @next/next/no-img-element -- remote company logos from CMS
              <img src={logoUrl} alt="" className="h-full w-full object-cover" />
            ) : (
              <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-slate-100 to-slate-200 text-sm font-bold text-slate-700 dark:from-slate-700 dark:to-slate-800 dark:text-slate-100">
                {initial}
              </div>
            )}
          </div>
          <div className="min-w-0 flex-1 space-y-1">
            <div className="flex items-start justify-between gap-2">
              <Link
                href={`/opportunities/${opp.id}`}
                onPointerDown={(e) => e.stopPropagation()}
                className="line-clamp-2 text-sm font-semibold leading-snug text-[#111827] hover:underline dark:text-foreground"
              >
                {companyName}
              </Link>
              {dateLabel ? (
                <span className="shrink-0 text-[11px] tabular-nums text-[#9CA3AF] dark:text-muted-foreground">{dateLabel}</span>
              ) : null}
            </div>
            <p className="line-clamp-2 text-xs leading-relaxed text-[#6B7280] dark:text-muted-foreground">{cardSubtitle(opp)}</p>
            <div className="flex items-center gap-2 pt-1">
              <BarChart3 className="h-4 w-4 shrink-0 text-[#9CA3AF] dark:text-muted-foreground" aria-hidden />
              <span className="min-w-0 flex-1 text-center text-sm font-semibold tabular-nums text-[#111827] dark:text-foreground">
                {formatValueLine(opp.currency ?? "INR", opp.quoted_value)}
              </span>
              <Badge
                variant="secondary"
                className="max-w-[120px] shrink-0 truncate border border-[#E5E7EB] bg-[#F9FAFB] text-[10px] font-medium text-[#374151] dark:border-border dark:bg-muted dark:text-foreground"
              >
                {PROJECT_BLURB[pt] ?? pt}
              </Badge>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function DraggableOpportunity({ opp }: { opp: OpportunityWithLead }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: opp.id,
  });
  const style = transform ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` } : undefined;

  return (
    <div ref={setNodeRef} style={style} {...listeners} {...attributes} className={cn(isDragging && "opacity-40")}>
      <OpportunityPreview opp={opp} />
    </div>
  );
}

function GroupColumn({ column, rows, index }: { column: OpportunityKanbanColumn; rows: OpportunityWithLead[]; index?: number }) {
  const { setNodeRef, isOver } = useDroppable({ id: column.id });
  return (
    <div
      ref={setNodeRef}
      className={cn(
        "flex min-h-[min(420px,70vh)] w-[min(100vw-2rem,280px)] shrink-0 flex-col rounded-2xl border shadow-[0_1px_3px_rgba(15,23,42,0.06)] sm:w-72",
        column.columnShellClass,
        isOver && "ring-2 ring-[hsl(var(--primary))]/35",
        index !== undefined && "animate-in fade-in zoom-in-95 duration-500 fill-mode-both"
      )}
      style={index !== undefined ? { animationDelay: `${index * 50}ms` } : undefined}
    >
      <div
        className={cn(
          "sticky top-0 z-10 rounded-t-2xl border-b px-3 py-2.5 backdrop-blur-sm",
          column.headerBarClass
        )}
      >
        <p className="text-[11px] font-bold uppercase tracking-[0.08em]">{column.label}</p>
        <p className="text-[11px] font-medium opacity-80">({rows.length})</p>
      </div>
      <div className="flex flex-1 flex-col gap-2.5 p-2">
        {rows.map((opp) => (
          <DraggableOpportunity key={opp.id} opp={opp} />
        ))}
      </div>
    </div>
  );
}

export function KanbanBoard() {
  const qc = useQueryClient();
  const [activeId, setActiveId] = useState<string | null>(null);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }));

  const { data: opportunities = [], isLoading } = useQuery({
    queryKey: ["opportunities", "pipeline"],
    queryFn: () => apiListAll<OpportunityWithLead>("/opportunities"),
  });

  const move = useApiMutation({
    errorTitle: "Could not move card",
    // Stage belongs to the pursuit. This used to PATCH /leads/{id}/stage, which went away
    // when leads stopped carrying a mirrored copy of it.
    mutationFn: async ({
      opportunityId,
      stage,
      version,
    }: {
      opportunityId: string;
      stage: string;
      version: number;
    }) => {
      await apiFetch(`/opportunities/${opportunityId}`, {
        method: "PATCH",
        headers: { "If-Match": `"${version}"` },
        body: JSON.stringify({ stage }),
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["opportunities"] });
      qc.invalidateQueries({ queryKey: ["leads"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  const byColumn = useMemo(() => {
    const map = new Map<OpportunityKanbanColumnId, OpportunityWithLead[]>();
    for (const col of OPPORTUNITY_KANBAN_COLUMNS) map.set(col.id, []);

    for (const opp of opportunities) {
      const cid = columnForStage(opp.stage);
      if (!cid) continue;
      map.get(cid)!.push(opp);
    }

    for (const col of OPPORTUNITY_KANBAN_COLUMNS) {
      const list = map.get(col.id) ?? [];
      list.sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());
      map.set(col.id, list);
    }
    return map;
  }, [opportunities]);

  function onDragEnd(e: DragEndEvent) {
    setActiveId(null);
    const oppId = String(e.active.id);
    const overId = e.over?.id;
    if (!overId) return;

    const targetColumn = OPPORTUNITY_KANBAN_COLUMNS.find((c) => c.id === overId);
    if (!targetColumn) return;

    const opp = opportunities.find((o) => o.id === oppId);
    if (!opp) return;

    // Same column: the card already sits in this swimlane, so keep its granular stage.
    if (targetColumn.stages.includes(opp.stage)) return;

    move.mutate({
      opportunityId: opp.id,
      stage: targetColumn.dropStage,
      version: opp.version,
    });
  }

  const activeOpp = activeId ? opportunities.find((o) => o.id === activeId) : null;

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCorners}
      onDragStart={(ev) => setActiveId(String(ev.active.id))}
      onDragCancel={() => setActiveId(null)}
      onDragEnd={onDragEnd}
    >
      <div className="-mx-1 flex gap-3 overflow-x-auto pb-2 pt-1 md:-mx-0">
        {isLoading ? (
          <>
            {Array.from({ length: 4 }).map((_, i) => (
              <div
                key={i}
                className="flex min-h-[min(420px,70vh)] w-[min(100vw-2rem,280px)] shrink-0 flex-col rounded-2xl border border-[#E5E7EB] bg-white shadow-[0_1px_3px_rgba(15,23,42,0.06)] dark:border-border dark:bg-card sm:w-72"
              >
                <div className="sticky top-0 z-10 rounded-t-2xl border-b border-[#E5E7EB] px-3 py-2.5 dark:border-border">
                  <Skeleton className="h-4 w-24" />
                </div>
                <div className="flex flex-1 flex-col gap-2.5 p-2">
                  {Array.from({ length: 3 }).map((_, j) => (
                    <Card key={j} className="overflow-hidden rounded-xl border-[#E5E7EB] bg-white shadow-[0_1px_2px_rgba(15,23,42,0.05)] dark:border-border dark:bg-card">
                      <CardContent className="p-3">
                        <div className="flex gap-3">
                          <Skeleton className="h-11 w-11 shrink-0 rounded-lg" />
                          <div className="min-w-0 flex-1 space-y-2">
                            <div className="flex items-start justify-between gap-2">
                              <Skeleton className="h-4 w-28" />
                              <Skeleton className="h-3 w-10 shrink-0" />
                            </div>
                            <Skeleton className="h-3 w-20" />
                            <div className="flex items-center gap-2 pt-1">
                              <Skeleton className="h-5 w-24" />
                              <Skeleton className="h-5 w-16" />
                            </div>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </div>
            ))}
          </>
        ) : (
          OPPORTUNITY_KANBAN_COLUMNS.map((column, i) => (
            <GroupColumn key={column.id} column={column} index={i} rows={byColumn.get(column.id) ?? []} />
          ))
        )}
      </div>
      <DragOverlay>{activeOpp ? <OpportunityPreview opp={activeOpp} /> : null}</DragOverlay>
      {move.isError ? (
        <p className="mt-2 text-sm text-destructive">{(move.error as Error).message}</p>
      ) : null}
    </DndContext>
  );
}
