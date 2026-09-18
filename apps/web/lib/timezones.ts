/** IANA timezone helpers for the timezone pickers and signup. */

const FALLBACK = [
  "UTC",
  "Asia/Kolkata",
  "Asia/Dubai",
  "Asia/Singapore",
  "Asia/Tokyo",
  "Europe/London",
  "Europe/Berlin",
  "America/New_York",
  "America/Chicago",
  "America/Los_Angeles",
  "Australia/Sydney",
];

/** The browser's own zone, e.g. "Europe/Paris"; undefined if the runtime cannot say. */
export function browserTimezone(): string | undefined {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || undefined;
  } catch {
    return undefined;
  }
}

/**
 * Every zone the runtime knows, always including `current`: a saved zone missing from the list
 * would otherwise render as the first option and be silently overwritten on the next save.
 */
export function timezoneOptions(current?: string | null): string[] {
  let zones: string[];
  try {
    zones = (Intl as unknown as { supportedValuesOf(key: string): string[] }).supportedValuesOf("timeZone");
  } catch {
    zones = FALLBACK;
  }
  const all = new Set(zones.length ? zones : FALLBACK);
  all.add("UTC");
  if (current) all.add(current);
  return Array.from(all).sort();
}

export const timezoneLabel = (zone: string) => zone.replaceAll("_", " ");
