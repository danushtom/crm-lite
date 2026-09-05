"""Domain enums mirroring the PostgreSQL enum types in ``supabase/migrations``.

Declaring these as real enums rather than bare ``str`` gives three things the previous
``str``-typed request models did not: rejection of invalid values at the edge with a 422
instead of a 500 from Postgres, self-documenting OpenAPI schemas, and a single place to
update when a migration changes an enum.

Keep in sync with ``packages/types/src/index.ts`` (TypeScript mirror).
"""

from __future__ import annotations

from enum import StrEnum


class LeadStage(StrEnum):
    PROSPECT = "prospect"
    CONTACTING = "contacting"
    DISCOVERY_SCHEDULED = "discovery_scheduled"
    REQUIREMENTS_GATHERING = "requirements_gathering"
    SOLUTION_DESIGN = "solution_design"
    PROPOSAL_SENT = "proposal_sent"
    NEGOTIATION = "negotiation"
    WON = "won"
    DELIVERY_TRANSITION = "delivery_transition"
    ON_HOLD = "on_hold"
    FOLLOWUP_LATER = "followup_later"
    LOST = "lost"


class ProjectType(StrEnum):
    MVP = "mvp"
    SAAS = "saas"
    AI = "ai"
    WEBAPP = "webapp"
    ERP = "erp"
    OTHER = "other"


class LeadSource(StrEnum):
    COLD_CALL = "cold_call"
    REFERRAL = "referral"
    WEBSITE = "website"
    LINKEDIN = "linkedin"
    OTHER = "other"


class CommPreference(StrEnum):
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    LINKEDIN = "linkedin"
    PHONE = "phone"
    CALL = "call"


class CompanySegment(StrEnum):
    SME = "sme"
    STARTUP = "startup"
    ENTERPRISE = "enterprise"


class ActivityType(StrEnum):
    CALL = "call"
    EMAIL = "email"
    MEETING = "meeting"
    NOTE = "note"
    STAGE_CHANGE = "stage_change"
    PROPOSAL_SENT = "proposal_sent"
    TASK_CREATED = "task_created"
    TASK_COMPLETED = "task_completed"
    DOCUMENT_UPLOADED = "document_uploaded"


class TaskStatus(StrEnum):
    PENDING = "pending"
    SNOOZED = "snoozed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class MeetingStatus(StrEnum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    RESCHEDULED = "rescheduled"


class MeetingOutcome(StrEnum):
    INTERESTED = "interested"
    NEEDS_PROPOSAL = "needs_proposal"
    BUDGET_ISSUE = "budget_issue"
    NOT_INTERESTED = "not_interested"
    FOLLOWUP_LATER = "followup_later"


class OpportunityStatus(StrEnum):
    ACTIVE = "active"
    WON = "won"
    LOST = "lost"
    ON_HOLD = "on_hold"


class ProposalStatus(StrEnum):
    DRAFT = "draft"
    SENT = "sent"
    UNDER_REVIEW = "under_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class VoiceAgentDirection(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    BOTH = "both"


class CallDirection(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class CallStatus(StrEnum):
    QUEUED = "queued"
    RINGING = "ringing"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    NO_CONSENT_BLOCKED = "no_consent_blocked"


#: Outcomes that should automatically schedule a follow-up task (tdd.md 14.2).
OUTCOMES_REQUIRING_FOLLOWUP = frozenset({MeetingOutcome.NEEDS_PROPOSAL, MeetingOutcome.FOLLOWUP_LATER})

#: Stages that close a deal; used by dashboard and reporting rollups.
CLOSED_WON_STAGES = frozenset({LeadStage.WON, LeadStage.DELIVERY_TRANSITION})
CLOSED_LOST_STAGES = frozenset({LeadStage.LOST})
