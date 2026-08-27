"use client";

import type { CompanyRow, ContactRow, LeadWithOpportunities } from "@dracara/types";
import { Button } from "@dracara/ui";
import { useMutation } from "@tanstack/react-query";
import { Download, Loader2 } from "lucide-react";
import { usePathname } from "next/navigation";
import { toast } from "sonner";
import { apiListAll } from "@/lib/api";
import { downloadCsv, timestampedName, toCsv, type CsvColumn } from "@/lib/csv";
import { leadCurrency, leadScore, leadStage, leadValue } from "@/lib/leads";
import { describeError } from "@/lib/use-api-mutation";

/**
 * Exports whatever the current page lists.
 *
 * The button lives in the global top bar, so it works out what to export from the route
 * rather than being told — that keeps every list page from having to wire up its own.
 * It re-fetches rather than reading the table on screen, so an export is the whole set and
 * not just the page you happen to be looking at.
 */

type Exporter = {
  label: string;
  filename: string;
  run: () => Promise<string>;
};

function leadsExporter(): Exporter {
  const columns: CsvColumn<LeadWithOpportunities>[] = [
    { header: "Company", value: (l) => l.companies?.name ?? "" },
    { header: "Project type", value: (l) => l.project_type },
    { header: "Source", value: (l) => l.lead_source },
    { header: "Stage", value: (l) => leadStage(l) ?? "" },
    { header: "Value", value: (l) => leadValue(l) || "" },
    { header: "Currency", value: (l) => leadCurrency(l) },
    { header: "Score", value: (l) => leadScore(l) },
    { header: "Last contact", value: (l) => l.last_contact_date ?? "" },
    { header: "Next follow-up", value: (l) => l.next_followup_date ?? "" },
    { header: "Tags", value: (l) => l.tags },
  ];
  return {
    label: "leads",
    filename: timestampedName("leads"),
    run: async () => toCsv(await apiListAll<LeadWithOpportunities>("/leads"), columns),
  };
}

function contactsExporter(): Exporter {
  const columns: CsvColumn<ContactRow & { companies?: { name?: string } | null }>[] = [
    { header: "Name", value: (c) => c.full_name },
    { header: "Company", value: (c) => c.companies?.name ?? "" },
    { header: "Role", value: (c) => c.role ?? "" },
    { header: "Email", value: (c) => c.email ?? "" },
    { header: "Phone", value: (c) => c.phone ?? "" },
    { header: "Source", value: (c) => c.source ?? "" },
    { header: "LinkedIn", value: (c) => c.linkedin_url ?? "" },
  ];
  return {
    label: "contacts",
    filename: timestampedName("contacts"),
    run: async () => toCsv(await apiListAll<ContactRow>("/contacts"), columns),
  };
}

function companiesExporter(): Exporter {
  const columns: CsvColumn<CompanyRow>[] = [
    { header: "Name", value: (c) => c.name },
    { header: "Industry", value: (c) => c.industry ?? "" },
    { header: "Segment", value: (c) => c.segment ?? "" },
    { header: "Size", value: (c) => c.size ?? "" },
    { header: "Location", value: (c) => c.location ?? "" },
    { header: "Website", value: (c) => c.website ?? "" },
  ];
  return {
    label: "companies",
    filename: timestampedName("companies"),
    run: async () => toCsv(await apiListAll<CompanyRow>("/companies"), columns),
  };
}

type OpportunityExport = {
  title: string;
  stage: string;
  status: string;
  quoted_value: number | null;
  currency: string;
  deal_probability: number;
  priority_score: number;
  leads?: { companies?: { name?: string } | null } | null;
};

function opportunitiesExporter(): Exporter {
  const columns: CsvColumn<OpportunityExport>[] = [
    { header: "Title", value: (o) => o.title },
    { header: "Company", value: (o) => o.leads?.companies?.name ?? "" },
    { header: "Stage", value: (o) => o.stage },
    { header: "Status", value: (o) => o.status },
    { header: "Value", value: (o) => o.quoted_value ?? "" },
    { header: "Currency", value: (o) => o.currency },
    { header: "Probability", value: (o) => o.deal_probability },
    { header: "Score", value: (o) => o.priority_score },
  ];
  return {
    label: "opportunities",
    filename: timestampedName("opportunities"),
    run: async () => toCsv(await apiListAll<OpportunityExport>("/opportunities"), columns),
  };
}

function exporterFor(pathname: string): Exporter | null {
  if (pathname.startsWith("/leads")) return leadsExporter();
  if (pathname.startsWith("/contacts")) return contactsExporter();
  if (pathname.startsWith("/companies")) return companiesExporter();
  if (pathname.startsWith("/opportunities") || pathname.startsWith("/pipeline")) {
    return opportunitiesExporter();
  }
  return null;
}

export function ExportButton() {
  const pathname = usePathname();
  const exporter = exporterFor(pathname);

  const run = useMutation({
    mutationFn: async () => {
      if (!exporter) throw new Error("Nothing to export here");
      const csv = await exporter.run();
      downloadCsv(exporter.filename, csv);
      return exporter.filename;
    },
    onSuccess: (filename) => toast.success("Exported", { description: filename }),
    onError: (error: Error) =>
      toast.error("Could not export", { description: describeError(error) }),
  });

  return (
    <Button
      size="sm"
      className="h-9 gap-1 rounded-lg bg-[#0A1128] px-3 text-white hover:bg-[#151f3d] disabled:opacity-50"
      disabled={!exporter || run.isPending}
      title={exporter ? `Export all ${exporter.label} as CSV` : "This page has nothing to export"}
      onClick={() => run.mutate()}
    >
      {run.isPending ? (
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
      ) : (
        <Download className="h-3.5 w-3.5" />
      )}
      Export
    </Button>
  );
}
