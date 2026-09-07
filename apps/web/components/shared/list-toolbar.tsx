"use client";

import { Input, cn } from "@dracara/ui";
import { LayoutGrid, List, Search, X } from "lucide-react";
import type { ReactNode } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

/**
 * Search box with a clear affordance. Split out so Contacts, Companies and Leads share one
 * implementation instead of three near-copies (Leads previously had no search at all).
 */
export function ToolbarSearch({
  value,
  onChange,
  placeholder,
  label,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  label: string;
}) {
  return (
    <div className="relative">
      <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
      <Input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-label={label}
        className="h-8 w-full rounded-md border-border/70 pl-8 pr-8 text-xs sm:w-64"
      />
      {value ? (
        <button
          type="button"
          aria-label="Clear search"
          onClick={() => onChange("")}
          className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      ) : null}
    </div>
  );
}

export type ViewOption = { value: string; label: string; icon: ReactNode };

const DEFAULT_VIEWS: ViewOption[] = [
  { value: "list", label: "List", icon: <List className="h-3.5 w-3.5" /> },
  { value: "gallery", label: "Gallery", icon: <LayoutGrid className="h-3.5 w-3.5" /> },
];

/**
 * The List/Gallery segmented control. View mode lives in `?view=` so it survives a refresh and
 * is shareable, which is how the Contacts page already did it.
 */
export function ViewSwitcher({
  current,
  options = DEFAULT_VIEWS,
}: {
  current: string;
  options?: ViewOption[];
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const select = (value: string) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("view", value);
    router.push(`${pathname}?${params.toString()}`);
  };

  return (
    <div className="inline-flex h-8 items-center rounded-md border border-border/70 bg-card p-0.5">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => select(option.value)}
          aria-pressed={current === option.value}
          className={cn(
            "inline-flex h-6 items-center gap-1 rounded px-2 text-xs transition-colors",
            current === option.value
              ? "bg-muted/80 font-semibold text-foreground"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          {option.icon}
          {option.label}
        </button>
      ))}
    </div>
  );
}

/** Toolbar row: filters/search on the left, view switcher and primary action on the right. */
export function ListToolbar({ left, right }: { left?: ReactNode; right?: ReactNode }) {
  return (
    <div className="flex flex-col gap-2.5 xl:flex-row xl:items-center xl:justify-between">
      <div className="flex flex-wrap items-center gap-2">{left}</div>
      <div className="flex items-center gap-2">{right}</div>
    </div>
  );
}
