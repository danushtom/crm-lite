"use client";

import { Button } from "@dracara/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, UserCog } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { apiFetch } from "@/lib/api";
import { compactPayload } from "@/lib/forms";
import { useApiMutation } from "@/lib/use-api-mutation";
import { EntityDrawer, SelectField, TextField } from "@/components/shared/entity-drawer";
import type { Role } from "@dracara/types";

export type AgentSummary = {
  id: string;
  email: string;
  full_name: string;
  role_id: string;
  role_name: string;
  is_active: boolean;
  timezone?: string;
};

const ACCESS_OPTIONS = [
  { value: "true", label: "Active" },
  { value: "false", label: "Access revoked" },
];

const COMMON_TIMEZONES = [
  "Asia/Kolkata",
  "Asia/Dubai",
  "Asia/Singapore",
  "Europe/London",
  "Europe/Berlin",
  "America/New_York",
  "America/Los_Angeles",
  "Australia/Sydney",
];

/**
 * Change a team member's role, name, timezone or access.
 *
 * Admins could previously invite people but never change or revoke them — there was no way to
 * promote an agent or switch off access for someone who had left. The database refuses to
 * demote or deactivate the organization's last full-access user, so this cannot lock the
 * workspace out.
 */
export function AgentDrawer({ agent }: { agent: AgentSummary }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    full_name: agent.full_name ?? "",
    role_id: agent.role_id,
    is_active: String(agent.is_active),
    timezone: agent.timezone ?? "Asia/Kolkata",
  });

  const { data: roles } = useQuery({
    queryKey: ["roles"],
    queryFn: () => apiFetch<Role[]>("/roles"),
  });
  const roleOptions = (roles ?? []).map((r) => ({
    value: r.id,
    label: r.grants_full_access ? `${r.name} — full access` : r.name,
  }));

  useEffect(() => {
    if (!open) return;
    setForm({
      full_name: agent.full_name ?? "",
      role_id: agent.role_id,
      is_active: String(agent.is_active),
      timezone: agent.timezone ?? "Asia/Kolkata",
    });
  }, [open, agent]);

  const set = (key: keyof typeof form, value: string) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const save = useApiMutation({
    errorTitle: "Could not update this team member",
    mutationFn: () =>
      apiFetch<AgentSummary>(`/agents/${agent.id}`, {
        // No If-Match: public.users has no version column (it was never added to the
        // bump_version() table list), so there is nothing to make this conditional on.
        method: "PATCH",
        body: JSON.stringify(
          compactPayload({
            full_name: form.full_name.trim(),
            role_id: form.role_id,
            timezone: form.timezone,
            // A boolean, so compactPayload must not see it as an empty string.
            is_active: form.is_active === "true",
          })
        ),
      }),
    onSuccess: (saved) => {
      qc.invalidateQueries({ queryKey: ["agents"] });
      qc.invalidateQueries({ queryKey: ["roles"] });
      toast.success("Team member updated", {
        description: `${saved.full_name || saved.email} — ${saved.role_name}`,
      });
      setOpen(false);
    },
  });

  // GET /agents/{id}/performance has existed unused since the API was built; tdd.md 13.2
  // specifies this table. Fetched only while the drawer is open, so the roster listing does
  // not turn into one request per person.
  const { data: performance } = useQuery({
    queryKey: ["agent-performance", agent.id],
    queryFn: () =>
      apiFetch<{
        assigned_leads: number;
        stage_moves_logged: number;
        meetings_count: number;
        wins: number;
        win_rate: number;
      }>(`/agents/${agent.id}/performance`),
    enabled: open,
  });

  const roleChanged = form.role_id !== agent.role_id;
  const accessChanged = form.is_active !== String(agent.is_active);

  return (
    <EntityDrawer
      open={open}
      onOpenChange={setOpen}
      trigger={
        <Button variant="ghost" size="icon" className="h-8 w-8" aria-label={`Edit ${agent.email}`}>
          <Pencil className="h-3.5 w-3.5" />
        </Button>
      }
      icon={UserCog}
      title="Team member"
      description={agent.email}
      submitLabel="Save changes"
      canSubmit
      isPending={save.isPending}
      onSubmit={() => save.mutate()}
    >
      <TextField
        id="agent-name"
        label="Full name"
        placeholder="Sam Agent"
        value={form.full_name}
        onChange={(v) => set("full_name", v)}
      />

      <SelectField
        id="agent-role"
        label="Role"
        value={form.role_id}
        onChange={(v) => set("role_id", v)}
        options={roleOptions}
        hint={
          roleChanged
            ? "Takes effect the next time they load the app."
            : "Manage what each role can do from the Roles tab."
        }
      />

      <SelectField
        id="agent-access"
        label="Access"
        value={form.is_active}
        onChange={(v) => set("is_active", v)}
        options={ACCESS_OPTIONS}
        hint={
          accessChanged && form.is_active === "false"
            ? "They keep everything they own; only their access is revoked."
            : undefined
        }
      />

      <SelectField
        id="agent-timezone"
        label="Timezone"
        value={form.timezone}
        onChange={(v) => set("timezone", v)}
        options={COMMON_TIMEZONES.map((t) => ({ value: t, label: t.replace("_", " ") }))}
        hint="Decides when their follow-up queue rolls over to the next day."
      />

      <div className="space-y-2 rounded-lg border border-border/60 bg-muted/20 p-3">
        <p className="text-xs font-bold uppercase tracking-widest text-muted-foreground">
          Performance
        </p>
        {performance ? (
          <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
            <Stat label="Leads owned" value={performance.assigned_leads} />
            <Stat label="Won" value={performance.wins} />
            <Stat label="Meetings" value={performance.meetings_count} />
            <Stat label="Stage moves" value={performance.stage_moves_logged} />
            <Stat
              label="Win rate"
              value={
                performance.assigned_leads === 0
                  ? "—"
                  : `${Math.round(performance.win_rate * 100)}%`
              }
            />
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">Loading…</p>
        )}
      </div>

      <p className="text-xs text-muted-foreground">
        The organization's last full-access user cannot be demoted or have access revoked —
        otherwise nobody could administer the workspace.
      </p>
    </EntityDrawer>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="font-semibold tabular-nums">{value}</span>
    </div>
  );
}
