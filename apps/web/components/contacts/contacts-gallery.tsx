import { Badge } from "@dracara/ui";
import { Mail, Phone, Building2, UserCircle } from "lucide-react";
import { cn } from "@dracara/ui";
import type { ContactRow, LeadWithOpportunities } from "@dracara/types";
import { leadStage } from "@/lib/leads";

type ContactWithCompany = ContactRow & { companies?: { name?: string | null } | null };

type CompanyStage = "Won" | "Leads" | "Lost" | "Discovery";

const STAGE_VARIANTS: Record<CompanyStage, string> = {
  Won: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
  Leads: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  Lost: "bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300",
  Discovery: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
};

function leadStageToCompanyStage(stage?: string | null): CompanyStage {
  if (!stage) return "Leads";
  if (stage === "won" || stage === "delivery_transition") return "Won";
  if (stage === "lost") return "Lost";
  if (stage === "discovery_scheduled" || stage === "requirements_gathering") return "Discovery";
  return "Leads";
}

function initials(name: string): string {
  const parts = (name || "").trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 1).toUpperCase();
  return `${parts[0].slice(0, 1)}${parts[1].slice(0, 1)}`.toUpperCase();
}

function contactPipelineStage(contact: ContactRow, leads: LeadWithOpportunities[]): CompanyStage {
  for (const lead of leads) {
    if (lead.primary_contact_id === contact.id) {
      return leadStageToCompanyStage(leadStage(lead) ?? undefined);
    }
  }
  const leadsByCompany = new Map<string, LeadWithOpportunities[]>();
  for (const lead of leads) {
    const arr = leadsByCompany.get(lead.company_id) ?? [];
    arr.push(lead);
    leadsByCompany.set(lead.company_id, arr);
  }
  const companyLeads = leadsByCompany.get(contact.company_id) ?? [];
  const first = companyLeads[0];
  return leadStageToCompanyStage(first ? leadStage(first) ?? undefined : undefined);
}

export function ContactsGallery({ 
  contacts, 
  leads 
}: { 
  contacts: ContactWithCompany[]; 
  leads: LeadWithOpportunities[] 
}) {
  if (contacts.length === 0) {
    return <p className="text-sm text-muted-foreground p-4">No contacts yet.</p>;
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 p-4">
      {contacts.map((contact, index) => {
        const stage = contactPipelineStage(contact, leads);
        
        return (
          <div 
            key={contact.id}
            className="flex flex-col p-5 rounded-xl border border-border/70 bg-card hover:border-primary/50 hover:shadow-md transition-all animate-in fade-in slide-in-from-bottom-2 duration-500 fill-mode-both"
            style={{ animationDelay: `${index * 50}ms` }}
          >
            <div className="flex justify-between items-start mb-4">
              <div className="flex gap-3 items-center">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-primary/20 to-primary/10 border border-primary/20 text-sm font-semibold text-primary">
                  {initials(contact.full_name)}
                </div>
                <div>
                  <h3 className="font-semibold text-[#111827] dark:text-slate-100 line-clamp-1">
                    {contact.full_name}
                  </h3>
                  <p className="text-xs text-muted-foreground line-clamp-1">
                    {contact.role || "No role"}
                  </p>
                </div>
              </div>
              <Badge className={cn("px-2 py-0.5 text-[10px] font-semibold", STAGE_VARIANTS[stage])}>
                {stage}
              </Badge>
            </div>
            
            <div className="flex flex-col gap-2.5 mb-4">
              <div className="flex items-center gap-2 text-sm text-foreground">
                <Building2 className="h-4 w-4 text-muted-foreground shrink-0" />
                <span className="line-clamp-1">{contact.companies?.name || "No company"}</span>
              </div>
              <div className="flex items-center gap-2 text-sm text-foreground">
                <Mail className="h-4 w-4 text-muted-foreground shrink-0" />
                <span className="line-clamp-1 truncate">{contact.email || "No email"}</span>
              </div>
              <div className="flex items-center gap-2 text-sm text-foreground">
                <Phone className="h-4 w-4 text-muted-foreground shrink-0" />
                <span className="line-clamp-1">{contact.phone || "No phone"}</span>
              </div>
            </div>

            <div className="mt-auto pt-3 border-t border-border/50 flex items-center justify-between">
              <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                <span className="font-semibold px-2 py-0.5 rounded-md bg-muted text-foreground capitalize">
                  {contact.source ? contact.source.replace(/_/g, " ") : "Unknown Source"}
                </span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
