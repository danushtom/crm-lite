import { LeadWithOpportunities } from "@dracara/types";
import { formatDistanceToNow } from "date-fns";
import { Badge } from "@dracara/ui";
import { Calendar, Building, User, Target, CircleDollarSign } from "lucide-react";
import { cn } from "@dracara/ui";
import Link from "next/link";

/** Keyed by the `lead_stage` enum values the API actually returns, not display labels. */
const STAGE_COLORS: Record<string, string> = {
  prospect: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
  contacting: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300",
  discovery_scheduled: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300",
  requirements_gathering: "bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-300",
  solution_design: "bg-pink-100 text-pink-700 dark:bg-pink-900/30 dark:text-pink-300",
  proposal_sent: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
  negotiation: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300",
  won: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
  delivery_transition: "bg-teal-100 text-teal-700 dark:bg-teal-900/30 dark:text-teal-300",
  on_hold: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  followup_later: "bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300",
  lost: "bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300",
};

function formatCompactCurrency(n: number, currency: string = "USD"): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency,
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(n);
}

export type LeadGalleryRow = {
  id: string;
  projectType: string;
  companyName: string;
  contactName: string;
  /** Display label, e.g. "Proposal sent". */
  stage: string;
  /** The raw `lead_stage` enum value, used for the badge colour. */
  rawStage: string | null;
  value: number;
  currency: string;
  score: number;
  /** Raw ISO date or null -- never a pre-formatted string. */
  nextFollowup: string | null;
};

export function LeadsGallery({ leads }: { leads: LeadGalleryRow[] }) {
  if (leads.length === 0) {
    return <p className="text-sm text-muted-foreground p-4">No leads yet.</p>;
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 p-4">
      {leads.map((lead, index) => {
        const stage = lead.stage || "No pursuit";
        const stageKey = (lead.rawStage ?? "").toLowerCase();
        const score = lead.score;
        const value = lead.value;
        const currency = lead.currency;
        
        return (
          <Link 
            href={`/leads/${lead.id}`} 
            key={lead.id}
            className="flex flex-col gap-3 p-4 rounded-xl border border-border/70 bg-card hover:border-primary/50 hover:shadow-md transition-all animate-in fade-in slide-in-from-bottom-2 duration-500 fill-mode-both"
            style={{ animationDelay: `${index * 50}ms` }}
          >
            <div className="flex justify-between items-start">
              <div>
                <h3 className="font-semibold text-[#111827] dark:text-slate-100 line-clamp-1">
                  {lead.projectType}
                </h3>
                <p className="text-xs text-muted-foreground mt-0.5 capitalize flex items-center gap-1">
                  <Building className="h-3 w-3" /> {lead.companyName}
                </p>
              </div>
              <Badge className={cn("capitalize px-2 py-0.5 text-[10px] font-semibold whitespace-nowrap", STAGE_COLORS[stageKey] || "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300")}>
                {stage}
              </Badge>
            </div>
            
            <div className="grid grid-cols-2 gap-2 mt-2">
              <div className="flex flex-col gap-1">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Score</span>
                <div className="flex items-center gap-1.5">
                  <Target className={cn("h-3.5 w-3.5", score > 80 ? "text-emerald-500" : score > 50 ? "text-amber-500" : "text-muted-foreground")} />
                  <span className="text-sm font-semibold">{score}</span>
                </div>
              </div>
              <div className="flex flex-col gap-1">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Value</span>
                <div className="flex items-center gap-1.5">
                  <CircleDollarSign className="h-3.5 w-3.5 text-blue-500" />
                  <span className="text-sm font-semibold">{formatCompactCurrency(value, currency)}</span>
                </div>
              </div>
            </div>

            <div className="mt-auto pt-3 border-t border-border/50 flex items-center justify-between">
              <p className="text-xs text-muted-foreground flex items-center gap-1">
                <User className="h-3.5 w-3.5" /> {lead.contactName}
              </p>
              <div className="flex items-center gap-1 text-[11px] text-muted-foreground">
                <Calendar className="h-3 w-3" />
                {lead.nextFollowup ? formatDistanceToNow(new Date(lead.nextFollowup), { addSuffix: true }) : "No follow-up"}
              </div>
            </div>
          </Link>
        );
      })}
    </div>
  );
}
