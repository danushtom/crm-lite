"use client";

import { OpportunityHero } from "@/components/opportunities/opportunity-hero";
import { OpportunitySubnav } from "@/components/opportunities/opportunity-subnav";
import { ChevronLeft } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

export default function OpportunityLayout({ children }: { children: React.ReactNode }) {
  const { id } = useParams<{ id: string }>();

  return (
    <div className="w-full space-y-4">
      {/* No padding on this container: the app shell's <main> already sets px-4 lg:px-6, and
          adding a second layer here left every opportunity sub-route inset further than the
          rest of the app. */}
      <div className="flex items-center gap-2">
        <Link 
          href="/opportunities" 
          className="group inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
        >
          <ChevronLeft className="h-3.5 w-3.5 transition-transform group-hover:-translate-x-0.5" />
          Back to Pipeline
        </Link>
      </div>
      <OpportunityHero id={id} />
      <div className="space-y-6">
        <OpportunitySubnav id={id} />
        {children}
      </div>
    </div>
  );
}
