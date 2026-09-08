import type { ContactRow } from "@dracara/types";

/**
 * Turning raw UTM parameters into the channel a human recognises.
 *
 * Mirrors `apps/api/app/domain/attribution.py`, which does the same mapping server-side when a
 * captured contact's coarse `source` is derived. The two are kept deliberately in step: if the
 * card says "Meta Ads" and the stored source says something else, the reports disagree with
 * the pipeline.
 *
 * Ad platforms are not consistent about `utm_source`. The same Meta click arrives as
 * `facebook`, `fb`, `ig` or `instagram` depending on placement and template, so grouping on
 * the raw value scatters one channel across four cards. Nothing here rewrites what was stored:
 * `contacts.utm_*` keeps exactly what the click carried, because that is the only version that
 * reconciles against the ad platform's own reporting.
 */

const PLATFORM_ALIASES: Record<string, string> = {
  facebook: "Meta",
  fb: "Meta",
  meta: "Meta",
  instagram: "Meta",
  ig: "Meta",
  linkedin: "LinkedIn",
  li: "LinkedIn",
  google: "Google",
  adwords: "Google",
  googleads: "Google",
  bing: "Microsoft",
  microsoft: "Microsoft",
  twitter: "X",
  x: "X",
  reddit: "Reddit",
  youtube: "YouTube",
  tiktok: "TikTok",
};

/** utm_medium values that mean somebody paid for the click. */
const PAID_MEDIUMS = new Set([
  "cpc",
  "ppc",
  "paid",
  "paidsocial",
  "paid_social",
  "paid-social",
  "display",
  "cpm",
  "ads",
]);

const REFERRAL_MEDIUMS = new Set(["referral", "partner", "affiliate"]);

function clean(value: string | null | undefined): string {
  return (value ?? "").trim().toLowerCase();
}

function titleCase(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

/** "facebook" -> "Meta". Unknown sources are title-cased rather than dropped. */
export function platformLabel(utmSource: string | null | undefined): string | null {
  const cleaned = clean(utmSource);
  if (!cleaned) return null;
  return PLATFORM_ALIASES[cleaned] ?? titleCase(cleaned);
}

export function isPaid(utmMedium: string | null | undefined): boolean {
  return PAID_MEDIUMS.has(clean(utmMedium));
}

/** The channel shown on a card: "Meta Ads", "LinkedIn", "Referral", "Direct". */
export function channelLabel(
  utmSource: string | null | undefined,
  utmMedium: string | null | undefined,
  source?: string | null
): string {
  const platform = platformLabel(utmSource);
  if (platform) return isPaid(utmMedium) ? `${platform} Ads` : platform;

  const medium = clean(utmMedium);
  if (REFERRAL_MEDIUMS.has(medium)) return "Referral";
  if (medium === "email") return "Email";

  // Hand-entered contacts have no UTM at all, only the coarse enum.
  if (source) return titleCase(source);
  return "Direct";
}

/** The channel for a contact row. */
export function contactChannel(contact: ContactRow): string {
  return channelLabel(contact.utm_source, contact.utm_medium, contact.source);
}

/** Whether a contact carries enough attribution to be worth showing a detail panel for. */
export function hasAttribution(contact: ContactRow): boolean {
  return Boolean(
    contact.utm_source ||
      contact.utm_medium ||
      contact.utm_campaign ||
      contact.utm_content ||
      contact.landing_page_url ||
      contact.referrer_url
  );
}

/**
 * Brand-ish tints per channel, so the same platform reads the same colour on every page.
 * Deliberately muted: these sit behind data, not next to a logo.
 */
export const CHANNEL_TONE: Record<string, string> = {
  Meta: "bg-[#0866FF]",
  "Meta Ads": "bg-[#0866FF]",
  LinkedIn: "bg-[#0A66C2]",
  "LinkedIn Ads": "bg-[#0A66C2]",
  Google: "bg-[#EA4335]",
  "Google Ads": "bg-[#EA4335]",
  Referral: "bg-emerald-500",
  Email: "bg-amber-500",
  Direct: "bg-slate-400",
};

export function channelTone(channel: string): string {
  return CHANNEL_TONE[channel] ?? "bg-[#2FA8E8]";
}
