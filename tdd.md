DRACARA GROWTH OS
Deal Flow Command Center for dracara.dev


Business Requirements Document  +  Technical Design Document

Document Version
v1.0
Document Type
Combined BRD + TDD
Product
Dracara Growth OS
Stack
Next.js 16 / FastAPI / Supabase / shadcn/ui
Prepared For
dracara.dev Internal Use


Table of Contents



PART 1: BUSINESS REQUIREMENTS DOCUMENT (BRD)

1. Executive Summary
Dracara Growth OS is a purpose-built deal flow command center for dracara.dev — a software services and consulting agency. Unlike generic CRMs (Salesforce, HubSpot, Zoho) that are designed for volume B2C sales, the Growth OS is engineered specifically for high-value software project sales cycles: from the first cold outreach to final delivery handoff and upsell.

The platform consolidates lead management, founder intelligence, follow-up workflows, proposal tracking, agent coordination, and revenue forecasting into a single opinionated workspace — replacing fragmented spreadsheets, WhatsApp notes, and calendar hacks that most boutique agencies rely on.

The MVP encompasses nine core modules: Lead Pipeline, Founder CRM Profile, Follow-Up Engine, Activities Timeline, Google Calendar Integration, Multi-Agent Management, Proposal & Requirements Tracker, Opportunity Scoring, and the Founder Dashboard. The system is designed to scale into AI-assisted workflows in Phase 2.


2. Business Context & Problem Statement
2.1 Current State Pain Points
Leads tracked across spreadsheets, WhatsApp chats, and memory — no single source of truth
Follow-ups missed because there is no intelligent reminder system
Proposal versions scattered across email threads and Google Drive folders
No visibility into deal pipeline health, stalled deals, or conversion rates
Client intelligence (pain points, budget hints, decision makers) lives in the founder's head — not structured data
Agent/team coordination happens ad hoc with no accountability trail
Most CRMs end at deal close; dracara.dev revenue continues through delivery and upsell

2.2 Business Goals
Establish a single deal flow command center replacing all ad-hoc tracking
Reduce follow-up slippage to near zero through automated reminders and queues
Increase proposal win rate by 20-30% through structured requirements tracking and client intelligence
Enable multi-agent coordination with full activity audit trails
Build a pipeline that tracks value from Prospect through Delivery Transition and Upsell
Create a foundation for AI-assisted deal intelligence in Phase 2


3. Stakeholder Analysis
Stakeholder
Role
Primary Need
Access Level
Founder / Admin
Dan (dracara.dev)
Full pipeline visibility, founder daily brief, revenue forecast
Full Admin
SDR / Caller
Sales agent
Lead assignment, call logging, follow-up queue
Agent
Follow-Up Agent
Outreach specialist
Overdue reminders, touchpoint logging
Agent
Sales Partner
External collaborator
Assigned leads, proposal status
Restricted Agent
Client (indirect)
Prospect / customer
No direct access; represented as data
None



4. Scope
4.1 In-Scope — MVP (Phase 1)
Lead Pipeline Kanban (9 stages)
Founder CRM Profile with business intelligence fields
Follow-Up Engine with today queue, overdue alerts, 14-day no-touch rule
Activities Timeline per lead
Google Calendar OAuth integration with two-way sync
Multi-agent assignment, notes, mentions, performance metrics
Proposal & Requirements Tracker (versioned docs, Figma/Git links)
Opportunity Scoring (weighted lead score 0-100)
Founder Dashboard (cockpit view)
Authentication via Supabase Auth (email + OAuth)

4.2 Out-of-Scope — Phase 1
AI call summarization and action item extraction
AI proposal draft generation
Twilio calling logs
WhatsApp integration
Email sync (Gmail/Outlook)
Client-facing portal
Mobile app (web responsive only)


5. Functional Requirements
5.1 Lead Pipeline (FR-LP)
ID
Requirement
Priority
Notes
FR-LP-01
Kanban board with 9 configurable stages
Must Have
Drag-and-drop card movement
FR-LP-02
Lead card with all standard fields (company, contact, email, phone, LinkedIn, source, type, value, priority, dates, owner, probability)
Must Have
Full field spec in data model
FR-LP-03
Lead-to-Opportunity conversion as a distinct action
Must Have
Creates Opportunity entity separately
FR-LP-04
Stage transition history logged automatically
Must Have
Part of Activities Timeline
FR-LP-05
Filter leads by owner, stage, source, project type, priority
Must Have


FR-LP-06
Search across lead company, contact name, email
Must Have
Full-text via Supabase
FR-LP-07
Bulk reassign leads
Should Have
Admin only
FR-LP-08
Deal value aggregate by stage (pipeline value)
Must Have
Dashboard widget
FR-LP-09
Lead tags (multi-select)
Should Have


FR-LP-10
Import leads from CSV
Nice to Have
Phase 1 stretch goal


5.2 Founder CRM Profile (FR-CP)
ID
Requirement
Priority
Notes
FR-CP-01
Per-lead business intelligence panel with pain points, tech stack, budget hints, decision makers, competitors, objections, and strategic notes
Must Have
Rich text fields
FR-CP-02
Communication preference field (WhatsApp, email, LinkedIn, phone)
Must Have


FR-CP-03
Company profile with industry, size, location, website
Must Have


FR-CP-04
Multiple contacts per company with roles
Must Have
One-to-many
FR-CP-05
Intelligence notes timestamped per edit
Should Have
Audit trail for notes


5.3 Follow-Up Engine (FR-FU)
ID
Requirement
Priority
Notes
FR-FU-01
Today's follow-up queue with count badge
Must Have
Homepage widget
FR-FU-02
Overdue follow-ups list (past due date, not completed)
Must Have
Red-flagged
FR-FU-03
Upcoming meetings view (next 7 days)
Must Have


FR-FU-04
14-day no-touch alert: leads with no activity for 14+ days
Must Have
Background job
FR-FU-05
Create follow-up task from any lead with date, time, owner, note
Must Have


FR-FU-06
Snooze task (reschedule to later date)
Should Have


FR-FU-07
Mark task complete with outcome note
Must Have


FR-FU-08
Daily digest email summary to founder (Founder Daily Brief)
Should Have
Celery scheduled job
FR-FU-09
In-app notification for overdue tasks on login
Must Have
Toast notification


5.4 Activities Timeline (FR-AT)
ID
Requirement
Priority
Notes
FR-AT-01
Per-lead chronological activity feed
Must Have


FR-AT-02
Activity types: call, email, meeting, note, stage change, proposal sent, task created, task completed, document uploaded
Must Have


FR-AT-03
Manual activity logging with type, outcome, notes, date
Must Have


FR-AT-04
Auto-log on stage changes and task completions
Must Have
Backend event hooks
FR-AT-05
Activity author (agent) stamped on every entry
Must Have


FR-AT-06
Filter timeline by activity type
Should Have




