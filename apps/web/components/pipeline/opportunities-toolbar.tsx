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
import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { useState } from "react";
import { AskAiDrawer } from "@/components/ai/ask-ai-drawer";

export type OpportunitiesViewMode = "list" | "kanban" | "timeline";

export function OpportunitiesToolbar({
  viewMode = "kanban",
  onViewModeChange,
}: {
  viewMode?: OpportunitiesViewMode;
  onViewModeChange?: (v: OpportunitiesViewMode) => void;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [showAi, setShowAi] = useState(false);
  
  const setView = onViewModeChange ?? ((v: OpportunitiesViewMode) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("view", v);
    router.push(`${pathname}?${params.toString()}`);
  });

  return (
    <>
      <AskAiDrawer open={showAi} onOpenChange={setShowAi} />
      <div className="flex flex-col gap-3 border-b border-[#E5E7EB] pb-3 dark:border-border sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          {/* Work enters the pipeline as a lead; creating one opens its first pursuit. */}
          <AddLeadDrawer />
          <Button
            type="button"
            size="sm"
            onClick={() => setShowAi(true)}
            className="h-9 gap-2 rounded-lg bg-[#0A1128] px-4 text-white hover:bg-[#151f3d]"
          >
            <Sparkles className="h-4 w-4 shrink-0" />
            Ask AI
          </Button>
        </div>

      <div className="flex flex-wrap items-center gap-2 sm:justify-end">
        <div className="flex rounded-lg border border-[#E5E7EB] bg-[#F9FAFB] p-0.5 dark:border-border dark:bg-muted/40">
          {[
            { id: "list", icon: List, label: "List" },
            { id: "kanban", icon: LayoutGrid, label: "Board" },
            { id: "timeline", icon: Timer, label: "Timeline" },
          ].map(({ id, icon: Icon, label }) => (
            <button
              key={id}
              onClick={() => setView(id as OpportunitiesViewMode)}
              className={cn(
                "flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-all",
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
      </div>
    </div>
    </>
  );
}
