"use client";

import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Skeleton,
  cn,
  fieldLabel,
  primaryButton,
  toolbarButton,
} from "@dracara/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, Eye, EyeOff, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { apiFetch } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useApiMutation } from "@/lib/use-api-mutation";

type CaptureKey = {
  id: string;
  name: string;
  key: string;
  is_active: boolean;
  owner_id: string | null;
  created_at: string | null;
  last_used_at: string | null;
};

/**
 * Capture keys for the public lead-capture endpoint.
 *
 * One key per landing page or ad platform, so a leaked one can be revoked without taking the
 * others down. Revoking is preferred to deleting: the record of which key a lead arrived
 * through outlives the key itself.
 */
export function CaptureKeysCard() {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [revealed, setRevealed] = useState<Record<string, boolean>>({});
  const [copied, setCopied] = useState<string | null>(null);

  const { data: keys, isLoading, error } = useQuery({
    queryKey: ["lead-capture-keys"],
    queryFn: () => apiFetch<CaptureKey[]>("/lead-capture/keys"),
    retry: false,
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["lead-capture-keys"] });

  const create = useApiMutation({
    errorTitle: "Could not create this key",
    mutationFn: () =>
      apiFetch<CaptureKey>("/lead-capture/keys", {
        method: "POST",
        body: JSON.stringify({ name: name.trim() }),
      }),
    onSuccess: (created) => {
      invalidate();
      setName("");
      // Shown immediately: this is the one moment the person creating it is looking at it.
      setRevealed((prev) => ({ ...prev, [created.id]: true }));
      toast.success("Capture key created", { description: created.name });
    },
  });

  const setActive = useApiMutation({
    errorTitle: "Could not update this key",
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      apiFetch(`/lead-capture/keys/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ is_active }),
      }),
    onSuccess: (_data, variables) => {
      invalidate();
      toast.success(variables.is_active ? "Key re-enabled" : "Key revoked", {
        description: variables.is_active
          ? undefined
          : "Submissions using it are now rejected silently.",
      });
    },
  });

  const remove = useApiMutation({
    errorTitle: "Could not delete this key",
    mutationFn: (id: string) => apiFetch(`/lead-capture/keys/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      invalidate();
      toast.success("Key deleted");
    },
  });

  const copy = async (key: CaptureKey) => {
    try {
      await navigator.clipboard.writeText(key.key);
      setCopied(key.id);
      window.setTimeout(() => setCopied(null), 2000);
    } catch {
      toast.error("Could not copy", { description: "Reveal the key and copy it by hand." });
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Lead capture keys</CardTitle>
        <CardDescription>
          Let a landing page or ad lead form create leads here without a login. Create one key
          per form, so a leaked key can be revoked on its own.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Meta lead form"
            aria-label="Key name"
            className="h-8 max-w-[220px] rounded-md border-border/70 text-xs"
          />
          <Button
            className={primaryButton}
            disabled={!name.trim() || create.isPending}
            onClick={() => create.mutate()}
          >
            {create.isPending ? "Creating…" : "Create key"}
          </Button>
        </div>

        {error ? (
          <p className="text-sm text-destructive">{(error as Error).message}</p>
        ) : isLoading ? (
          <Skeleton className="h-16 w-full" />
        ) : (keys ?? []).length === 0 ? (
          <p className="text-xs text-muted-foreground">
            No keys yet. Create one, then point your form at it.
          </p>
        ) : (
          <ul className="space-y-2">
            {keys!.map((key) => (
              <li
                key={key.id}
                className={cn(
                  "space-y-2 rounded-lg border border-border/60 p-3",
                  !key.is_active && "opacity-60"
                )}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-semibold text-foreground">{key.name}</span>
                  {key.is_active ? (
                    <Badge className="h-5 rounded-md bg-emerald-100 px-2 text-[10px] font-semibold text-emerald-700 hover:bg-emerald-100 dark:bg-emerald-900/30 dark:text-emerald-300">
                      Active
                    </Badge>
                  ) : (
                    <Badge variant="secondary" className="h-5 rounded-md px-2 text-[10px]">
                      Revoked
                    </Badge>
                  )}
                  <span className="ml-auto text-[11px] text-muted-foreground">
                    {key.last_used_at
                      ? `Last used ${formatDate(key.last_used_at)}`
                      : "Never used"}
                  </span>
                </div>

                <div className="flex items-center gap-1.5">
                  <code className="flex-1 truncate rounded bg-muted/50 px-2 py-1 font-mono text-[11px]">
                    {revealed[key.id] ? key.key : "•".repeat(24)}
                  </code>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7"
                    aria-label={revealed[key.id] ? "Hide key" : "Reveal key"}
                    onClick={() =>
                      setRevealed((prev) => ({ ...prev, [key.id]: !prev[key.id] }))
                    }
                  >
                    {revealed[key.id] ? (
                      <EyeOff className="h-3.5 w-3.5" />
                    ) : (
                      <Eye className="h-3.5 w-3.5" />
                    )}
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7"
                    aria-label={`Copy ${key.name}`}
                    onClick={() => copy(key)}
                  >
                    {copied === key.id ? (
                      <Check className="h-3.5 w-3.5 text-emerald-600" />
                    ) : (
                      <Copy className="h-3.5 w-3.5" />
                    )}
                  </Button>
                </div>

                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    className={cn(toolbarButton, "h-7")}
                    disabled={setActive.isPending}
                    onClick={() =>
                      setActive.mutate({ id: key.id, is_active: !key.is_active })
                    }
                  >
                    {key.is_active ? "Revoke" : "Re-enable"}
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 text-muted-foreground hover:text-destructive"
                    aria-label={`Delete ${key.name}`}
                    title="Revoking is usually better: it keeps the record of which key a lead came through."
                    disabled={remove.isPending}
                    onClick={() => remove.mutate(key.id)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}

        <div className="space-y-2 rounded-lg border border-border/60 bg-muted/20 p-3">
          <p className={fieldLabel}>How to use it</p>
          <p className="text-xs text-muted-foreground">
            POST the form to the address below with the key in an{" "}
            <code className="rounded bg-muted px-1">X-Capture-Key</code> header — a header, not
            the URL, so it stays out of browser history and{" "}
            <code className="rounded bg-muted px-1">Referer</code>. Pass through whatever UTM
            parameters are on the landing page URL and they become the contact&rsquo;s
            attribution.
          </p>
          <pre className="overflow-x-auto rounded bg-muted/60 p-2 font-mono text-[11px] leading-relaxed">
{`POST /api/v1/lead-capture
X-Capture-Key: <your key>
Content-Type: application/json

{
  "full_name": "Priya Raman",
  "email": "priya@example.com",
  "company_name": "Northwind Labs",
  "utm_source": "facebook",
  "utm_medium": "cpc",
  "utm_campaign": "q3-mvp-sprint",
  "utm_content": "founder-video-a",
  "landing_page_url": "https://your-site.com/mvp"
}`}
          </pre>
          <p className="text-xs text-muted-foreground">
            It always answers <code className="rounded bg-muted px-1">202 received</code>, even
            for a bad key — so nobody can use it to work out which organizations exist.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