5.5 Google Calendar Integration (FR-GC)
ID
Requirement
Priority
Notes
FR-GC-01
Google OAuth 2.0 login and calendar access
Must Have
Per-user token
FR-GC-02
Create meeting event from CRM lead view
Must Have
Push to Google Calendar
FR-GC-03
Attach Google Calendar event to a lead record
Must Have
Store event ID
FR-GC-04
Pull upcoming events from calendar into CRM view
Must Have
Read sync
FR-GC-05
Meeting outcome capture after event end (interested / needs proposal / budget issue / follow-up date)
Must Have
Post-meeting modal
FR-GC-06
Auto-create follow-up task from meeting outcome
Must Have
Triggered on outcome save
FR-GC-07
Meeting reminders (in-app)
Should Have
15 min before
FR-GC-08
Two-way event delete (delete from CRM also cancels Google event)
Should Have




5.6 Multi-Agent Management (FR-AG)
ID
Requirement
Priority
Notes
FR-AG-01
User roles: Admin, SDR, Follow-Up Agent, Sales Partner
Must Have
RBAC
FR-AG-02
Assign lead owner from lead card
Must Have


FR-AG-03
@mention in activity notes (notifies mentioned agent)
Should Have
In-app notification
FR-AG-04
Activity log filtered by agent
Must Have
Audit trail
FR-AG-05
Reassign lead to different owner
Must Have
Admin or current owner
FR-AG-06
Agent performance dashboard: calls made, meetings booked, leads moved, conversion rate
Must Have


FR-AG-07
Invite agent by email
Must Have
Supabase invite
FR-AG-08
Deactivate agent (reassign their leads on deactivation)
Should Have




5.7 Proposal & Requirements Tracker (FR-PT)
ID
Requirement
Priority
Notes
FR-PT-01
Per-opportunity proposal workspace with requirements doc (rich text)
Must Have


FR-PT-02
Architecture notes field
Must Have


FR-PT-03
Versioned scope documents (v1, v2... with change notes)
Must Have
Stored as separate rows
FR-PT-04
Proposal PDF upload and versioning
Must Have
Supabase Storage
FR-PT-05
Quoted price, timeline estimate, tech stack suggested
Must Have


FR-PT-06
Proposal status: Draft / Sent / Under Review / Accepted / Rejected
Must Have


FR-PT-07
External link fields: Figma, GitHub repo, Loom recording
Should Have


FR-PT-08
Attach any file (max 50MB per file)
Should Have
Supabase Storage


5.8 Opportunity Scoring (FR-OS)
ID
Requirement
Priority
Notes
FR-OS-01
Weighted opportunity score 0-100 per lead
Must Have
Configurable weights
FR-OS-02
Score dimensions: budget fit, urgency, authority access, project size, closing probability
Must Have


FR-OS-03
Score tier labels: Hot (80-100), Warm (50-79), Cold (0-49)
Must Have
Color-coded badges
FR-OS-04
Score recalculated on lead field updates
Must Have
Backend trigger
FR-OS-05
Founder can manually override score with reason
Should Have


FR-OS-06
Sort leads on Kanban by score
Should Have




5.9 Founder Dashboard (FR-FD)
ID
Requirement
Priority
Notes
FR-FD-01
Today's follow-ups count + list
Must Have


FR-FD-02
Total pipeline value (sum of estimated deal values by stage)
Must Have


FR-FD-03
Meetings today (from Google Calendar)
Must Have


FR-FD-04
Proposals pending response count
Must Have


FR-FD-05
Hot leads needing action (score >80, no touch >3 days)
Must Have


FR-FD-06
Agent activity summary (last 7 days)
Must Have


FR-FD-07
Revenue forecast (weighted pipeline value = deal value x deal probability)
Must Have


FR-FD-08
Stage-wise funnel chart
Must Have


FR-FD-09
Win/loss ratio last 30 days
Should Have





6. Non-Functional Requirements
Category
Requirement
Target
Performance
Dashboard initial load
< 2 seconds on 4G
Performance
Kanban board render (up to 200 cards)
< 1.5 seconds
Performance
API response time (95th percentile)
< 300ms
Availability
Uptime SLA
99.5% monthly
Security
Authentication
Supabase Auth with JWT, RLS enforced
Security
Row-Level Security
Agents see only assigned leads; Admin sees all
Security
Data encryption at rest
Supabase-managed AES-256
Security
HTTPS
TLS 1.3 enforced
Scalability
Initial target users
1-10 agents
Scalability
Lead records supported
Up to 10,000 in MVP
Accessibility
WCAG compliance
2.1 AA
Browser support
Chrome, Firefox, Safari, Edge
Latest 2 versions
Responsive
Mobile-friendly
Usable on mobile, optimised for desktop



7. Business Pipeline Definition
The Dracara Growth OS pipeline is purpose-built for software services and goes beyond typical CRM close events:

Stage
Description
Exit Criteria
1. Prospect
Initial lead identified. No contact made yet.
Contact info verified
2. Contacting
First outreach sent (cold email, LinkedIn, call).
Positive response received
3. Discovery Call Scheduled
Call booked on calendar.
Discovery call completed
4. Requirements Gathering
Understanding client problem, scope, budget.
Requirements documented
5. Solution Design
Architecture, scope, and tech stack defined.
Scope document approved internally
6. Proposal Sent
Formal proposal delivered to client.
Client acknowledged receipt
7. Negotiation
Price, scope, or timeline discussions underway.
Agreement in principle reached
8. Won
Contract signed / project confirmed.
Opportunity created, delivery team briefed
9. Delivery Transition
Active project; upsell opportunities tracked.
Project delivered
10. On Hold
Paused by client decision.
Follow-up date set
11. Follow-Up Later
Not ready now; nurture cadence active.
Re-engagement date set
12. Lost
Deal closed-lost with reason.
Loss reason recorded



8. Success Metrics (KPIs)
Metric
Target
Measurement Period
Follow-up slippage rate
< 5% of scheduled follow-ups missed
Weekly
Proposal turnaround time
< 72 hours from requirements to proposal sent
Per deal
Pipeline coverage ratio
3x revenue target in active pipeline
Monthly
Lead-to-Won conversion rate
Baseline in month 1; 20% improvement by month 3
Monthly
Agent activity compliance
> 90% of assigned leads with activity in last 14 days
Weekly
Dashboard daily active usage
100% (founder opens daily)
Daily


PART 2: TECHNICAL DESIGN DOCUMENT (TDD)

9. System Architecture Overview
Dracara Growth OS follows a decoupled client-server architecture. The frontend is a Next.js 16 application deployed on Vercel, communicating with a FastAPI backend deployed on Railway (or Render). Supabase provides the Postgres database, Row-Level Security, real-time subscriptions, file storage, and authentication. A Redis + Celery worker layer handles background jobs including follow-up reminders and the daily brief.

