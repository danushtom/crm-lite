import { cn } from "@dracara/ui";
import { initials } from "@/lib/format";

/**
 * Initials circle used in every people/company row. The contacts list, companies list and both
 * galleries each inlined this span with slightly different sizes and dark-mode colours.
 */
export function Avatar({
  name,
  className,
  square,
}: {
  name: string;
  className?: string;
  /** Companies use a rounded square rather than a circle, to read as an org not a person. */
  square?: boolean;
}) {
  return (
    <span
      aria-hidden
      className={cn(
        "inline-flex h-8 w-8 shrink-0 items-center justify-center bg-slate-200 text-[11px] font-semibold text-slate-700 transition-colors dark:bg-slate-700 dark:text-slate-100",
        square ? "rounded-md" : "rounded-full",
        className
      )}
    >
      {initials(name)}
    </span>
  );
}
