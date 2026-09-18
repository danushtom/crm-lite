"use client";

import { Badge, Button, Card, CardContent, Skeleton, cn } from "@dracara/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArchiveRestore, ArrowLeft, Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { toast } from "sonner";
import { apiFetch, apiPage } from "@/lib/api";
import { useApiMutation } from "@/lib/use-api-mutation";

type Kind = "leads" | "opportunities" | "contacts" | "companies";

type DeletedRecord = {
  id: string;
  label: string;
  detail: string | null;
  deleted_at: string;
  deleted_by_name: string | null;
  blocked_by: "company" | "contact" | "lead" | null;
};

const TABS: { kind: Kind; label: string; singular: string }[] = [
  { kind: "leads", label: "Leads", singular: "lead" },
  { kind: "opportunities", label: "Opportunities", singular: "opportunity" },
  { kind: "contacts", label: "Contacts", singular: "contact" },
  { kind: "companies", label: "Companies", singular: "company" },
];

/** Which tab holds the parent a blocked record is waiting on. */
const PARENT_TAB: Record<NonNullable<DeletedRecord["blocked_by"]>, Kind> = {
  company: "companies",
  contact: "contacts",
  lead: "leads",
};

const PAGE_SIZE = 50;

const when = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" });

export default function RecentlyDeletedPage() {
  return (
    <Suspense fallback={<Skeleton className="h-64 w-full max-w-4xl" />}>
      <RecentlyDeleted />
    </Suspense>
  );
}

function RecentlyDeleted() {
  const params = useSearchParams();
  const router = useRouter();
  const kind = (TABS.find((t) => t.kind === params.get("kind"))?.kind ?? "leads") as Kind;
  const tab = TABS.find((t) => t.kind === kind)!;
  const [page, setPage] = useState(0);
  const qc = useQueryClient();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["recently-deleted", kind, page],
    queryFn: () => apiPage<DeletedRecord>(`/recently-deleted?kind=${kind}&limit=${PAGE_SIZE}&offset=${page * PAGE_SIZE}`),
  });

  const restore = useApiMutation({
    mutationFn: (record: DeletedRecord) =>
      apiFetch(`/recently-deleted/${kind}/${record.id}/restore`, { method: "POST" }),
    onSuccess: (_data, record) => {
      toast.success(`Restored ${record.label}`);
      // The record reappears in its own lists, and anything waiting on it may now be restorable.
      qc.invalidateQueries({ queryKey: ["recently-deleted"] });
      qc.invalidateQueries({ queryKey: [kind] });
    },
    errorTitle: "Could not restore",
  });

  return (
    <div className="max-w-4xl space-y-5">
      <div className="space-y-1">
        <Link href="/settings" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-3.5 w-3.5" /> Settings
        </Link>
        <h1 className="text-xl font-semibold tracking-tight">Recently deleted</h1>
        <p className="text-sm text-muted-foreground">
          Deleted records are kept and can be restored here. You see what you would have been allowed to delete.
        </p>
      </div>

      <div role="tablist" aria-label="Record type" className="flex flex-wrap gap-1 border-b border-border">
        {TABS.map((t) => (
          <button
            key={t.kind}
            role="tab"
            aria-selected={t.kind === kind}
            onClick={() => {
              setPage(0);
              router.replace(`/recently-deleted?kind=${t.kind}`);
            }}
            className={cn(
              "-mb-px border-b-2 px-3 py-2 text-sm font-medium",
              t.kind === kind ? "border-[hsl(var(--primary))] text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <Skeleton className="h-40 w-full" />
      ) : isError ? (
        <p className="text-sm text-destructive">Could not load deleted {tab.label.toLowerCase()}.</p>
      ) : !data?.items.length ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            {page === 0 ? `No deleted ${tab.label.toLowerCase()}.` : "No more."}
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="p-0">
            <ul className="divide-y divide-border/60">
              {data.items.map((record) => {
                const pending = restore.isPending && restore.variables?.id === record.id;
                return (
                  <li key={record.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium">{record.label}</p>
                      <p className="truncate text-xs text-muted-foreground">
                        {[record.detail, `Deleted ${when(record.deleted_at)}`, record.deleted_by_name ? `by ${record.deleted_by_name}` : null]
                          .filter(Boolean)
                          .join(" · ")}
                      </p>
                    </div>
                    {record.blocked_by ? (
                      <Link
                        href={`/recently-deleted?kind=${PARENT_TAB[record.blocked_by]}`}
                        onClick={() => setPage(0)}
                        className="text-xs"
                        title={`Its ${record.blocked_by} is deleted too. Restore that first.`}
                      >
                        <Badge variant="secondary">Restore its {record.blocked_by} first</Badge>
                      </Link>
                    ) : (
                      <Button size="sm" variant="outline" disabled={pending} onClick={() => restore.mutate(record)}>
                        {pending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ArchiveRestore className="h-3.5 w-3.5" />}
                        Restore
                      </Button>
                    )}
                  </li>
                );
              })}
            </ul>
          </CardContent>
        </Card>
      )}

      {data && (page > 0 || data.page.has_more) ? (
        <div className="flex justify-between">
          <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
            Newer
          </Button>
          <Button variant="outline" size="sm" disabled={!data.page.has_more} onClick={() => setPage((p) => p + 1)}>
            Older
          </Button>
        </div>
      ) : null}
    </div>
  );
}