9.1 High-Level Architecture
Layer
Technology
Responsibility
Frontend
Next.js 16 (App Router), TypeScript, Tailwind CSS, shadcn/ui
UI, routing, server components, API calls
State Management
TanStack Query v5 (React Query)
Server state, caching, optimistic updates
Backend API
FastAPI (Python 3.12)
REST API, business logic, Google Calendar, Supabase client
Database
Supabase (PostgreSQL 15)
Relational data, RLS, full-text search
Auth
Supabase Auth
JWT tokens, OAuth (Google), magic links
File Storage
Supabase Storage
Proposal PDFs, attachments
Real-Time
Supabase Realtime
Live pipeline updates, activity feed
Background Jobs
Celery + Redis
Follow-up reminders, 14-day alerts, daily brief
Email
Resend (or SendGrid)
Daily brief email, task notifications
Calendar
Google Calendar API v3
Event CRUD, OAuth 2.0 per user
CI/CD
GitHub Actions
Test, lint, deploy on push to main
Hosting (FE)
Vercel
Edge-optimised Next.js deployment
Hosting (BE)
Railway
FastAPI + Celery containers


9.2 Monorepo Structure
The project uses a Turborepo monorepo:

dracara-growth-os/
  apps/
    web/          # Next.js 16 frontend
    api/           # FastAPI backend
    worker/        # Celery background jobs
  packages/
    types/         # Shared TypeScript types + Pydantic schemas
    ui/            # Shared shadcn/ui component wrappers
    config/        # ESLint, Tailwind, tsconfig presets



10. Database Design
10.1 Entity-Relationship Summary
Core entities and their relationships:
users → many leads (as owner)
companies → many contacts, many leads
leads → many activities, many tasks, many meetings
leads → one opportunity (on conversion)
opportunities → many proposals, many scope_versions
meetings → one meeting_outcome
tasks → one user (owner), one lead

10.2 Table Schemas
Table: users
Column
Type
Constraints
Notes
id
UUID
PK, DEFAULT gen_random_uuid()
Supabase Auth UID
email
TEXT
UNIQUE NOT NULL


full_name
TEXT
NOT NULL


role
ENUM
NOT NULL DEFAULT 'agent'
admin | agent | sdr | partner
avatar_url
TEXT
NULLABLE


google_access_token
TEXT
NULLABLE, ENCRYPTED
Per-user Google OAuth token
google_refresh_token
TEXT
NULLABLE, ENCRYPTED


is_active
BOOLEAN
DEFAULT TRUE
Soft deactivate
created_at
TIMESTAMPTZ
DEFAULT NOW()


updated_at
TIMESTAMPTZ
DEFAULT NOW()




Table: companies
Column
Type
Constraints
Notes
id
UUID
PK


name
TEXT
NOT NULL


industry
TEXT
NULLABLE


size
TEXT
NULLABLE
e.g. 1-10, 11-50
website
TEXT
NULLABLE


location
TEXT
NULLABLE


created_by
UUID
FK users.id


created_at
TIMESTAMPTZ
DEFAULT NOW()




Table: contacts
Column
Type
Constraints
Notes
id
UUID
PK


company_id
UUID
FK companies.id


full_name
TEXT
NOT NULL


role
TEXT
NULLABLE
CTO, Founder, etc.
email
TEXT
NULLABLE


phone
TEXT
NULLABLE


linkedin_url
TEXT
NULLABLE


is_primary
BOOLEAN
DEFAULT FALSE
Primary contact for company
created_at
TIMESTAMPTZ
DEFAULT NOW()




Table: leads
Column
Type
Constraints
Notes
id
UUID
PK


company_id
UUID
FK companies.id NOT NULL


primary_contact_id
UUID
FK contacts.id NULLABLE


owner_id
UUID
FK users.id NOT NULL
Assigned agent
stage
ENUM
NOT NULL DEFAULT 'prospect'
Full stage enum below
project_type
ENUM
NOT NULL
mvp | saas | ai | webapp | erp | other
lead_source
ENUM
NOT NULL
cold_call | referral | website | linkedin | other
estimated_value
NUMERIC(12,2)
NULLABLE
INR or USD
currency
TEXT
DEFAULT 'INR'


deal_probability
SMALLINT
DEFAULT 50, CHECK 0-100
% likelihood to close
priority_score
SMALLINT
DEFAULT 0
Calculated 0-100
last_contact_date
DATE
NULLABLE


next_followup_date
DATE
NULLABLE


is_opportunity
BOOLEAN
DEFAULT FALSE
Set on conversion
tags
TEXT[]
DEFAULT '{}'
Array of tags
created_at
TIMESTAMPTZ
DEFAULT NOW()


updated_at
TIMESTAMPTZ
DEFAULT NOW()




Stage enum values: prospect | contacting | discovery_scheduled | requirements_gathering | solution_design | proposal_sent | negotiation | won | delivery_transition | on_hold | followup_later | lost

Table: lead_intelligence (Founder CRM Profile)
Column
Type
Constraints
Notes
id
UUID
PK


lead_id
UUID
FK leads.id UNIQUE NOT NULL
One-to-one with lead
pain_points
TEXT
NULLABLE
Rich text / markdown
tech_stack
TEXT
NULLABLE
Client's current stack
budget_hints
TEXT
NULLABLE
Inferred/stated budget context
decision_makers
TEXT
NULLABLE
Names, roles, influence
competitors_involved
TEXT
NULLABLE
Other vendors being evaluated
objections_raised
TEXT
NULLABLE
Objections noted in calls
strategic_notes
TEXT
NULLABLE
Founder's private notes
comm_preference
ENUM
DEFAULT 'email'
whatsapp | email | linkedin | phone | call
updated_at
TIMESTAMPTZ
DEFAULT NOW()


updated_by
UUID
FK users.id




Table: activities
Column
Type
Constraints
Notes
id
UUID
PK


lead_id
UUID
FK leads.id NOT NULL


type
ENUM
NOT NULL
call | email | meeting | note | stage_change | proposal_sent | task_created | task_completed | document_uploaded
description
TEXT
NOT NULL


outcome
TEXT
NULLABLE


performed_by
UUID
FK users.id NOT NULL


performed_at
TIMESTAMPTZ
DEFAULT NOW()


metadata
JSONB
NULLABLE
Flexible: old_stage, new_stage, task_id, etc.


Table: tasks
Column
Type
Constraints
Notes
id
UUID
PK


lead_id
UUID
FK leads.id NOT NULL


owner_id
UUID
FK users.id NOT NULL


title
TEXT
NOT NULL


notes
TEXT
NULLABLE


due_date
DATE
NOT NULL


due_time
TIME
NULLABLE


status
ENUM
DEFAULT 'pending'
pending | snoozed | completed | cancelled
outcome_note
TEXT
NULLABLE
On completion
snoozed_until
DATE
NULLABLE


completed_at
TIMESTAMPTZ
NULLABLE


created_at
TIMESTAMPTZ
DEFAULT NOW()




