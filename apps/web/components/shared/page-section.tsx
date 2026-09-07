"use client";

import type { ReactNode } from "react";

/**
 * Heading for a detail-page sub-route (lead notes, opportunity proposals, and so on).
 *
 * Eight sub-route pages each hand-rolled an `<h2 className="text-2xl font-semibold">`, which
 * competed with the app chrome's own page title and used a heading scale that appears nowhere
 * in the design reference. A sub-route sits *inside* an already-titled page, so its heading is
 * a section heading, not a page heading.
 */
export function PageSection({
  title,
  description,
  action,
  children,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold tracking-tight text-foreground">{title}</h2>
          {description ? (
            <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>
          ) : null}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
