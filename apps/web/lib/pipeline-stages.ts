import type { LeadRow } from "@dracara/types";

/** Ordered Kanban columns — matches DB enum (tdd.md §10.2) */
export const PIPELINE_STAGES: LeadRow["stage"][] = [
  "prospect",
  "contacting",
  "discovery_scheduled",
  "requirements_gathering",
  "solution_design",
  "proposal_sent",
  "negotiation",
  "won",
  "delivery_transition",
  "on_hold",
  "followup_later",
  "lost",
];

export function stageLabel(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