Table: meetings
Column
Type
Constraints
Notes
id
UUID
PK


lead_id
UUID
FK leads.id NOT NULL


owner_id
UUID
FK users.id NOT NULL


title
TEXT
NOT NULL


google_event_id
TEXT
NULLABLE, UNIQUE
Google Calendar event ID
google_meet_link
TEXT
NULLABLE


scheduled_at
TIMESTAMPTZ
NOT NULL


duration_minutes
INTEGER
DEFAULT 30


status
ENUM
DEFAULT 'scheduled'
scheduled | completed | cancelled | rescheduled
outcome
ENUM
NULLABLE
interested | needs_proposal | budget_issue | not_interested | followup_later
outcome_notes
TEXT
NULLABLE


created_at
TIMESTAMPTZ
DEFAULT NOW()




Table: opportunities

**Pipeline model:** One opportunity row per lead (shell inserted when the lead is created). Kanban reads and writes `opportunities.stage` (`lead_stage` enum). Commercial detail (`quoted_value`, CPQ text fields) lives here; `proposals` FK targets `opportunities.id`. `leads.stage` / `estimated_value` mirror the opportunity for scoring helpers and older clients — maintained by DB triggers on opportunity updates, not duplicate business concepts.

Column
Type
Constraints
Notes
id
UUID
PK


lead_id
UUID
FK leads.id UNIQUE NOT NULL
Converted from lead
owner_id
UUID
FK users.id NOT NULL


title
TEXT
NOT NULL
Human-readable label (default shell: “Opportunity”)
stage
lead_stage
NOT NULL
Kanban position; mirrored on leads for scoring
deal_probability
SMALLINT
NOT NULL, 0–100
Mirrored on leads
priority_score
SMALLINT
NOT NULL, 0–100
Display tier; mirrored on leads
tags
TEXT[]
NOT NULL DEFAULT {}
Pipeline labels copied from lead at insert/sync


quoted_value
NUMERIC(12,2)
NULLABLE
Final quoted price
currency
TEXT
DEFAULT 'INR'


timeline_weeks
INTEGER
NULLABLE
Estimated delivery weeks
tech_stack
TEXT
NULLABLE
Proposed tech stack
requirements_doc
TEXT
NULLABLE
Rich text requirements
architecture_notes
TEXT
NULLABLE


status
ENUM
DEFAULT 'active'
active | won | lost | on_hold
created_at
TIMESTAMPTZ
DEFAULT NOW()


updated_at
TIMESTAMPTZ
DEFAULT NOW()




Table: proposals
Column
Type
Constraints
Notes
id
UUID
PK


opportunity_id
UUID
FK opportunities.id NOT NULL


version
INTEGER
NOT NULL DEFAULT 1
Auto-increment per opportunity
title
TEXT
NOT NULL


file_url
TEXT
NULLABLE
Supabase Storage URL
figma_url
TEXT
NULLABLE


github_url
TEXT
NULLABLE


loom_url
TEXT
NULLABLE


quoted_price
NUMERIC(12,2)
NULLABLE


change_notes
TEXT
NULLABLE
What changed from prev version
status
ENUM
DEFAULT 'draft'
draft | sent | under_review | accepted | rejected
sent_at
TIMESTAMPTZ
NULLABLE


created_by
UUID
FK users.id


created_at
TIMESTAMPTZ
DEFAULT NOW()





11. Row-Level Security (RLS) Policies
Table
Policy
Rule
leads
Agents: SELECT own leads
auth.uid() = owner_id OR role = 'admin'
leads
Agents: INSERT
auth.uid() IS NOT NULL
leads
Agents: UPDATE own leads
auth.uid() = owner_id OR role = 'admin'
leads
Admin: all access
role = 'admin' (via users table join)
lead_intelligence
Same as leads
Via lead_id foreign key join
activities
Read all activities for accessible leads
lead_id in accessible leads
tasks
Agents see own tasks; Admin sees all
owner_id = auth.uid() OR admin
meetings
Same as tasks
owner_id = auth.uid() OR admin
users
Read own profile; Admin reads all
id = auth.uid() OR admin
proposals
Read via opportunity → lead ownership
Joined check



12. Backend API Design (FastAPI)
12.1 Router Structure
POST   /auth/google                — Exchange Google OAuth code
GET    /leads                       — List leads (filtered, paginated)
POST   /leads                       — Create lead
GET    /leads/{id}                  — Get lead detail (with intelligence, activities)
PATCH  /leads/{id}                  — Update lead fields
PATCH  /leads/{id}/stage            — Move stage (triggers activity log)
POST   /leads/{id}/convert          — Convert lead to opportunity
GET    /leads/{id}/activities        — Activity timeline
POST   /leads/{id}/activities        — Log activity
GET    /leads/{id}/tasks             — Tasks for lead
POST   /leads/{id}/tasks             — Create task
PATCH  /tasks/{id}                  — Update task (snooze, complete)
GET    /leads/{id}/meetings          — Meetings for lead
POST   /leads/{id}/meetings          — Schedule meeting (creates Google event)
PATCH  /meetings/{id}/outcome        — Record meeting outcome (auto-tasks)
GET    /opportunities/{id}           — Opportunity with proposals
POST   /opportunities/{id}/proposals — Upload proposal version
GET    /dashboard                    — Aggregated dashboard data
GET    /dashboard/followups          — Today + overdue follow-ups
GET    /agents                       — List agents (admin)
POST   /agents/invite                — Invite agent
GET    /agents/{id}/performance      — Agent metrics

12.2 Opportunity Score Calculation
The score is calculated on every lead update by a FastAPI dependency:

score = (
  budget_fit   * 0.25 +   # estimated_value vs. typical project range
  urgency      * 0.20 +   # days to decision from requirements
  authority    * 0.20 +   # is decision-maker in CRM profile?
  project_size * 0.15 +   # estimated_value bucket score
  probability  * 0.20     # deal_probability / 100 * 100
) rounded to integer

Each dimension is normalised 0–100 before weighting. Final score is stored in leads.priority_score.


13. Frontend Architecture (Next.js 16)
13.1 Route Structure (App Router)
Route
Page
Description
/
redirect
→ /dashboard
/login
Login
Supabase Auth UI / Google OAuth
/dashboard
Founder Dashboard
Cockpit view — widgets, metrics
/pipeline
Lead Kanban
Drag-and-drop Kanban board
/leads/[id]
Lead 360 View
Full lead detail with tabs
/leads/[id]/intelligence
CRM Profile
Business intelligence panel
/leads/[id]/timeline
Activity Timeline
Chronological activities
/leads/[id]/meetings
Meetings
Meeting history + schedule
/opportunities/[id]
Opportunity View
Pre-sales workspace
/opportunities/[id]/proposals
Proposals
Versioned proposals
/follow-ups
Follow-Up Engine
Today, overdue, upcoming queue
/calendar
Calendar View
Embedded Google Calendar + meeting list
/agents
Agent Management
Admin: agents, performance dashboard
/reports
Reports
Pipeline analytics, funnel, win-loss
/settings
Settings
Org settings, pipeline stages, score weights


