"use client";

import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input, cn, primaryButton, toolbarButton } from "@dracara/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useApiMutation } from "@/lib/use-api-mutation";
import { useMemo, useState } from "react";
import { apiFetch, apiList } from "@/lib/api";
import { AgentDrawer, type AgentSummary } from "@/components/agents/agent-drawer";
import { RoleDrawer } from "@/components/agents/role-drawer";
import { SelectField } from "@/components/shared/entity-drawer";
import { Avatar } from "@/components/shared/avatar";
import { DataTable, type Column } from "@/components/shared/data-table";
import { ListToolbar, ToolbarSearch } from "@/components/shared/list-toolbar";
import { PageSection } from "@/components/shared/page-section";
import { TablePagination } from "@/components/shared/table-pagination";
import { compareValues, usePagination, useSort } from "@/lib/use-table-controls";
import type { Role } from "@dracara/types";

type AgentSortKey = "name" | "email" | "role" | "status";

/** The value each sortable column sorts on, kept next to the column definitions below. */
const AGENT_SORT_VALUES: Record<AgentSortKey, (agent: AgentSummary) => string | number> = {
  name: (a) => a.full_name ?? "",
  email: (a) => a.email,
  role: (a) => a.role_name ?? "",
  // Active first when ascending: the roster is normally read to find live users.
  status: (a) => (a.is_active ? 0 : 1),
};

