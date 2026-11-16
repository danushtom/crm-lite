/**
 * Plain-English labels for the script vocabulary, and the agent-status rule.
 *
 * The keys here mirror `dracara_ai.voice_script`; the API validates against that module, so a
 * key that is wrong shows up as a 422 rather than as a silently ignored setting. What lives
 * here is only the wording a client reads -- never a second copy of the behaviour.
 */

import type { LeadField, ScriptGoal, ScriptTone, VoiceAgent, VoiceTool } from "@dracara/types";
import type { AgentStatusTone } from "@/components/voice-agents/agent-avatar";

export const GOALS: { value: ScriptGoal; label: string; blurb: string }[] = [
  { value: "qualify", label: "Qualify a new lead", blurb: "Work out whether it is worth a rep's time." },
  { value: "book_meeting", label: "Book a meeting", blurb: "Get a date and time in the diary." },
  { value: "follow_up", label: "Follow up on a proposal", blurb: "Find out where it stands." },
  { value: "reactivate", label: "Re-open a cold lead", blurb: "Check whether the project is still live." },
  { value: "collect_info", label: "Collect information", blurb: "Gather specific details accurately." },
  { value: "support", label: "Answer inbound questions", blurb: "Help the caller and route them." },
  { value: "custom", label: "Something else", blurb: "Describe it in the brief yourself." },
];

export const TONES: { value: ScriptTone; label: string; blurb: string }[] = [
  { value: "warm", label: "Warm", blurb: "Friendly and unhurried" },
  { value: "direct", label: "Direct", blurb: "Straight to the point" },
  { value: "formal", label: "Formal", blurb: "Professional and measured" },
  { value: "upbeat", label: "Upbeat", blurb: "Bright, never pushy" },
];

/** The four capabilities an organization actually chooses between. */
export const OPTIONAL_TOOLS: { value: VoiceTool; label: string; blurb: string; writes: boolean }[] = [
  {
    value: "get_lead_context",
    label: "Read CRM data about the lead",
    blurb: "Lets it open with what you already know instead of asking them to repeat it.",
    writes: false,
  },
  {
    value: "search_knowledge_base",
    label: "Search your uploaded documents",
    blurb: "Pricing, packages and FAQs. Without this it has to say it will follow up.",
    writes: false,
  },
  {
    value: "book_appointment",
    label: "Book meetings",
    blurb: "Puts a meeting on the lead owner's calendar during the call.",
    writes: true,
  },
  {
    value: "update_deal_stage",
    label: "Move deals between stages",
    blurb: "Updates your pipeline based on what the caller says.",
    writes: true,
  },
];

/** Not offered as choices: see ALWAYS_ON_TOOLS in the compiler for why. */
export const ALWAYS_ON_TOOLS: { label: string; blurb: string }[] = [
  { label: "Check calling consent", blurb: "How it confirms it is allowed to call at all." },
  { label: "Log the call outcome", blurb: "How the call reaches the lead's timeline." },
];

export const LEAD_FIELDS: { value: LeadField; label: string; blurb: string; sensitive?: boolean }[] = [
  { value: "company_name", label: "Company name", blurb: "Who they are" },
  { value: "project_type", label: "Project type", blurb: "The work they asked about" },
  { value: "stage", label: "Pipeline stage", blurb: "How far along the deal is" },
  { value: "tags", label: "Tags", blurb: "Labels your team added" },
  { value: "next_followup_date", label: "Next follow-up", blurb: "When you said you would call" },
  { value: "last_contact_date", label: "Last contacted", blurb: "When you last spoke" },
  { value: "quoted_value", label: "Deal value", blurb: "What you quoted", sensitive: true },
  { value: "budget_range", label: "Their budget", blurb: "What they said they can spend", sensitive: true },
  { value: "timeline", label: "Their timeline", blurb: "When they want to start" },
  { value: "pain_points", label: "Pain points", blurb: "The problems they described" },
  { value: "decision_makers", label: "Decision makers", blurb: "Who else signs it off" },
  { value: "tech_stack", label: "Tech stack", blurb: "What they are built on" },
  { value: "notes", label: "Internal notes", blurb: "Your team's own notes", sensitive: true },
];

export const goalLabel = (goal: ScriptGoal) => GOALS.find((g) => g.value === goal)?.label ?? "Something else";

export type AgentStatus = { tone: AgentStatusTone; label: string; hint: string };

/**
 * What an agent's card says it is doing. Deliberately distinguishes "paused" from "not
 * finished": an agent with no number can never take a call, and saying "Ready" would be a lie.
 */
export function agentStatus(agent: VoiceAgent, activeCalls = 0): AgentStatus {
  if (activeCalls > 0) {
    return {
      tone: "calling",
      label: activeCalls === 1 ? "On a call" : `On ${activeCalls} calls`,
      hint: "Live right now",
    };
  }
  if (!agent.is_active) {
    return { tone: "paused", label: "Paused", hint: "Keeps its script and history, takes no calls" };
  }
  if (!agent.platform_assistant_id) {
    return { tone: "setup", label: "Not connected", hint: "The voice platform is not configured yet" };
  }
  if (!agent.phone_number_id) {
    return { tone: "setup", label: "Needs a number", hint: "Assign a phone number so it can be reached" };
  }
  return { tone: "ready", label: "Ready", hint: "Available to take and place calls" };
}

/** An agent is only as specific as its script; this is what the roster card reports. */
export function scriptCompleteness(agent: VoiceAgent): { filled: number; total: number; missing: string[] } {
  const script = agent.script;
  const checks: { ok: boolean; label: string }[] = [
    { ok: Boolean(script?.opening?.trim()), label: "an opening" },
    { ok: (script?.talking_points?.length ?? 0) > 0, label: "talking points" },
    { ok: (script?.questions?.length ?? 0) > 0, label: "questions to ask" },
    { ok: (script?.objections?.length ?? 0) > 0, label: "objection handling" },
    { ok: Boolean(script?.closing?.trim()), label: "a closing" },
  ];
  return {
    filled: checks.filter((c) => c.ok).length,
    total: checks.length,
    missing: checks.filter((c) => !c.ok).map((c) => c.label),
  };
}
