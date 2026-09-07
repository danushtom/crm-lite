import type { CallStatus } from "@dracara/types";

/** Human labels for `call_status`. The raw enum values are not presentable. */
export const CALL_STATUS_LABEL: Record<CallStatus, string> = {
  queued: "Queued",
  ringing: "Ringing",
  in_progress: "In progress",
  completed: "Completed",
  failed: "Failed",
  no_consent_blocked: "Blocked — no consent",
};

/**
 * Badge colours per status. A blocked call is deliberately not styled as an error: it is the
 * consent guardrail working, so it reads as a warning rather than a failure.
 */
export const CALL_STATUS_TONE: Record<CallStatus, string> = {
  queued: "bg-slate-100 text-slate-700 hover:bg-slate-100 dark:bg-slate-800 dark:text-slate-200",
  ringing: "bg-sky-100 text-sky-700 hover:bg-sky-100 dark:bg-sky-900/30 dark:text-sky-300",
  in_progress: "bg-sky-100 text-sky-700 hover:bg-sky-100 dark:bg-sky-900/30 dark:text-sky-300",
  completed:
    "bg-emerald-100 text-emerald-700 hover:bg-emerald-100 dark:bg-emerald-900/30 dark:text-emerald-300",
  failed: "bg-rose-100 text-rose-700 hover:bg-rose-100 dark:bg-rose-900/30 dark:text-rose-300",
  no_consent_blocked:
    "bg-amber-100 text-amber-800 hover:bg-amber-100 dark:bg-amber-900/30 dark:text-amber-300",
};
