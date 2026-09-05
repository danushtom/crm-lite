"use client";

import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input } from "@dracara/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useApiMutation } from "@/lib/use-api-mutation";
import { useState } from "react";
import { apiFetch, apiList } from "@/lib/api";
import { AgentDrawer, type AgentSummary } from "@/components/agents/agent-drawer";
import { RoleDrawer } from "@/components/agents/role-drawer";
import { SelectField } from "@/components/shared/entity-drawer";
import type { Role } from "@dracara/types";

export default function AgentsPage() {
  const qc = useQueryClient();
  const { data: agents, error, isLoading } = useQuery({
    queryKey: ["agents"],
    queryFn: () => apiList<AgentSummary>("/agents"),
    retry: false,
  });

  const { data: roles, isLoading: rolesLoading } = useQuery({
    queryKey: ["roles"],
    // Not paginated -- an organization has a handful of roles, never a "page" of them.
    queryFn: () => apiFetch<Role[]>("/roles"),
    retry: false,
  });

  const [email, setEmail] = useState("");
  const [roleId, setRoleId] = useState("");
  const invite = useApiMutation({
    errorTitle: "Could not send invitation",
    mutationFn: () =>
      apiFetch("/agents/invite", {
        method: "POST",
        body: JSON.stringify({ email, role_id: roleId }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agents"] });
      setEmail("");
    },
    retry: false,
  });

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">User management</h1>
        <p className="mt-1 text-muted-foreground">
          Invite teammates, assign roles, or revoke access. Define what each role can do under
          Roles below.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Invite teammate</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-2">
          <Input
            type="email"
            placeholder="email@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="max-w-xs"
          />
          <div className="w-48">
            <SelectField
              id="invite-role"
              label="Role"
              value={roleId}
              onChange={setRoleId}
              placeholder={rolesLoading ? "Loading roles…" : "Select a role"}
              options={(roles ?? []).map((r) => ({ value: r.id, label: r.name }))}
            />
          </div>
          <Button disabled={!email || !roleId || invite.isPending} onClick={() => invite.mutate()}>
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
                <th className="px-3 py-2 text-right">Edit</th>
              </tr>
            </thead>
            <tbody>
              {(agents ?? []).map((u) => (
                <tr key={u.id} className="border-t border-border/80">
                  <td className="px-3 py-2">{u.email}</td>
                  <td className="px-3 py-2">{u.role_name}</td>
                  <td className="px-3 py-2">{u.is_active ? "Yes" : "Revoked"}</td>
                  <td className="px-3 py-2 text-right">
                    <AgentDrawer agent={u} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {invite.isError ? <p className="text-sm text-destructive">{(invite.error as Error).message}</p> : null}

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle>Roles</CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              What each role can do. Create a custom role by picking permissions, or edit one
              of the defaults below.
            </p>
          </div>
          <RoleDrawer
            trigger={
              <Button size="sm">
                <Plus className="mr-1.5 h-4 w-4" />
                New role
              </Button>
            }
          />
        </CardHeader>
        <CardContent className="overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                <th className="px-3 py-2 text-left">Name</th>
                <th className="px-3 py-2 text-left">Access</th>
                <th className="px-3 py-2 text-left">Permissions</th>
                <th className="px-3 py-2 text-left">Users</th>
                <th className="px-3 py-2 text-right">Edit</th>
              </tr>
            </thead>
            <tbody>
              {(roles ?? []).map((r) => (
                <tr key={r.id} className="border-t border-border/80">
                  <td className="px-3 py-2 font-medium">
                    {r.name} {r.is_system ? <Badge variant="secondary" className="ml-1.5 align-middle text-[10px]">Default</Badge> : null}
                  </td>
                  <td className="px-3 py-2">
                    {r.grants_full_access ? <Badge className="text-[10px]">Full access</Badge> : "—"}
                  </td>
                  <td className="px-3 py-2 text-muted-foreground">
                    {r.grants_full_access ? "Everything" : `${r.permissions.length} granted`}
                  </td>
                  <td className="px-3 py-2">{r.user_count}</td>
                  <td className="px-3 py-2 text-right">
                    <RoleDrawer
                      role={r}
                      trigger={
                        <Button variant="ghost" size="sm">
                          Edit
                        </Button>
                      }
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}