export default function AgentsPage() {
  const qc = useQueryClient();
  const { data: agents, error, isLoading } = useQuery({
    queryKey: ["agents"],
    queryFn: () => apiList<AgentSummary>("/agents"),
    retry: false,
  });

  const { data: roles, isLoading: rolesLoading, error: rolesError } = useQuery({
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
      qc.invalidateQueries({ queryKey: ["roles"] });
      setEmail("");
    },
    retry: false,
  });

  const [search, setSearch] = useState("");
  const { sortKey, sortDirection, toggleSort } = useSort<AgentSortKey>("name");

  const visibleAgents = useMemo(() => {
    const term = search.trim().toLowerCase();
    const filtered = (agents ?? []).filter((a) =>
      term
        ? `${a.full_name ?? ""} ${a.email} ${a.role_name ?? ""}`.toLowerCase().includes(term)
        : true
    );
    const value = AGENT_SORT_VALUES[sortKey];
    return [...filtered].sort((a, b) => compareValues(value(a), value(b), sortDirection));
  }, [agents, search, sortKey, sortDirection]);

  const pagination = usePagination(visibleAgents);

  const agentColumns: Column<AgentSummary, AgentSortKey>[] = [
    {
      key: "name",
      header: "Name",
      sortKey: "name",
      skeletonWidth: "w-40",
      cell: (a) => (
        <div className="flex items-center gap-2.5">
          <Avatar name={a.full_name || a.email} />
          <span className="text-[13px] font-semibold text-foreground">
            {a.full_name || "Invitation pending"}
          </span>
        </div>
      ),
    },
    {
      key: "email",
      header: "Email",
      sortKey: "email",
      skeletonWidth: "w-48",
      cell: (a) => <span className="text-muted-foreground">{a.email}</span>,
    },
    {
      key: "role",
      header: "Role",
      sortKey: "role",
      cell: (a) => a.role_name ?? "—",
    },
    {
      key: "status",
      header: "Status",
      sortKey: "status",
      skeletonWidth: "w-16",
      cell: (a) =>
        a.is_active ? (
          <Badge className="h-5 rounded-md bg-emerald-100 px-2 text-[10px] font-semibold text-emerald-700 hover:bg-emerald-100 dark:bg-emerald-900/30 dark:text-emerald-300">
            Active
          </Badge>
        ) : (
          <Badge variant="secondary" className="h-5 rounded-md px-2 text-[10px] font-semibold">
            Revoked
          </Badge>
        ),
    },
    {
      key: "actions",
      header: <span className="sr-only">Edit</span>,
      className: "text-right",
      skeletonWidth: "w-8",
      cell: (a) => <AgentDrawer agent={a} />,
    },
  ];

  const roleColumns: Column<Role>[] = [
    {
      key: "name",
      header: "Name",
      skeletonWidth: "w-32",
      cell: (r) => (
        <span className="font-medium text-foreground">
          {r.name}
          {r.is_system ? (
            <Badge variant="secondary" className="ml-1.5 align-middle text-[10px]">
              Default
            </Badge>
          ) : null}
        </span>
      ),
    },
    {
      key: "access",
      header: "Access",
      cell: (r) =>
        r.grants_full_access ? (
          <Badge className="h-5 rounded-md px-2 text-[10px] font-semibold">Full access</Badge>
        ) : (
          <span className="text-muted-foreground">Scoped</span>
        ),
    },
    {
      key: "permissions",
      header: "Permissions",
      cell: (r) => (
        <span className="text-muted-foreground">
          {r.grants_full_access ? "Everything" : `${r.permissions.length} granted`}
        </span>
      ),
    },
    {
      key: "users",
      header: "Users",
      cell: (r) => <span className="tabular-nums">{r.user_count}</span>,
    },
    {
      key: "actions",
      header: <span className="sr-only">Edit</span>,
      className: "text-right",
      skeletonWidth: "w-12",
      cell: (r) => (
        <RoleDrawer
          role={r}
          trigger={
            <Button variant="ghost" size="sm" className="h-8 text-xs">
              Edit
            </Button>
          }
        />
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground">
        Invite teammates, assign roles, or revoke access. Define what each role can do under Roles
        below.
      </p>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Invite teammate</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex flex-wrap items-end gap-2">
            <Input
              type="email"
              placeholder="email@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="h-8 max-w-xs rounded-md border-border/70 text-xs"
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
            <Button
              className={primaryButton}
              disabled={!email || !roleId || invite.isPending}
              onClick={() => invite.mutate()}
            >
              {invite.isPending ? "Sending…" : "Send invite"}
            </Button>
          </div>
          {invite.isError ? (
            <p className="text-xs text-destructive">{(invite.error as Error).message}</p>
          ) : null}
        </CardContent>
      </Card>

      <PageSection
        title="Team members"
        description={
          agents ? `${agents.length} ${agents.length === 1 ? "person" : "people"} in this workspace` : undefined
        }
      >
        <div className="space-y-2.5">
          <ListToolbar
            left={
              <ToolbarSearch
                value={search}
                onChange={setSearch}
                placeholder="Search name, email or role…"
                label="Search team members"
              />
            }
          />
          <DataTable
            rows={pagination.pageRows}
            columns={agentColumns}
            isLoading={isLoading}
            error={(error as Error) ?? null}
            emptyMessage={
              search ? "No teammates match that search." : "Nobody has been invited yet."
            }
            sortKey={sortKey}
            sortDirection={sortDirection}
            onSort={toggleSort}
            minWidth="min-w-[720px]"
          />
          <TablePagination
            page={pagination.page}
            pageCount={pagination.pageCount}
            pageSize={pagination.pageSize}
            total={pagination.total}
            onPageChange={pagination.setPage}
            onPageSizeChange={pagination.setPageSize}
          />
        </div>
      </PageSection>

      <PageSection
        title="Roles"
        description="What each role can do. Create a custom role by picking permissions, or edit one of the defaults."
        action={
          <RoleDrawer
            trigger={
              <Button variant="outline" className={cn(toolbarButton, "font-semibold")}>
                <Plus className="h-3.5 w-3.5" />
                New role
              </Button>
            }
          />
        }
      >
        <DataTable
          rows={roles ?? []}
          columns={roleColumns}
          isLoading={rolesLoading}
          error={(rolesError as Error) ?? null}
          emptyMessage="No roles defined."
          minWidth="min-w-[640px]"
          skeletonRows={4}
        />
      </PageSection>
    </div>
  );
}
