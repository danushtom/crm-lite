import { LeadSubnav } from "@/components/leads/lead-subnav";
import { LeadHero } from "@/components/leads/lead-hero";

import { ChevronLeft } from "lucide-react";
import Link from "next/link";

export default async function LeadLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <div className="mx-auto max-w-6xl space-y-4 pb-12 pt-2">
      <div className="flex items-center gap-2">
        <Link 
          href="/leads" 
          className="group inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
        >
          <ChevronLeft className="h-3.5 w-3.5 transition-transform group-hover:-translate-x-0.5" />
          Back to Leads
        </Link>
      </div>
      <LeadHero id={id} />
      <LeadSubnav id={id} />
      {children}
    </div>
  );
}
