import type { LeadSource, LeadStage, ProjectType } from "@dracara/types";

/**
 * Strip empty form values before sending them to the API.
 *
 * Request bodies are validated strictly server-side: an optional enum or email field sent as
 * `""` is a 422, not "unset". Form state uses `""` for "nothing chosen", so empty strings,
 * `null` and `undefined` are dropped here. `false` and `0` are deliberately preserved.
 */
export function compactPayload<T extends Record<string, unknown>>(form: T): Partial<T> {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(form)) {
    if (value === "" || value === null || value === undefined) continue;
    if (Array.isArray(value) && value.length === 0) continue;
    out[key] = value;
  }
  return out as Partial<T>;
}

/** Turn a comma-separated tag input into the array the API expects. */
export function parseTags(input: string): string[] {
  return Array.from(
    new Set(
      input
        .split(",")
        .map((tag) => tag.trim())
        .filter(Boolean)
    )
  ).slice(0, 25);
}

/** `discovery_scheduled` -> `Discovery Scheduled` */
export function humanizeEnum(value: string): string {
  return value
    .split("_")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

type Option<T extends string> = { value: T; label: string };

/** Mirrors `lead_stage` in the database and `LeadStage` in @dracara/types. */
export const LEAD_STAGE_OPTIONS: Option<LeadStage>[] = [
  { value: "prospect", label: "Prospect" },
  { value: "contacting", label: "Contacting" },
  { value: "discovery_scheduled", label: "Discovery Scheduled" },
  { value: "requirements_gathering", label: "Requirements Gathering" },
  { value: "solution_design", label: "Solution Design" },
  { value: "proposal_sent", label: "Proposal Sent" },
  { value: "negotiation", label: "Negotiation" },
  { value: "won", label: "Won" },
  { value: "delivery_transition", label: "Delivery Transition" },
  { value: "on_hold", label: "On Hold" },
  { value: "followup_later", label: "Follow-up Later" },
  { value: "lost", label: "Lost" },
];

/** Mirrors `project_type`. */
export const PROJECT_TYPE_OPTIONS: Option<ProjectType>[] = [
  { value: "mvp", label: "MVP" },
  { value: "saas", label: "SaaS Platform" },
  { value: "ai", label: "AI / ML" },
  { value: "webapp", label: "Web Application" },
  { value: "erp", label: "ERP" },
  { value: "other", label: "Other" },
];

/** Mirrors `lead_source`. */
export const LEAD_SOURCE_OPTIONS: Option<LeadSource>[] = [
  { value: "cold_call", label: "Cold Call" },
  { value: "referral", label: "Referral" },
  { value: "website", label: "Website" },
  { value: "linkedin", label: "LinkedIn" },
  { value: "other", label: "Other" },
];

/** Currencies the pipeline quotes in; the column is a 3-letter code. */
export const CURRENCY_OPTIONS = ["INR", "USD", "EUR", "GBP", "AED", "SGD"];
