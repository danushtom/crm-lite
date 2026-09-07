import { Badge } from "@dracara/ui";
import { Users, Briefcase, UserCircle, Building2 } from "lucide-react";
import { cn } from "@dracara/ui";
import Link from "next/link";

type CompanyStage = "Won" | "Leads" | "Lost" | "Discovery";

type CompanyGalleryRow = {
  id: string;
  name: string;
  stage: CompanyStage;
  value: number;
  contactName: string;
  contactRole: string;
  contactsCount: number;
  industry: string | null;
};

const STAGE_VARIANTS: Record<CompanyStage, string> = {
  Won: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
  Leads: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  Lost: "bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300",
  Discovery: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
};

function formatCompactCurrency(n: number): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "USD",
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(n);
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 1).toUpperCase();
  return `${parts[0].slice(0, 1)}${parts[1].slice(0, 1)}`.toUpperCase();
}

export function CompaniesGallery({ companies }: { companies: CompanyGalleryRow[] }) {
  if (companies.length === 0) {
    return <p className="text-sm text-muted-foreground p-4">No companies yet.</p>;
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 p-4">
      {companies.map((company, index) => (
        <Link 
          href={`/companies/${company.id}`} 
          key={company.id}
          className="flex flex-col p-5 rounded-xl border border-border/70 bg-card hover:border-primary/50 hover:shadow-md transition-all animate-in fade-in slide-in-from-bottom-2 duration-500 fill-mode-both"
          style={{ animationDelay: `${index * 50}ms` }}
        >
          <div className="flex justify-between items-start mb-4">
            <div className="flex gap-3 items-center">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-border/50 bg-muted text-sm font-semibold text-foreground">
                {initials(company.name)}
              </div>
              <div>
                <h3 className="font-semibold text-[#111827] dark:text-slate-100 line-clamp-1">
                  {company.name}
                </h3>
                <p className="text-xs text-muted-foreground flex items-center gap-1">
                  <Briefcase className="h-3 w-3" /> {company.industry || "Unspecified"}
                </p>
              </div>
            </div>
            <Badge className={cn("px-2 py-0.5 text-[10px] font-semibold", STAGE_VARIANTS[company.stage])}>
              {company.stage}
            </Badge>
          </div>
          
          <div className="grid grid-cols-2 gap-2 mb-4 bg-muted/30 p-3 rounded-lg border border-border/30">
            <div className="flex flex-col">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Pipeline Value</span>
              <span className="text-sm font-semibold text-foreground">{formatCompactCurrency(company.value)}</span>
            </div>
            <div className="flex flex-col">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Team Size</span>
              <span className="text-sm font-semibold text-foreground flex items-center gap-1.5">
                <Users className="h-3.5 w-3.5 text-muted-foreground" />
                {company.contactsCount} Contact{company.contactsCount !== 1 ? 's' : ''}
              </span>
            </div>
          </div>

          <div className="mt-auto pt-3 border-t border-border/50 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/10 text-primary">
                <UserCircle className="h-4 w-4" />
              </div>
              <div className="flex flex-col">
                <span className="text-xs font-medium text-foreground leading-none">{company.contactName}</span>
                <span className="text-[10px] text-muted-foreground mt-0.5">{company.contactRole}</span>
              </div>
            </div>
          </div>
        </Link>
      ))}
    </div>
  );
}
