import type { LeadStage } from "@dracara/types";

/** Grouped Kanban columns — maps CRM stages → swimlanes (pipeline lives on opportunities). */
export type OpportunityKanbanColumnId = "leads" | "discovery" | "demo" | "won" | "lost";

export type OpportunityKanbanColumn = {
  id: OpportunityKanbanColumnId;
  /** Uppercase label for header */
  label: string;
  stages: LeadStage[];
  /** Stage applied when a card is dropped on this column */
  dropStage: LeadStage;
  headerBarClass: string;
  columnShellClass: string;
};

export const OPPORTUNITY_KANBAN_COLUMNS: OpportunityKanbanColumn[] = [
  {
    id: "leads",
    label: "Leads",
    stages: ["prospect", "contacting"],
    dropStage: "prospect",
    headerBarClass: "border-slate-200 bg-gradient-to-b from-slate-50 to-slate-100/90 text-slate-800 dark:border-slate-700 dark:from-slate-900/80 dark:to-slate-900/40 dark:text-slate-100",
    columnShellClass: "border-slate-200/90 bg-slate-50/40 dark:border-slate-800 dark:bg-slate-950/40",
  },
  {
    id: "discovery",
    label: "Discovery",
    stages: ["discovery_scheduled", "requirements_gathering", "solution_design"],
    dropStage: "discovery_scheduled",
    headerBarClass: "border-blue-200 bg-gradient-to-b from-blue-50 to-blue-100/80 text-blue-950 dark:border-blue-900 dark:from-blue-950/60 dark:to-blue-950/30 dark:text-blue-50",
    columnShellClass: "border-blue-200/80 bg-blue-50/30 dark:border-blue-900/60 dark:bg-blue-950/20",
  },
  {
    id: "demo",
    label: "Demo",
    stages: ["proposal_sent", "negotiation", "on_hold", "followup_later"],
    dropStage: "proposal_sent",
    headerBarClass: "border-amber-200 bg-gradient-to-b from-amber-50 to-orange-50/90 text-amber-950 dark:border-amber-900 dark:from-amber-950/50 dark:to-orange-950/30 dark:text-amber-50",
    columnShellClass: "border-amber-200/80 bg-amber-50/25 dark:border-amber-900/50 dark:bg-amber-950/15",
  },
  {
    id: "won",
    label: "Won",
    stages: ["won", "delivery_transition"],
    dropStage: "won",
    headerBarClass: "border-emerald-200 bg-gradient-to-b from-emerald-50 to-emerald-100/80 text-emerald-950 dark:border-emerald-900 dark:from-emerald-950/50 dark:to-emerald-950/25 dark:text-emerald-50",
    columnShellClass: "border-emerald-200/80 bg-emerald-50/25 dark:border-emerald-900/50 dark:bg-emerald-950/15",
  },
  {
    id: "lost",
    label: "Lost",
    stages: ["lost"],
    dropStage: "lost",
    headerBarClass: "border-border bg-muted/70 text-muted-foreground",
    columnShellClass: "border-border/80 bg-muted/20 opacity-95",
  },
];

export function columnForStage(stage: LeadStage): OpportunityKanbanColumnId | null {
  for (const col of OPPORTUNITY_KANBAN_COLUMNS) {
    if (col.stages.includes(stage)) return col.id;
  }
  return null;
}
