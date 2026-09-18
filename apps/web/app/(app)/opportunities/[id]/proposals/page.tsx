"use client";

import { Badge, Button, Card, CardContent, CardHeader, CardTitle } from "@dracara/ui";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { ProposalDrawer } from "@/components/opportunities/proposal-drawer";
import { DraftWithAiButton } from "@/components/opportunities/draft-with-ai-button";
import { FileText, Plus, ExternalLink, Download } from "lucide-react";
import { format, parseISO } from "date-fns";

type Proposal = {
  id: string;
  version: number;
  title: string;
  status: string;
  quoted_price: number | null;
  created_at: string;
  file_url?: string | null;
  figma_url?: string | null;
  github_url?: string | null;
  loom_url?: string | null;
  change_notes?: string | null;
};

export default function ProposalsPage() {
  const { id } = useParams<{ id: string }>();

  const { data: opp, isLoading } = useQuery({
    queryKey: ["opportunity", id],
    queryFn: () => apiFetch<{ proposals?: Proposal[]; currency: string }>(`/opportunities/${id}`),
  });

  if (isLoading || !opp) return <p className="text-sm text-muted-foreground animate-pulse">Loading proposals…</p>;

  const proposals = opp.proposals || [];

  const formatCurrency = (val: number | null) => {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: opp.currency || "USD",
      maximumFractionDigits: 0,
    }).format(val || 0);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">Proposals</h2>
          <p className="mt-1 text-sm text-muted-foreground">Version history and commercial documents sent to the client.</p>
        </div>
        <div className="flex items-center gap-2">
          <DraftWithAiButton opportunityId={id} />
          <ProposalDrawer opportunityId={id} />
        </div>
      </div>

      <div className="grid gap-4">
        {proposals.length > 0 ? (
          proposals.map((p) => (
            <Card key={p.id} className="overflow-hidden border border-border/70 shadow-sm transition-all hover:shadow-md">
              <CardContent className="p-0">
                <div className="flex flex-col sm:flex-row">
                  <div className="flex flex-1 items-center gap-4 p-5">
                    <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-[#0B7FB3]/10 text-[#0B7FB3] dark:bg-[#0B7FB3]/25 dark:text-[#4FB8E3]">
                      <FileText className="h-6 w-6" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <h3 className="font-semibold text-foreground truncate">v{p.version} · {p.title}</h3>
                        <Badge variant="outline" className="capitalize text-[10px] shrink-0">
                          {p.status}
                        </Badge>
                      </div>
                      <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
                        <span>Created: {format(parseISO(p.created_at), "MMM d, yyyy")}</span>
                        <span className="font-medium text-foreground">{formatCurrency(p.quoted_price)}</span>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 border-t bg-muted/5 p-4 sm:border-l sm:border-t-0">
                    {p.file_url ? (
                      <Button variant="ghost" size="sm" className="h-9 gap-1.5 text-xs" asChild>
                        <a href={p.file_url} target="_blank" rel="noreferrer">
                          <Download className="h-3.5 w-3.5" />
                          Document
                        </a>
                      </Button>
                    ) : null}
                    <ProposalDrawer
                      opportunityId={id}
                      proposal={p}
                      trigger={
                        <Button variant="ghost" size="sm" className="h-9 gap-1.5 text-xs">
                          <ExternalLink className="h-3.5 w-3.5" />
                          Open
                        </Button>
                      }
                    />
                  </div>
                </div>
              </CardContent>
            </Card>
          ))
        ) : (
          <Card className="flex flex-col items-center justify-center py-20 text-center border-dashed">
            <div className="rounded-full bg-muted/50 p-4 mb-4">
              <FileText className="h-8 w-8 text-muted-foreground/50" />
            </div>
            <p className="text-sm text-muted-foreground">No proposals for this opportunity yet.</p>
            <div className="mt-4">
              <ProposalDrawer
                opportunityId={id}
                trigger={
                  <Button variant="outline" size="sm">
                    Draft the first version
                  </Button>
                }
              />
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
