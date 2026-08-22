"use client";

import { Button, Card, CardContent, CardHeader, CardTitle, Input } from "@dracara/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useApiMutation } from "@/lib/use-api-mutation";
import { useState } from "react";
import { apiFetch, apiList } from "@/lib/api";

export default function AgentsPage() {
  const qc = useQueryClient();
  const { data, error, isLoading } = useQuery({
    queryKey: ["agents"],
    queryFn: () => apiList<Record<string, unknown>>("/agents"),
    retry: false,
  });

  const [email, setEmail] = useState("");
  const invite = useApiMutation({
    errorTitle: "Could not send invitation",    mutationFn: () => apiFetch("/agents/invite", { method: "POST", body: JSON.stringify({ email }) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agents"] });
      setEmail("");
    },
    retry: false,
  });

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Agents</h1>
        <p className="mt-1 text-muted-foreground">Admin-only roster and invites.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Invite agent</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Input type="email" placeholder="email@company.com" value={email} onChange={(e) => setEmail(e.target.value)} />
          <Button disabled={!email || invite.isPending} onClick={() => invite.mutate()}>
            Invite
          </Button>
        </CardContent>
      </Card>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : error ? (
        <p className="text-sm text-destructive">{(error as Error).message}</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                <th className="px-3 py-2 text-left">Email</th>
                <th className="px-3 py-2 text-left">Role</th>
                <th className="px-3 py-2 text-left">Active</th>
              </tr>
            </thead>
            <tbody>
              {(data ?? []).map((u) => (
                <tr key={String(u.id)} className="border-t border-border/80">
                  <td className="px-3 py-2">{String(u.email)}</td>
                  <td className="px-3 py-2 capitalize">{String(u.role)}</td>
                  <td className="px-3 py-2">{String(u.is_active)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {invite.isError ? <p className="text-sm text-destructive">{(invite.error as Error).message}</p> : null}
    </div>
  );
}
