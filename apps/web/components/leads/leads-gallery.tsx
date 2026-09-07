import { LeadWithOpportunities } from "@dracara/types";
import { formatDistanceToNow } from "date-fns";
import { Badge } from "@dracara/ui";
import { Calendar, Building, User, Target, CircleDollarSign } from "lucide-react";
import { cn } from "@dracara/ui";
import Link from "next/link";

const STAGE_COLORS: Record<string, string> = {
  new: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
  contacted: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300",
  discovery: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300",
  demo: "bg-pink-100 text-pink-700 dark:bg-pink-900/30 dark:text-pink-300",
  proposal: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
  negotiation: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300",
  won: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
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
  stage: string;
  value: number;
  currency: string;
  score: number;
  nextFollowup: string | null;
};

export function LeadsGallery({ leads }: { leads: LeadGalleryRow[] }) {
  if (leads.length === 0) {
    return <p className="text-sm text-muted-foreground p-4">No leads yet.</p>;
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 p-4">
      {leads.map((lead, index) => {
        const stage = lead.stage || "new";
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
              <Badge className={cn("capitalize px-2 py-0.5 text-[10px] font-semibold whitespace-nowrap", STAGE_COLORS[stage.toLowerCase()] || "bg-gray-100 text-gray-700")}>
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
