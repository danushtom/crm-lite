"use client";

import {
  Button,
  Input,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
  cn,
} from "@dracara/ui";
import { Loader2 } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useState, type ReactNode } from "react";

/**
 * Shared chrome for the create/edit side panels.
 *
 * The first two drawers copied the same Sheet scaffolding, label styling, footer and pending
 * state between them; a third would have made that a pattern by accident. Everything specific
 * to a resource lives in the form passed as children.
 */

export const selectClass =
  "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50";

export const labelClass = "text-xs font-bold uppercase tracking-widest text-muted-foreground";

export function Field({
  label,
  htmlFor,
  required,
  hint,
  error,
  children,
}: {
  label: string;
  htmlFor?: string;
  required?: boolean;
  hint?: string;
  error?: string | null;
  children: ReactNode;
}) {
  return (
    <div className="space-y-2">
      <label htmlFor={htmlFor} className={labelClass}>
        {label}
        {required ? <span className="ml-1 text-destructive">*</span> : null}
      </label>
      {children}
      {error ? (
        <p className="text-xs text-destructive">{error}</p>
      ) : hint ? (
        <p className="text-xs text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  );
}

export function TextField({
  label,
  id,
  value,
  onChange,
  required,
  hint,
  error,
  ...rest
}: {
  label: string;
  id: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
  hint?: string;
  error?: string | null;
} & Omit<React.ComponentProps<typeof Input>, "value" | "onChange" | "id">) {
  return (
    <Field label={label} htmlFor={id} required={required} hint={hint} error={error}>
      <Input
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={Boolean(error)}
        {...rest}
      />
    </Field>
  );
}

export function SelectField<T extends string>({
  label,
  id,
  value,
  onChange,
  options,
  placeholder,
  required,
  disabled,
  hint,
}: {
  label: string;
  id: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: T; label: string }[];
  placeholder?: string;
  required?: boolean;
  disabled?: boolean;
  hint?: string;
}) {
  return (
    <Field label={label} htmlFor={id} required={required} hint={hint}>
      <select
        id={id}
        className={selectClass}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        disabled={disabled}
      >
        {placeholder !== undefined ? <option value="">{placeholder}</option> : null}
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </Field>
  );
}

export function EntityDrawer({
  trigger,
  title,
  description,
  icon: Icon,
  submitLabel,
  pendingLabel,
  onSubmit,
  canSubmit,
  isPending,
  onOpenChange,
  open,
  destructiveAction,
  children,
}: {
  trigger: ReactNode;
  title: string;
  description?: string;
  icon: LucideIcon;
  submitLabel: string;
  pendingLabel?: string;
  onSubmit: () => void;
  canSubmit: boolean;
  isPending: boolean;
  /** Controlled mode; omit to let the drawer manage its own open state. */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** Rendered on the left of the footer — a delete action, typically. */
  destructiveAction?: ReactNode;
  children: ReactNode;
}) {
  const [internalOpen, setInternalOpen] = useState(false);
  const isControlled = open !== undefined;
  const isOpen = isControlled ? open : internalOpen;

  const setOpen = (next: boolean) => {
    if (!isControlled) setInternalOpen(next);
    onOpenChange?.(next);
  };

  return (
    <Sheet open={isOpen} onOpenChange={setOpen}>
      <SheetTrigger asChild>{trigger}</SheetTrigger>
      <SheetContent
        side="right"
        className="flex w-[400px] flex-col overflow-y-auto border-l border-border/60 sm:w-[540px]"
      >
        <SheetHeader className="border-b border-border/50 pb-4">
          <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-indigo-50 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-400">
            <Icon className="h-5 w-5" />
          </div>
          <SheetTitle className="text-xl">{title}</SheetTitle>
          {description ? <SheetDescription>{description}</SheetDescription> : null}
        </SheetHeader>

        <form
          className="flex flex-1 flex-col"
          onSubmit={(e) => {
            e.preventDefault();
            if (canSubmit && !isPending) onSubmit();
          }}
        >
          <div className="flex-1 space-y-4 py-6">{children}</div>

          <SheetFooter
            className={cn(
              "border-t border-border/50 pt-6",
              destructiveAction && "sm:justify-between"
            )}
          >
            {destructiveAction ?? null}
            <div className="flex gap-2">
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button
                type="submit"
                className="bg-[#0A1128] text-white hover:bg-[#1a2a53]"
                disabled={!canSubmit || isPending}
              >
                {isPending ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    {pendingLabel ?? "Saving…"}
                  </>
                ) : (
                  submitLabel
                )}
              </Button>
            </div>
          </SheetFooter>
        </form>
      </SheetContent>
    </Sheet>
  );
}