13.2 Component Architecture
layout/AppShell — sidebar, header, notification bell
pipeline/KanbanBoard — DnD board, stage columns, lead cards
pipeline/LeadCard — compact card with score badge, followup indicator
leads/LeadDetail — tabbed 360 view component
leads/IntelligencePanel — CRM profile rich form
leads/ActivityFeed — timeline with type icons
followups/FollowUpQueue — sorted task list with snooze/complete actions
meetings/MeetingScheduler — Google Calendar event creator
meetings/OutcomeModal — post-call outcome capture
dashboard/MetricCard — KPI card widget
dashboard/FunnelChart — Recharts funnel visualization
dashboard/PipelineValueBar — stage breakdown bar chart
agents/AgentPerformanceTable — metrics table
shared/OpportunityScoreBadge — Hot/Warm/Cold badge

13.3 State Management
TanStack Query v5 handles all server state. Patterns used:
useLeads(filters) — paginated lead list with infinite scroll
useLead(id) — single lead with all relations
useActivities(leadId) — timeline activities
useTasks(filters) — today/overdue/upcoming
useDashboard() — aggregated dashboard data
useMeetings(leadId?) — meetings list
Optimistic updates on stage moves (Kanban drag)
Supabase Realtime subscription invalidates lead queries on changes


14. Google Calendar Integration
14.1 OAuth 2.0 Flow
User clicks 'Connect Google Calendar' in Settings
Frontend redirects to /auth/google (FastAPI route)
FastAPI builds Google OAuth URL with scopes: calendar.events, calendar.readonly
User approves; Google redirects back with code
FastAPI exchanges code for access_token + refresh_token
Tokens stored encrypted in users.google_access_token, users.google_refresh_token
All subsequent calendar calls use per-user token with auto-refresh on expiry

14.2 Meeting Sync Logic
Create meeting in CRM → POST to Google Calendar API → store google_event_id on meeting row
Pull meetings → GET from Google Calendar list API → sync into meetings table (upsert on google_event_id)
Delete from CRM → DELETE Google Calendar event via API
Post-meeting outcome capture → triggered by scheduled Celery task 5 minutes after meeting end_time
Auto-task creation → on outcome save, if outcome requires follow-up, create task with computed due_date


15. Background Jobs (Celery + Redis)
Job
Schedule
Description
daily_brief
08:00 AM daily (cron)
Aggregate today's follow-ups, meetings, hot leads. Send email to admin via Resend.
followup_reminder
Every 30 min
Find tasks with due_date = today and status = pending. Push in-app notification.
no_touch_alert
Every 6 hours
Find leads with last_contact_date < now - 14 days. Flag with no_touch_alert = true.
score_recalculate
Every 1 hour
Recalculate priority_score for leads updated in last hour.
calendar_sync
Every 15 min (per user)
Pull upcoming Google Calendar events and upsert into meetings table.
post_meeting_prompt
5 min after meeting end_time
Push outcome capture modal notification to meeting owner.
overdue_escalation
09:00 AM daily
Find overdue tasks not completed. Notify task owner and admin.



16. Authentication & Security
16.1 Auth Flow
User authenticates via Supabase Auth (email/password or Google OAuth)
Supabase issues JWT with user id and role claim
Frontend stores JWT in memory (not localStorage); uses Supabase JS client
All FastAPI endpoints validate JWT via Supabase JWT secret
FastAPI extracts user_id and role from token; applies business-logic RBAC on top of DB-level RLS

16.2 RBAC Matrix
Permission
Admin
SDR
Follow-Up Agent
Sales Partner
View all leads
Yes
Own only
Own only
Assigned only
Create leads
Yes
Yes
No
No
Move stage
Yes
Yes
Yes
No
Reassign lead
Yes
No
No
No
Log activity
Yes
Yes
Yes
Yes (view only for notes)
View intelligence
Yes
Yes
Yes
No
Edit intelligence
Yes
Yes
No
No
Create/edit proposals
Yes
Yes
No
View only
View all agents
Yes
No
No
No
Invite agents
Yes
No
No
No
View reports
Yes
Yes
No
No



17. Infrastructure & Deployment
17.1 Environment Configuration
Variable
Service
Notes
SUPABASE_URL
FastAPI + Frontend
Project URL from Supabase dashboard
SUPABASE_ANON_KEY
Frontend
Public anon key
SUPABASE_SERVICE_KEY
FastAPI (server)
Service role key — never exposed to client
SUPABASE_JWT_SECRET
FastAPI
For JWT validation
GOOGLE_CLIENT_ID
FastAPI
Google OAuth credentials
GOOGLE_CLIENT_SECRET
FastAPI


GOOGLE_REDIRECT_URI
FastAPI
Backend callback URL
REDIS_URL
FastAPI + Celery worker
Redis connection string
RESEND_API_KEY
Celery worker
For daily brief emails
NEXT_PUBLIC_API_URL
Frontend
FastAPI base URL
NEXT_PUBLIC_SUPABASE_URL
Frontend


NEXT_PUBLIC_SUPABASE_ANON_KEY
Frontend




17.2 CI/CD Pipeline (GitHub Actions)
PR opened → run ESLint, TypeScript check, Pytest suite
PR merged to main → build Docker images (api, worker)
Push images to GitHub Container Registry
Railway auto-deploys on new image tag
Vercel auto-deploys frontend on push to main
Supabase migrations run via supabase db push in CI step


18. MVP Build Phases
Phase
Scope
Duration
Deliverable
Phase 0: Setup
Turborepo init, Supabase project, Vercel + Railway setup, auth wiring, base shadcn/ui layout
3 days
Working shell with login
Phase 1: Core Data
DB migrations, RLS policies, FastAPI router scaffolding, lead CRUD, company/contact CRUD
5 days
API tests passing, data model live
Phase 2: Kanban
Lead Kanban with DnD, stage transitions, activity auto-log, lead card UI
4 days
Draggable pipeline UI
Phase 3: Lead 360
Lead detail view, CRM intelligence panel, activity timeline, task creation
4 days
Full lead detail screen
Phase 4: Follow-Up Engine
Task queue, overdue alerts, 14-day no-touch job, in-app notifications
3 days
Daily follow-up workflow live
Phase 5: Calendar
Google OAuth, calendar sync, meeting scheduler, outcome modal, auto-tasks
5 days
Google Calendar fully integrated
Phase 6: Proposals
Opportunity workspace, proposal versioning, file upload to Supabase Storage
3 days
Pre-sales workspace complete
Phase 7: Agents
Invite flow, RBAC enforcement, performance dashboard, @mention
3 days
Multi-agent ready
Phase 8: Dashboard
Founder cockpit widgets, funnel chart, revenue forecast, pipeline value
3 days
Dashboard complete
Phase 9: Polish + QA
Responsive fixes, error states, loading skeletons, E2E tests, security audit
5 days
Production-ready MVP


