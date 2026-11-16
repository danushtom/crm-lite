import { cn } from "@dracara/ui";

/**
 * The portrait for an AI agent.
 *
 * Drawn rather than uploaded: an organization hires several of these, gives them names its
 * customers hear, and needs to tell them apart down a list. Asking someone to find a photograph
 * for a piece of software is a strange thing to do, and a silhouette-with-a-headset icon reads
 * as clip art rather than as a colleague -- so these are proper characters, with faces.
 *
 * Eight presets, each a different person: skin tone, hair, and the colour behind them. The
 * headset is the one thing they share, because it is what says "this one answers the phone".
 */

export const AVATAR_KEYS = ["violet", "amber", "teal", "slate", "rose", "emerald", "sky", "indigo"] as const;
export type AvatarKey = (typeof AVATAR_KEYS)[number];

type Look = {
  /** Soft wash behind the character. */
  bg: string;
  skin: string;
  /** Shadow under the chin and on the ears; a slightly deeper skin tone. */
  shade: string;
  hair: string;
  /** Collar and shoulders. */
  clothes: string;
  style: "crop" | "long" | "bun" | "beard" | "bob" | "curls" | "side" | "ponytail";
};

const LOOKS: Record<AvatarKey, Look> = {
  violet: { bg: "#EDE9FE", skin: "#F2C9A0", shade: "#E0AE80", hair: "#3B2A1F", clothes: "#7C3AED", style: "crop" },
  amber: { bg: "#FEF3C7", skin: "#8D5524", shade: "#73421A", hair: "#1C1210", clothes: "#D97706", style: "long" },
  teal: { bg: "#CCFBF1", skin: "#FBD9B8", shade: "#EEBF93", hair: "#6B4226", clothes: "#0D9488", style: "bun" },
  slate: { bg: "#E2E8F0", skin: "#C68642", shade: "#A96C32", hair: "#2B2B2B", clothes: "#475569", style: "beard" },
  rose: { bg: "#FFE4E6", skin: "#F7D7C4", shade: "#E7BBA2", hair: "#A8443B", clothes: "#E11D48", style: "bob" },
  emerald: { bg: "#D1FAE5", skin: "#7A4A21", shade: "#623917", hair: "#17120F", clothes: "#059669", style: "curls" },
  sky: { bg: "#E0F2FE", skin: "#EFC8A4", shade: "#DCAC82", hair: "#C2873F", clothes: "#0284C7", style: "side" },
  indigo: { bg: "#E0E7FF", skin: "#D9A273", shade: "#C0875A", hair: "#241A14", clothes: "#4F46E5", style: "ponytail" },
};

/** A stable preset for an agent that has never had one chosen, from whatever identifies it. */
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

const SIZES = { sm: "h-9 w-9", md: "h-12 w-12", lg: "h-16 w-16", xl: "h-20 w-20" } as const;

const INK = "#2A2320";

/** Hair behind the head: drawn first, so the face sits on top of it. */
function HairBack({ look }: { look: Look }) {
  const { hair, style } = look;
  switch (style) {
    case "long":
      return <path d="M11 24c0-9 5.8-14 13-14s13 5 13 14v10c0 2-1.6 3-3.4 2.4V22H14.4v14.4C12.6 37 11 36 11 34z" fill={hair} />;
    case "bob":
      return <path d="M11.4 24c0-8.6 5.6-13.4 12.6-13.4S36.6 15.4 36.6 24v6.6c0 1.8-1.4 2.8-3.1 2.2V22H14.5v10.8c-1.7.6-3.1-.4-3.1-2.2z" fill={hair} />;
    case "curls":
      return (
        <g fill={hair}>
          <circle cx="24" cy="15" r="11.4" />
          <circle cx="14.4" cy="19.6" r="5.4" />
          <circle cx="33.6" cy="19.6" r="5.4" />
          <circle cx="18" cy="9.6" r="5" />
          <circle cx="30" cy="9.6" r="5" />
        </g>
      );
    case "bun":
      return (
        <g fill={hair}>
          <circle cx="24" cy="7.6" r="4.4" />
          <ellipse cx="24" cy="21" rx="12.2" ry="12.4" />
        </g>
      );
    case "ponytail":
      return (
        <g fill={hair}>
          <ellipse cx="24" cy="21" rx="12.2" ry="12.4" />
          <path d="M34.4 17.6c3.6.6 5.6 3.4 5.6 7.4 0 3.4-1.4 6-3.6 7.4-1.2.8-2.6-.8-1.8-2 1.2-1.8 1.8-3.4 1.8-5.4 0-2-.8-3.6-2.4-4.8z" />
        </g>
      );
    case "beard":
      // A short crop plus a beard that frames the jaw; the beard is drawn in HairFront.
      return <ellipse cx="24" cy="21.4" rx="11.8" ry="12" fill={hair} />;
    case "side":
    case "crop":
    default:
      return <ellipse cx="24" cy="21" rx="12" ry="12.4" fill={hair} />;
  }
}

