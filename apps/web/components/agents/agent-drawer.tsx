"use client";

import { Button } from "@dracara/ui";
import { useQueryClient } from "@tanstack/react-query";
import { Pencil, UserCog } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { apiFetch } from "@/lib/api";
import { compactPayload } from "@/lib/forms";
import { useApiMutation } from "@/lib/use-api-mutation";
import { EntityDrawer, SelectField, TextField } from "@/components/shared/entity-drawer";

export type AgentSummary = {
  id: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  timezone?: string;
  version: number;
};

const ROLE_OPTIONS = [
  { value: "admin", label: "Admin — full access" },
  { value: "agent", label: "Agent — own leads" },
  { value: "sdr", label: "SDR — outreach" },
  { value: "partner", label: "Partner — read-only intelligence" },
];

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
 * demote or deactivate the last active admin, so this cannot lock the organisation out.
 */
export function AgentDrawer({ agent }: { agent: AgentSummary }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    full_name: agent.full_name ?? "",
    role: agent.role,
    is_active: String(agent.is_active),
    timezone: agent.timezone ?? "Asia/Kolkata",
  });

  useEffect(() => {
    if (!open) return;
    setForm({
      full_name: agent.full_name ?? "",
      role: agent.role,
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
        method: "PATCH",
        headers: { "If-Match": `"${agent.version}"` },
        body: JSON.stringify(
          compactPayload({
            full_name: form.full_name.trim(),
            role: form.role,
            timezone: form.timezone,
            // A boolean, so compactPayload must not see it as an empty string.
            is_active: form.is_active === "true",
          })
        ),
      }),
    onSuccess: (saved) => {
      qc.invalidateQueries({ queryKey: ["agents"] });
      toast.success("Team member updated", {
        description: `${saved.full_name || saved.email} — ${saved.role}`,
      });
      setOpen(false);
    },
  });

  const roleChanged = form.role !== agent.role;
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
        value={form.role}
        onChange={(v) => set("role", v)}
        options={ROLE_OPTIONS}
        hint={
          roleChanged
            ? "Takes effect the next time they load the app."
            : "Partners can read CRM intelligence but not edit it."
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

      <p className="text-xs text-muted-foreground">
        The last active admin cannot be demoted or have access revoked — otherwise nobody
        could administer the workspace.
      </p>
    </EntityDrawer>
  );
}