Total estimated MVP duration: ~38 developer days (solo) or ~20 days with one additional developer.


19. Testing Strategy
19.1 Backend (FastAPI)
Pytest with async test client (httpx)
Test coverage target: >80%
Unit tests: score calculator, outcome-to-task mapper, stage transition validator
Integration tests: full CRUD for leads, activities, tasks, meetings against Supabase test instance
Auth tests: RLS enforcement — agent cannot read unassigned lead (expect 403)

19.2 Frontend (Next.js)
Vitest + React Testing Library for component unit tests
MSW (Mock Service Worker) for API mocking in component tests
Playwright E2E tests for critical flows: login, create lead, move stage, schedule meeting, complete task
Storybook for UI component documentation and visual review

19.3 Test Environments
Local: Docker Compose — FastAPI + Redis + Supabase local
Staging: Railway staging service + Supabase staging project
Production: separate Supabase project with prod keys


20. Phase 2 AI Roadmap
Post-MVP AI features planned for Phase 2:

Feature
Implementation
Value
AI Call Notes
After call: send transcript to Claude claude-sonnet-4-20250514 → extract summary, action items, suggested follow-up date. Auto-populate activity note.
Removes manual note-taking
AI Proposal Drafting
Based on lead intelligence + requirements doc, Claude generates a proposal first draft. Founder edits and uploads final.
3x faster proposal creation
AI Deal Health Monitor
Nightly batch job: Claude analyzes pipeline data, flags stalled deals, at-risk leads, suggested interventions. Summary in daily brief.
Proactive pipeline management
AI Lead Scoring Enhancement
Replace weighted formula with ML model trained on historical win/loss data. Features: stage velocity, activity frequency, intelligence completeness.
More accurate prioritisation
WhatsApp Integration
Twilio WhatsApp API: log inbound/outbound messages as activities. Trigger follow-up tasks from WhatsApp replies.
Capture all touchpoints
Email Sync
Gmail API: bi-directional email sync per contact. Auto-log email threads as activities.
Full communication history



21. Risk Register
Risk
Likelihood
Impact
Mitigation
Google Calendar OAuth token expiry breaks sync
High
Medium
Implement token refresh interceptor in FastAPI; alert user if refresh fails
Supabase RLS misconfiguration exposes cross-agent data
Medium
High
Automated RLS integration test in CI that verifies access control per role
Celery job queue backlog during heavy load
Low
Medium
Redis priority queues; monitor queue length with alerting
Proposal file storage costs escalate
Low
Low
Enforce 50MB file limit; Supabase Storage tiered pricing reviewed monthly
Google Calendar rate limits (1M queries/day per project)
Low
Medium
Exponential backoff + per-user sync throttling
Scope creep from multi-agent feature requests
High
Medium
Strict MVP scope freeze; Phase 2 backlog for non-MVP requests



22. Glossary
Term
Definition
Lead
A prospect company or contact that has not yet been qualified as a revenue opportunity.
Opportunity
A lead that has been qualified and converted — representing an active pre-sales effort with a proposal in progress.
Pipeline
The set of all leads and opportunities organized by sales stage.
Activity
Any logged touchpoint or event against a lead: call, email, meeting, note, stage change, etc.
Task
A scheduled action item with a due date — the atomic unit of the Follow-Up Engine.
Founder CRM Profile
The business intelligence layer attached to each lead, capturing strategic context beyond standard contact fields.
Priority Score
A calculated 0-100 score representing how likely and valuable a lead is to close. Drives Kanban sorting and dashboard alerts.
Delivery Transition
A post-close stage unique to agency CRMs — tracking active delivery and upsell potential after contract sign.
RLS
Row-Level Security — Supabase/PostgreSQL feature ensuring database queries are automatically filtered by the authenticated user's permissions.
Daily Brief
An automated morning email and dashboard digest summarising the founder's most urgent actions for the day.





23. Changelog Since v1.0
This document was frozen at v1.0 scope: single-tenant, four fixed roles, zero AI. Everything below has shipped since, grouped by theme rather than commit. Where a change makes an earlier section inaccurate, that section is called out explicitly in §23.5 rather than silently rewritten — treat the codebase, not this document, as the source of truth for anything flagged stale there.

23.1 Platform hardening (pre-multi-tenancy)
Change
Summary
API layering & versioning
Backend restructured into a layered architecture; every route moved under /api/v1, with rate limiting, structured Problem Details errors, and security headers added.
Test coverage expansion
Backend suite grew from 7 tests to 110+, and now 201 as of the AI voice agents feature (23.4).
Data integrity fixes
RLS policy repairs, contact-visibility fixes, a NOT NULL trigger violation fix, currency correctness, stable pagination, timezone-correct scheduling.
Optimistic concurrency + audit trail
Every mutable row carries a version column; writes are conditional via If-Match/ETag; a new audit_log table records who changed what.
Idempotent creates & recoverable deletes
Idempotency-Key support on POST; every delete across leads/contacts/companies/opportunities is a soft delete (recoverable), not a hard delete.
Leads/opportunities single-owner-per-fact refactor
leads and opportunities were split so each fact (qualification data vs. pursuit data) has exactly one owner table — superseding §10.2's leads schema, which still shows stage, estimated_value and is_opportunity as columns directly on leads.
Full CRUD coverage
Create/edit/delete drawers built out across every resource page; the dashboard now reads real aggregated queries instead of placeholder data.

23.2 Multi-tenant organizations
Dracara Growth OS is no longer single-tenant. A new organizations table roots every tenant-owned row (organization_id on every table, auto-populated by database triggers — never client-supplied), with self-serve signup (an unrecognized signup mints a brand-new organization) and an invite-token flow (org_invites: single-use, expiring, email-pinned) for adding teammates to an existing one. This makes §16 (Authentication & Security) and the single-workspace assumption running through Part 1 incomplete: every permission and RLS rule described there now also carries an implicit "...within your own organization" boundary.

23.3 Dynamic, admin-configurable RBAC
§10.2's users.role enum (admin | agent | sdr | partner) and §16.2's fixed RBAC matrix are both superseded. Roles are no longer a fixed enum — they are organization-owned data in a new roles table (a name, a grants_full_access flag replacing the old binary "is admin", and a checklist of granted permissions from a permissions catalog). An admin can rename, edit, delete, or create roles and assign granular permissions (e.g. leads.write, voice_agents.manage) to them from the "User management" screen. The four original roles still exist as the seeded defaults for every new organization, but they are now a starting point, not a hard ceiling. Row-level visibility is unchanged by this — still: own your records, or hold a role with grants_full_access; permissions are feature gates layered on top of that, not a replacement for it.

