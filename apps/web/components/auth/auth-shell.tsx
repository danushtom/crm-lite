import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@dracara/ui";
import Link from "next/link";
import type { ReactNode } from "react";

/** The centred card every signed-out screen (sign in, sign up, reset, invite) shares. */
export function AuthShell({
  title,
  description,
  children,
  footer,
}: {
  title: string;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#F9FAFB] p-4 dark:bg-background">
      <Card className="w-full max-w-md rounded-2xl border-[#E5E7EB] bg-white shadow-[0_1px_3px_rgba(15,23,42,0.06)] dark:border-border dark:bg-card">
        <CardHeader className="space-y-1">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Dracara Growth OS</p>
          <CardTitle className="text-2xl font-semibold tracking-tight">{title}</CardTitle>
          {description ? <CardDescription>{description}</CardDescription> : null}
        </CardHeader>
        <CardContent>
          {children}
          {footer ? <div className="mt-6 text-center text-sm text-muted-foreground">{footer}</div> : null}
        </CardContent>
      </Card>
    </div>
  );
}

export const authButtonClass =
  "w-full rounded-lg bg-[#0A1128] font-semibold text-white hover:bg-[#151f3d]";

export function AuthLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link href={href} className="font-medium text-foreground underline underline-offset-4 hover:opacity-80">
      {children}
    </Link>
  );
}

export function MissingEnvNotice() {
  return (
    <p className="text-sm text-muted-foreground">
      Configure <code className="rounded bg-muted px-1 py-0.5 text-xs">NEXT_PUBLIC_SUPABASE_URL</code> and{" "}
      <code className="rounded bg-muted px-1 py-0.5 text-xs">NEXT_PUBLIC_SUPABASE_ANON_KEY</code> in{" "}
      <code className="rounded bg-muted px-1 py-0.5 text-xs">apps/web/.env.local</code>.
    </p>
  );
}

export function Field({
  id,
  label,
  hint,
  children,
}: {
  id: string;
  label: string;
  hint?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between gap-2">
        <label htmlFor={id} className="text-sm font-medium">
          {label}
        </label>
        {hint}
      </div>
      {children}
    </div>
  );
}