/** The fringe, and anything else that sits over the face. */
function HairFront({ look }: { look: Look }) {
  const { hair, skin, shade, style } = look;
  const fringe = (() => {
    switch (style) {
      case "side":
        return <path d="M13.2 17.6c1.6-5.4 6-8 10.8-8 4 0 7.6 1.8 9.6 5.2-4 .2-7-.8-9.2-3-1.6 3.4-5.4 5.4-11.2 5.8z" fill={hair} />;
      case "beard":
        return (
          <>
            {/* Beard along the jaw, under the mouth. */}
            <path d="M13.6 21.6c0 7.4 4.6 12.4 10.4 12.4s10.4-5 10.4-12.4c0 4.4-3.2 6.8-10.4 6.8s-10.4-2.4-10.4-6.8z" fill={hair} />
            <path d="M14.4 16.8c1.8-4.6 5.4-7 9.6-7s7.8 2.4 9.6 7c-2.6-2.2-5.8-3.2-9.6-3.2s-7 1-9.6 3.2z" fill={hair} />
          </>
        );
      case "curls":
        return null;
      case "ponytail":
      case "bun":
        return <path d="M14 17.4c2-4.6 5.6-7 10-7s8 2.4 10 7c-2.8-2-6.2-3-10-3s-7.2 1-10 3z" fill={hair} />;
      default:
        return <path d="M13.8 17.8c1.4-5 5.2-7.8 10.2-7.8s8.8 2.8 10.2 7.8c-2.8-2.6-6.2-3.8-10.2-3.8s-7.4 1.2-10.2 3.8z" fill={hair} />;
    }
  })();

  return (
    <>
      {/* Ears, then the face, then the fringe on top of it. */}
      <circle cx="12.8" cy="23" r="2.4" fill={shade} />
      <circle cx="35.2" cy="23" r="2.4" fill={shade} />
      <path d="M13.6 21.8c0-6.4 4.6-10.6 10.4-10.6s10.4 4.2 10.4 10.6c0 7.4-4.6 12.6-10.4 12.6s-10.4-5.2-10.4-12.6z" fill={skin} />
      {fringe}
    </>
  );
}

export function AgentAvatar({
  name,
  avatarKey,
  size = "md",
  status,
  className,
}: {
  /** Used only to seed the look when no key is set, and for the accessible label. */
  name: string;
  avatarKey?: string | null;
  size?: keyof typeof SIZES;
  status?: AgentStatusTone;
  className?: string;
}) {
  const key = avatarKeyFor(name, avatarKey);
  const look = LOOKS[key];

  return (
    <span className={cn("relative inline-flex shrink-0", className)}>
      <svg
        viewBox="0 0 48 48"
        role="img"
        aria-label={`${name}, AI agent`}
        className={cn(
          "overflow-hidden rounded-full",
          SIZES[size],
          status && `ring-2 ring-offset-2 ring-offset-card ${RING[status]}`
        )}
      >
        <rect width="48" height="48" fill={look.bg} />

        {/* Shoulders and collar, so it reads as a portrait rather than a floating head. */}
        <path d="M6.5 48c0-8.4 7.8-13.2 17.5-13.2S41.5 39.6 41.5 48z" fill={look.clothes} />
        <path d="M20.6 34.9h6.8l-3.4 4.6z" fill="#FFFFFF" opacity="0.9" />
        {/* Neck, behind the chin. */}
        <path d="M20.8 29.6h6.4v6.2h-6.4z" fill={look.shade} />

        <HairBack look={look} />
        <HairFront look={look} />

        {/* Face. Eyes sit a little above centre, which reads as friendly rather than stern. */}
        <ellipse cx="20.2" cy="22.4" rx="1.35" ry="1.7" fill={INK} />
        <ellipse cx="27.8" cy="22.4" rx="1.35" ry="1.7" fill={INK} />
        <circle cx="20.65" cy="21.85" r="0.45" fill="#FFFFFF" />
        <circle cx="28.25" cy="21.85" r="0.45" fill="#FFFFFF" />
        <ellipse cx="16.4" cy="25.4" rx="1.9" ry="1.2" fill="#F87171" opacity="0.3" />
        <ellipse cx="31.6" cy="25.4" rx="1.9" ry="1.2" fill="#F87171" opacity="0.3" />
        <path
          d="M21 26.8c.9 1.25 2.1 1.9 3 1.9s2.1-.65 3-1.9"
          fill="none"
          stroke={INK}
          strokeWidth="1.3"
          strokeLinecap="round"
        />

        {/* Headset: band over the hair, cups at the ears, boom mic to the mouth. */}
        <path
          d="M11.6 23.2a12.4 12.4 0 0 1 24.8 0"
          fill="none"
          stroke={INK}
          strokeWidth="2.1"
          strokeLinecap="round"
        />
        <rect x="9.1" y="20.6" width="5" height="7.6" rx="2.5" fill={INK} />
        <rect x="33.9" y="20.6" width="5" height="7.6" rx="2.5" fill={INK} />
        <path
          d="M36.4 28.4v1.2c0 2.6-2.3 4.5-5 4.5"
          fill="none"
          stroke={INK}
          strokeWidth="1.9"
          strokeLinecap="round"
        />
        <circle cx="30.6" cy="34.1" r="1.9" fill={INK} />
      </svg>
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
