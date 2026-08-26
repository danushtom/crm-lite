"use client";

import {
  ArrowDownWideNarrow,
  ChevronDown,
  Filter,
  KanbanSquare,
  LayoutGrid,
  List,
  Sparkles,
  Timer,
} from "lucide-react";
import { Button, cn } from "@dracara/ui";
import { AddLeadDrawer } from "@/components/leads/add-lead-drawer";

export type OpportunitiesViewMode = "list" | "kanban" | "timeline";

export function OpportunitiesToolbar({
  viewMode = "kanban",
  onViewModeChange,
}: {
  viewMode?: OpportunitiesViewMode;
  onViewModeChange?: (v: OpportunitiesViewMode) => void;
}) {
  const setView = onViewModeChange ?? (() => {});

  return (
    <div className="flex flex-col gap-3 border-b border-[#E5E7EB] pb-3 dark:border-border sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
      <div className="flex flex-wrap items-center gap-2">
        {/* Work enters the pipeline as a lead; creating one opens its first pursuit. */}
        <AddLeadDrawer />
        <Button
          type="button"
          size="sm"
          className="h-9 gap-2 rounded-lg bg-[#0A1128] px-4 text-white hover:bg-[#151f3d]"
        >
          <Sparkles className="h-4 w-4 shrink-0" />
          Ask AI
        </Button>
        <Button type="button" variant="outline" size="sm" className="h-9 rounded-lg border-[#E5E7EB] bg-white shadow-sm dark:border-border dark:bg-card">
          <Filter className="mr-1.5 h-3.5 w-3.5" />
          Filter
        </Button>
        <Button type="button" variant="outline" size="sm" className="h-9 rounded-lg border-[#E5E7EB] bg-white shadow-sm dark:border-border dark:bg-card">
          <ArrowDownWideNarrow className="mr-1.5 h-3.5 w-3.5" />
          Sort
        </Button>
        <Button type="button" variant="outline" size="sm" className="h-9 rounded-lg border-[#E5E7EB] bg-white shadow-sm dark:border-border dark:bg-card">
          <LayoutGrid className="mr-1.5 h-3.5 w-3.5" />
          Group
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-2 sm:justify-end">
        <div className="flex rounded-lg border border-[#E5E7EB] bg-[#F9FAFB] p-0.5 dark:border-border dark:bg-muted/40">
          {(
            [
              { id: "list" as const, label: "List", Icon: List },
              { id: "kanban" as const, label: "Kanban", Icon: KanbanSquare },
              { id: "timeline" as const, label: "Timeline", Icon: Timer },
            ] as const
          ).map(({ id, label, Icon }) => (
            <button
              key={id}
              type="button"
              disabled={id !== "kanban"}
              title={id !== "kanban" ? "Coming soon" : undefined}
              onClick={() => setView(id)}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition-colors",
                viewMode === id
                  ? "bg-white text-[#0A1128] shadow-sm dark:bg-card dark:text-foreground"
                  : "text-muted-foreground hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
              )}
            >
              <Icon className="h-3.5 w-3.5" />
              {label}
            </button>
          ))}
        </div>

        <Button
          type="button"
          size="sm"
          className="h-9 gap-1 rounded-lg bg-[#0A1128] px-3 text-white hover:bg-[#151f3d]"
        >
          Add New
          <ChevronDown className="h-4 w-4 opacity-80" />
        </Button>
      </div>
    </div>
  );
}
