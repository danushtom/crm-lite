/**
 * Shared style tokens.
 *
 * These exist because the same values were being retyped per page and drifting: the card shell
 * had three variants, and uppercase labels had six (`text-[10px] font-bold tracking-widest`,
 * `text-xs font-medium tracking-wide`, and so on). The Contacts pages are the design
 * reference; these constants are what those pages use.
 */

/** Container shell for a card. Matches the `Card` component default; use when styling a raw div. */
export const cardShell =
  "rounded-xl border border-border/70 bg-card shadow-[0_1px_3px_rgba(15,23,42,0.06)]";

/** Small-caps label above a value in a KPI or definition cell. */
export const fieldLabel =
  "text-[11px] font-semibold uppercase tracking-wide text-muted-foreground";

/** The smaller eyebrow above a page/hero title. */
export const eyebrowLabel =
  "text-[10px] font-semibold uppercase tracking-wide text-muted-foreground";

/** Table header row. */
export const tableHeadRow =
  "select-none border-b border-border/70 text-left text-[11px] font-semibold text-muted-foreground";

/** Table body row, including the hover state and the staggered entry animation. */
export const tableBodyRow =
  "group border-b border-border/50 transition-colors hover:bg-muted/30 animate-in fade-in slide-in-from-bottom-2 duration-500 fill-mode-both";

/** Standard cell padding, used by both `th` and `td`. */
export const tableCell = "py-2.5 pr-4";

/** Height-8 outline control used across toolbars. */
export const toolbarButton =
  "h-8 gap-1.5 rounded-md border-border/70 px-3 text-xs";

/** The primary (navy) action button. */
export const primaryButton =
  "h-8 gap-1.5 rounded-md bg-[#0A1128] px-3 text-xs font-semibold text-white hover:bg-[#1a2a53]";

/** Brand colours. Navy for primary surfaces, teal-blue for links and accents. */
export const BRAND_NAVY = "#0A1128";
export const BRAND_ACCENT = "#0B7FB3";
