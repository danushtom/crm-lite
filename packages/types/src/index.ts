/** Shared domain types — mirrors Supabase schema / API contracts */

export type UserRole = "admin" | "agent" | "sdr" | "partner";

export type LeadStage =
  | "prospect"
  | "contacting"
  | "discovery_scheduled"
  | "requirements_gathering"
  | "solution_design"
  | "proposal_sent"
  | "negotiation"
  | "won"
  | "delivery_transition"
  | "on_hold"
  | "followup_later"
  | "lost";

export type ProjectType = "mvp" | "saas" | "ai" | "webapp" | "erp" | "other";
export type LeadSource = "cold_call" | "referral" | "website" | "linkedin" | "other";

export interface UserRow {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  avatar_url: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export type CompanySegment = "sme" | "startup" | "enterprise";

export interface CompanyRow {
  id: string;
  name: string;
  industry: string | null;
  size: string | null;
  website: string | null;
  location: string | null;
  logo_url: string | null;
  linkedin_url: string | null;
  segment: CompanySegment | null;
  created_by: string | null;
  created_at: string;
  /** Monotonic row version, returned as an ETag and sent back via If-Match. */
  version: number;
  /** Set when soft-deleted; such rows are hidden from every query. */
  deleted_at?: string | null;
}

export interface ContactRow {
  id: string;
  company_id: string;
  full_name: string;
  role: string | null;
  email: string | null;
  phone: string | null;
  linkedin_url: string | null;
  avatar_url: string | null;
  source: LeadSource | null;
  is_primary: boolean;
  created_at: string;
  /** Monotonic row version, returned as an ETag and sent back via If-Match. */
  version: number;
  /** Set when soft-deleted; such rows are hidden from every query. */
  deleted_at?: string | null;
}

/**
 * A lead is a *qualification* record: who the prospect is, where they came from and when to
 * follow up. Pipeline stage and commercials belong to its opportunities -- a lead may have
 * several over time (the build, then the retainer). Use the helpers in `lib/leads.ts` to read
 * a lead's current pipeline position.
 */
export interface LeadRow {
  id: string;
  company_id: string;
  primary_contact_id: string | null;
  owner_id: string;
  project_type: ProjectType;
  lead_source: LeadSource;
  last_contact_date: string | null;
  next_followup_date: string | null;
  tags: string[];
  no_touch_alert?: boolean | null;
  created_at: string;
  updated_at: string;
  /** Monotonic row version, returned as an ETag and sent back via If-Match. */
  version: number;
  /** Set when soft-deleted; such rows are hidden from every query. */
  deleted_at?: string | null;
}

/** A lead's pursuit, as embedded in lead responses. */
export interface LeadOpportunityRow {
  id: string;
  title: string;
  stage: LeadStage;
  status: OpportunityStatus;
  quoted_value: number | null;
  currency: string;
  deal_probability: number;
  priority_score: number;
  updated_at: string;
}

/** A lead as returned by list and detail endpoints, with its pursuits embedded. */
export interface LeadWithOpportunities extends LeadRow {
  companies?: Partial<CompanyRow> | null;
  opportunities: LeadOpportunityRow[];
}

export interface LeadIntelligenceRow {
  id: string;
  lead_id: string;
  pain_points: string | null;
  tech_stack: string | null;
  budget_hints: string | null;
  decision_makers: string | null;
  competitors_involved: string | null;
  objections_raised: string | null;
  strategic_notes: string | null;
  comm_preference: string;
  updated_at: string;
  updated_by: string | null;
  /** Monotonic row version, returned as an ETag and sent back via If-Match. */
  version: number;
}

export type ActivityType =
  | "call"
  | "email"
  | "meeting"
  | "note"
  | "stage_change"
  | "proposal_sent"
  | "task_created"
  | "task_completed"
  | "document_uploaded";

export interface ActivityRow {
  id: string;
  lead_id: string;
  type: ActivityType;
  description: string;
  outcome: string | null;
  performed_by: string;
  performed_at: string;
  metadata: Record<string, unknown> | null;
}

export type TaskStatus = "pending" | "snoozed" | "completed" | "cancelled";

export interface TaskRow {
  id: string;
  lead_id: string;
  owner_id: string;
  title: string;
  notes: string | null;
  /** Absolute instant the follow-up falls due; render in the owner's timezone. */
  due_at: string;
  status: TaskStatus;
  outcome_note: string | null;
  snoozed_to: string | null;
  completed_at: string | null;
  created_at: string;
  version: number;
}

export type MeetingStatus = "scheduled" | "completed" | "cancelled" | "rescheduled";
export type MeetingOutcome =
  | "interested"
  | "needs_proposal"
  | "budget_issue"
  | "not_interested"
  | "followup_later";

export interface MeetingRow {
  id: string;
  lead_id: string | null;
  owner_id: string;
  title: string;
  google_event_id: string | null;
  google_meet_link: string | null;
  scheduled_at: string;
  duration_minutes: number;
  status: MeetingStatus;
  outcome: MeetingOutcome | null;
  outcome_notes: string | null;
  created_at: string;
  /** Monotonic row version, returned as an ETag and sent back via If-Match. */
  version: number;
}

export type OpportunityStatus = "active" | "won" | "lost" | "on_hold";

/** Canonical pipeline row per lead — Kanban stage + commercial fields + proposals FK target. */
export interface OpportunityRow {
  id: string;
  lead_id: string;
  owner_id: string;
  title: string;
  /** Pipeline position. Owned here; leads no longer carry a copy. */
  stage: LeadStage;
  quoted_value: number | null;
  currency: string;
  deal_probability: number;
  priority_score: number;
  tags: string[];
  timeline_weeks: number | null;
  tech_stack: string | null;
  requirements_doc: string | null;
  architecture_notes: string | null;
  status: OpportunityStatus;
  score_override: number | null;
  score_override_reason: string | null;
  created_at: string;
  updated_at: string;
  /** Monotonic row version, returned as an ETag and sent back via If-Match. */
  version: number;
  /** Set when soft-deleted; such rows are hidden from every query. */
  deleted_at?: string | null;
}

/** Shape returned by `GET /opportunities/by-lead/{id}` — a light subset of {@link OpportunityRow}. */
export type OpportunitySummaryRow = Pick<
  OpportunityRow,
  | "id"
  | "lead_id"
  | "title"
  | "status"
  | "stage"
  | "quoted_value"
  | "currency"
  | "deal_probability"
  | "priority_score"
  | "updated_at"
>;

export type ProposalDocStatus = "draft" | "sent" | "under_review" | "accepted" | "rejected";

export interface ProposalRow {
  id: string;
  opportunity_id: string;
  version: number;
  title: string;
  file_url: string | null;
  figma_url: string | null;
  github_url: string | null;
  loom_url: string | null;
  quoted_price: number | null;
  change_notes: string | null;
  status: ProposalDocStatus;
  sent_at: string | null;
  created_by: string | null;
  created_at: string;
}

/** Score tier labels */
export function scoreTier(score: number): "Hot" | "Warm" | "Cold" {
  if (score >= 80) return "Hot";
  if (score >= 50) return "Warm";
  return "Cold";
}