23.4 AI voice sales agents (first AI feature; partially overlaps §20's Phase 2 AI roadmap)
An organization admin can create an AI voice agent — a system prompt, a phone number, and supporting documents (upload works; wiring the uploaded documents into the agent's live knowledge does not yet) — that places outbound calls and answers inbound calls via Twilio plus a managed voice-AI platform (Vapi). Mid-call, the agent can call back into the CRM through a tool-calling bridge: check a contact's consent, pull a lead's context, log a call outcome, update a deal's stage, or book a meeting. Every call is logged to a new calls table and summarized onto the lead's activity timeline; the owning rep is notified through the existing notification system when a call completes.

This is not the Phase 2 roadmap as originally scoped in §20 — there is no AI call-note extraction, no AI proposal drafting, no ML-based lead scoring, and no WhatsApp/email sync. [Superseded by §23.6 for the first two; ML scoring and WhatsApp/email sync remain outstanding.] It is a separate capability (AI-driven calling) that §20 did not anticipate.

Compliance is built into the schema, not left to policy: an outbound call is blocked unless that specific contact has an explicit consent flag set (the block itself is logged, not silently dropped), a fixed recording-disclosure line plays at the start of every call regardless of what the admin's prompt says, and the whole feature is gated behind a one-time, org-wide compliance acknowledgment.

No vector database is in use. The agent's mid-call knowledge comes entirely from live tool-calls into Postgres — the same data every other screen reads — not a vector index or embeddings store. [Superseded by §23.6: Qdrant now backs the agent's uploaded-document knowledge base, alongside those live tool-calls.]

23.6 The AI layer: RAG, agent orchestration, and most of §20's roadmap
Six things shipped together, on one shared foundation.

Foundation. A new workspace package, packages/ai (dracara_ai), holds every model call, every prompt and every workflow in the product. It is installed into both apps/api and apps/worker from the workspace, for the same reason packages/scoring is — two copies of a prompt drift apart silently. LangGraph is the orchestration primitive; OpenAI is the provider. The rule that makes the package safe to share: graphs are pure. A graph takes plain data in and returns a Pydantic model out; it holds no database handle and resolves no organization_id. All database I/O and all tenant scoping stay in the caller.

Vector store. Qdrant, self-hosted via a new docker-compose.yml at the repo root — the first compose file in this repository. One collection, voice_agent_kb, carrying organization_id, voice_agent_id and document_id on every point's payload.

Qdrant has no row-level security, which makes it the only store in this product where a forgotten filter fails open rather than closed — it returns results, just the wrong tenant's. So organization_id is a required keyword-only argument on every read and delete in vector_store.py, applied inside that module rather than by its callers, with no "search everything" variant to reach for later. A payload that comes back carrying the wrong tenant is dropped and logged rather than served.

Voice-agent knowledge base. §23.4 recorded that uploading documents worked but wiring them into the agent's live knowledge did not. It does now: on upload the file is extracted (PDF/Word/text/Markdown/CSV), chunked, embedded and indexed, and a sixth mid-call tool, search_knowledge_base, lets the agent quote from it. Indexing failure never fails an upload — the file is stored, the reason is recorded on the row, and the worker retries it. The document list shows which state each file is in, because "uploaded" and "the agent can quote this" are not the same thing, and before this they were silently never the same thing.

Relatedly: the five existing mid-call tools were never declared to the voice platform at all. The dispatcher existed and the webhook could route a tool call, but no assistant was ever told the tools existed, so nothing could call them unless someone wired it up by hand in the vendor dashboard. voice_platform.py now declares all six, and a test asserts the declared set and the dispatchable set stay equal.

The CRM assistant. The "Ask AI" drawer was undocumented in this design record, unauthenticated, and built on mismatched SDK versions (@ai-sdk/react@4 against a route written for ai@3, both files carrying // @ts-nocheck). It is rebuilt as POST /api/v1/ai/chat. The security fix is architectural rather than a patch: the assistant no longer receives CRM context from the browser — it has seven read-only tools bound to the caller's own RLS-scoped connection. Postgres decides what the model can see, exactly as it does for every screen. There is no organization_id anywhere in that module, because there is nothing there that could use one correctly; a user — or an injected instruction sitting inside a CRM note — can ask for another organization's leads and the query still runs as them and returns nothing. The web app no longer holds an API key or talks to a model provider.

AI call notes (§20). A worker job every two minutes summarises completed calls that have a transcript, extracts action items, judges sentiment and suggests a follow-up date. It writes to new ai_* columns beside the platform's own summary rather than over it, creates a task per action item owned by the lead's owner, logs the summary to the activity timeline, and notifies the rep. Polling rather than webhook-driven: the voice platform waits on the webhook's response, and a model call would blow its timeout — the same reasoning as stale_call_reconciliation.

AI deal health monitor (§20). A pass at 07:00 over every organization's open pipeline, writing to a new deal_health_snapshots table and notifying owners of high-risk deals only. The graph's first node is deterministic: a deal touched recently, on schedule, with a next step booked is cleared in Python without any model call. Without that gate the job's cost scales with total pipeline size instead of with the number of deals actually worth looking at. Each snapshot records which of the two cleared it, so "nothing looked wrong" stays distinguishable from "a model considered this and cleared it". Findings reach owners per-tenant through a deal_at_risk notification and a dashboard card — deliberately not the 08:00 daily brief, which still goes to a single global ADMIN_EMAIL left over from before multi-tenancy and would otherwise mail every organization's deals to one address.

AI proposal drafting (§20). POST /api/v1/ai/proposals/{id}/draft builds a draft from lead intelligence, the opportunity's requirements and retrieved reference material, then persists it through the existing proposals.create_version — inheriting its unique-violation retry, so two people pressing the button at once cannot collide on a version number. It is always a draft for a human to edit; the prompt is instructed to leave visible [CONFIRM: …] placeholders rather than invent a price.

Authorization. A real gap predating this work: the API checked granular permissions via require_permission(), but RLS could only ever check is_admin(), because no SQL-side has_permission() existed at all. voice_agents.py carried a docstring admitting the two layers disagreed. has_permission(uid, resource, action) now exists as a chokepoint beside is_admin() — never inlined into a policy, per the can_access_lead() lesson — and the voice-agent write policies use it. Two new permissions: ai.read (granted to Agent/SDR by default; the assistant can only show a rep what the CRM already shows them) and ai.manage (admin only, because it exposes spend).

Cost control. Every AI call is attributed to an organization in a new ai_usage table, and AI_MONTHLY_TOKEN_BUDGET refuses new work past a ceiling with a 429. One API key serves every tenant: without attribution there is no way to answer which organization caused a bill, and without a ceiling one tenant can spend everyone's.

Calendar push. calendar_sync only ever pulled from Google, which is why book_appointment used to end by telling the caller the meeting would not reach the rep's calendar. A calendar_push job now forwards CRM-created meetings, sharing one credential helper with the pull direction so the two cannot drift on scopes, and the tool says "it will appear shortly" instead of apologising.

Company research and pre-call briefs (not in §20; the largest competitive gap). A rep can research a company from the public web via Exa and get a cited profile — description, industry, size, segment, location, recent news, tech signals — plus suggested edits to the company record, and can generate a pre-call brief for a lead from its CRM facts and that research. Only the company's name and website ever reach the search provider. Web text is treated as hostile: the research graph cannot act, every claim must cite a source it was actually given (verified in code, not requested in the prompt), and nothing is written to a company until a person accepts a suggestion through the ordinary edit path with its version check. Stored in company_research and lead_briefs (20260918010000), written only by the service role with organization derived by trigger, and readable exactly as widely as the company or lead they describe.

Deployment notes. Applying 20260918000000 to a real database surfaced two defects that 385 passing tests had not: permissions.action is an enum (has_permission() needed a cast), and 'use' was not a value of it (ai.use became ai.read; an enum value cannot be added and used in one transaction). Live verification also confirmed the organization triggers overwrite a forged organization_id even from the service role, and that RLS rejects well-formed writes to every new table from an unauthenticated session.

Still not shipped from §20: WhatsApp integration, email sync, and ML-based lead scoring (the weighted formula in packages/scoring stands; an ML model needs a few hundred closed deals before it beats a heuristic).


23.7 SaaS readiness: signup, password reset, invite acceptance, and billing
Self-serve onboarding now exists in the product, not just in the database. /signup creates an account whose metadata names the new organization (handle_new_user() already minted one for any un-invited signup); /forgot-password sends a reset link; and every emailed auth link lands on /auth/confirm, which accepts all three shapes Supabase can deliver (PKCE ?code=, invite #access_token= fragments, and token_hash templates) before forwarding to its next= target — which only honours same-origin paths, closing an open redirect the old login page had. Invites now pass redirect_to so the invitee reaches /auth/set-password; before this an invited user had no password and no way to set one, so they could not sign in a second time. Middleware changed from a list of protected paths (which had missed /voice-agents) to an allow-list of public ones.
Billing runs on Dodo Payments (merchant of record: it handles sales tax and invoicing). Plans are per seat per month — Starter (core CRM), Growth (+ AI features), Scale (+ AI voice agents) — defined once in apps/api/app/services/billing.py, whose entitlements() is used by both enforcement and the UI. New organizations get a 14-day, no-card trial with every feature and 5 seats; when it lapses the workspace becomes read-only (every write on the CRM routers returns 402 subscription_inactive; reads are never gated). Features outside the plan return 402 plan_upgrade_required, and inviting or reactivating a user past the seat count returns 402 seat_limit_reached. State lives in organization_subscriptions, a table with a member SELECT policy and no write policies at all, so plan and status can only be set by the service role — deliberately not columns on organizations, which an admin may update. The webhook (/api/v1/billing-webhooks/dodo) verifies the Standard Webhooks signature, resolves the organization from the Dodo customer id the API stored at checkout (never from payload metadata), is idempotent on webhook-id via billing_events, and ignores out-of-order events. Billing is a commercial gate, not a security boundary: a missing subscription row fails open.
The worker's scheduled AI jobs were not yet plan-gated when this shipped; see §23.8.


23.8 Release hardening
Deployment: one Dockerfile per app, built from the repo root (apps/api, apps/worker — which also runs beat — and apps/web as a Next.js standalone server), plus docker-compose.prod.yml for a single host. Error monitoring: Sentry in all three, inert without a DSN, with request bodies and PII never attached. Rate-limit counters can live in Redis (RATE_LIMIT_STORAGE_URI) with an in-memory fallback, and uvicorn runs with --proxy-headers so limits key on the real client. The API logs a production-config error at startup for each development-only setting still in place.
Plan catalog and entitlements() moved into packages/billing, shared by the API and the worker (the packages/scoring pattern). The worker's AI jobs now scan only organizations whose plan includes the feature, filtering inside the query so lapsed trials cannot starve paying customers' batches. This closes the gap §23.7 recorded.
The daily brief, previously one global email to ADMIN_EMAIL counting tasks across every organization, is now sent to each organization's full-access users about their own organization only, skipping lapsed ones, with an idempotency key per recipient per day.
Two latent schema-drift bugs fixed: overdue_escalation filtered users on the role column the dynamic-roles migration dropped, so it failed on every run and no overdue notifications were sent; agent performance counted wins on leads.stage, which moved to opportunities. The unit-test fakes ignore query parameters, which is how both passed; tests/test_schema_drift.py now checks every literal PostgREST filter in the API and worker against the columns the migrations define.
New users get their browser's timezone at signup (validated in handle_new_user) or on accepting an invite, instead of Asia/Kolkata, and the timezone pickers offer the full IANA list.


23.9 CSV import
Companies, contacts and leads can be imported from a CSV file at /import (and from an Import button beside Export on each list). The browser parses the file (RFC 4180, comma/semicolon/tab, BOM) and pre-maps its columns using aliases from the field catalog the API serves at GET /imports/fields, which cover HubSpot, Pipedrive, Zoho and Salesforce export headers. Rows go to POST /imports/{kind} in batches of 200.
Imports run as the caller under RLS, so an import can create only what its user could create by hand, and non-admins own everything they import (an owner column is honoured only for full-access users). Companies are matched by website domain then case-insensitive name, contacts by email (or by name within the company), and leads by company plus primary contact, so re-running a file creates nothing new. Validation happens before anything is written. Each table then gets one bulk insert, which falls back to row-by-row inserts when it fails, so one bad row never loses the rest of the batch. Ambiguous dates (03/04/2026) are refused rather than guessed. Every row gets a result, and failed rows can be downloaded as a CSV with the reason added, ready to fix and re-import. Imports are write operations, so the plan gate applies.


23.5 What in this document is now stale
Section
Why it's stale
§10.2, users table
role ENUM no longer exists; replaced by role_id → roles table (§23.3).
§11, RLS Policies table
Every role = 'admin' check shown here has been replaced by a roles.grants_full_access join; every policy also gained an organization-scoping clause not shown here (§23.2).
§16.2, RBAC Matrix
Describes four fixed roles with fixed permissions; roles and their permissions are now organization-configurable data (§23.3).
§12.1, Router Structure
Predates /api/v1 versioning and every endpoint added since — roles, permissions, organizations, voice agents, voice webhooks, billing. Treat as illustrative, not current.
§20, Phase 2 AI Roadmap
Three of the six have now shipped (§23.6): AI Call Notes, AI Proposal Drafting and AI Deal Health Monitor. That table's implementation notes are stale in one respect — they name Claude, and the shipped implementation uses OpenAI models through packages/ai. Still outstanding: ML lead scoring, WhatsApp integration, email sync.
Part 1, "the founder" / single workspace
The product now supports any number of independent organizations, each with their own founder/admin (§23.2).


Document End — Dracara Growth OS v1.0 BRD + TDD
dracara.dev  |  Confidential  |  Not for distribution
