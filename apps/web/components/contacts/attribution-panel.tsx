"use client";

import { Badge, cn, fieldLabel } from "@dracara/ui";
import { ExternalLink } from "lucide-react";
import type { ContactRow } from "@dracara/types";
import { channelTone, contactChannel, hasAttribution } from "@/lib/attribution";
import { formatDate } from "@/lib/format";

/**
 * Where this contact came from: the channel, the campaign, the specific creative, and the page
 * whose form they submitted.
 *
 * This is the detail the Contacts cards aggregate. Seeing it per-contact is what makes the
 * aggregate trustworthy -- "Meta Ads brought 6 people" is only useful if you can open one and
 * see which ad.
 */
export function AttributionPanel({ contact }: { contact: ContactRow }) {
  if (!hasAttribution(contact)) {
    return (
      <p className="text-sm text-muted-foreground">
        No attribution recorded. This contact was entered by hand rather than captured from a
        form, so there is no campaign behind them.
      </p>
    );
  }

  const channel = contactChannel(contact);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <span
          className={cn("inline-block h-2.5 w-2.5 rounded-sm", channelTone(channel))}
          aria-hidden
        />
        <span className="text-sm font-semibold text-foreground">{channel}</span>
        {contact.captured_at ? (
          <Badge variant="outline" className="text-[10px]">
            Captured {formatDate(contact.captured_at)}
          </Badge>
        ) : null}
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-2.5">
        <Detail label="Campaign" value={contact.utm_campaign} />
        <Detail label="Ad / creative" value={contact.utm_content} />
        <Detail label="Source" value={contact.utm_source} />
        <Detail label="Medium" value={contact.utm_medium} />
        {contact.utm_term ? <Detail label="Search term" value={contact.utm_term} /> : null}
      </dl>

      {contact.landing_page_url ? (
        <LinkRow label="Form they filled" href={contact.landing_page_url} />
      ) : null}
      {contact.referrer_url ? <LinkRow label="Referrer" href={contact.referrer_url} /> : null}
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <dt className={fieldLabel}>{label}</dt>
      {/* The raw stored value, not a prettified one: this is what reconciles against the ad
          platform's own reporting, so it has to match character for character. */}
      <dd className="mt-0.5 truncate font-mono text-xs text-foreground" title={value ?? undefined}>
        {value || "—"}
      </dd>
    </div>
  );
}

function LinkRow({ label, href }: { label: string; href: string }) {
  return (
    <div>
      <p className={fieldLabel}>{label}</p>
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="mt-0.5 inline-flex max-w-full items-center gap-1 truncate text-xs text-[#0B7FB3] hover:underline"
      >
        <span className="truncate">{href}</span>
        <ExternalLink className="h-3 w-3 shrink-0" />
      </a>
    </div>
  );
}
