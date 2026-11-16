import { cn } from "@dracara/ui";
import { initials } from "@/lib/format";

/**
 * The avatar for an AI agent.
 *
 * Same language as every person in the CRM -- an initials circle (see components/shared/avatar
 * and the contact detail page) -- because an agent sits in a list beside real colleagues and
 * should not look like a different kind of object. The only addition is colour: an organization
 * runs several agents, and a per-agent tint is what makes them tellable apart at a glance.
 *
 * Illustrated characters were tried here and read as toys next to the rest of the product.
 */

export const AVATAR_KEYS = ["violet", "amber", "teal", "slate", "rose", "emerald", "sky", "indigo"] as const;
export type AvatarKey = (typeof AVATAR_KEYS)[number];

/** Soft tint behind, strong tone for the initials. Tuned to stay legible in both themes. */
const TINTS: Record<AvatarKey, string> = {
  violet: "bg-violet-100 text-violet-700 dark:bg-violet-500/20 dark:text-violet-200",
  amber: "bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-200",
  teal: "bg-teal-100 text-teal-800 dark:bg-teal-500/20 dark:text-teal-200",
  slate: "bg-slate-200 text-slate-700 dark:bg-slate-600/40 dark:text-slate-100",
  rose: "bg-rose-100 text-rose-700 dark:bg-rose-500/20 dark:text-rose-200",
  emerald: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-200",
  sky: "bg-sky-100 text-sky-800 dark:bg-sky-500/20 dark:text-sky-200",
  indigo: "bg-indigo-100 text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-200",
};

/** A stable tint for an agent that has never had one chosen, from whatever identifies it. */
export function avatarKeyFor(seed: string, chosen?: string | null): AvatarKey {
  if (chosen && (AVATAR_KEYS as readonly string[]).includes(chosen)) return chosen as AvatarKey;
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) hash = (hash * 31 + seed.charCodeAt(i)) % 9973;
  return AVATAR_KEYS[hash % AVATAR_KEYS.length];
}

export type AgentStatusTone = "ready" | "calling" | "paused" | "setup";

const RING: Record<AgentStatusTone, string> = {
  ready: "ring-emerald-500/70",
  calling: "ring-sky-500/80",
  paused: "ring-slate-400/60",
  setup: "ring-amber-500/70",
};

const DOT: Record<AgentStatusTone, string> = {
  ready: "bg-emerald-500",
  calling: "bg-sky-500",
  paused: "bg-slate-400",
  setup: "bg-amber-500",
};

const SIZES: Record<string, string> = {
  sm: "h-9 w-9 text-[11px]",
  md: "h-12 w-12 text-sm",
  lg: "h-16 w-16 text-lg",
  xl: "h-20 w-20 text-xl",
};

export function AgentAvatar({
  name,
  avatarKey,
  size = "md",
  status,
  className,
}: {
  /** Shown as initials, and used to seed the tint when no key is set. */
  name: string;
  avatarKey?: string | null;
  size?: keyof typeof SIZES;
  status?: AgentStatusTone;
  className?: string;
}) {
  const key = avatarKeyFor(name, avatarKey);

  return (
    <span className={cn("relative inline-flex shrink-0", className)}>
      <span
        role="img"
        aria-label={`${name}, AI agent`}
        className={cn(
          "inline-flex items-center justify-center rounded-full font-semibold tracking-tight",
          SIZES[size],
          TINTS[key],
          status && `ring-2 ring-offset-2 ring-offset-card ${RING[status]}`
        )}
      >
        {initials(name)}
      </span>
      {status ? (
        <span
          className={cn(
            "absolute -bottom-0.5 -right-0.5 rounded-full border-2 border-card",
            size === "sm" ? "h-2.5 w-2.5" : "h-3 w-3",
            DOT[status],
            status === "calling" && "animate-pulse"
          )}
          aria-hidden
        />
      ) : null}
    </span>
  );
}
