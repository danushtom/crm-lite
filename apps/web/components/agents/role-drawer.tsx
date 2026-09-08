"use client";

import { Button } from "@dracara/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldPlus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { apiFetch } from "@/lib/api";
import { useApiMutation } from "@/lib/use-api-mutation";
import { EntityDrawer, Field, TextField, labelClass } from "@/components/shared/entity-drawer";
import type { Role } from "@dracara/types";

type Permission = { resource: string; action: string; description: string };

type RoleFormState = {
  name: string;
  grants_full_access: boolean;
  permission_keys: string[];
};

function emptyForm(role?: Role): RoleFormState {
  return {
    name: role?.name ?? "",
    grants_full_access: role?.grants_full_access ?? false,
    permission_keys: role?.permissions ?? [],
  };
}

/**
 * Create a role from scratch, or edit an existing one's name, permissions, and full-access
 * flag. Permissions are feature gates -- who can see which rows is unaffected by anything
 * checked here, except "grants full access", which bypasses row ownership entirely within
 * the organization (see is_admin() in the database).
 */
export function RoleDrawer({ role, trigger }: { role?: Role; trigger: React.ReactNode }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<RoleFormState>(emptyForm(role));
  const isEdit = Boolean(role);

  useEffect(() => {
    if (open) setForm(emptyForm(role));
  }, [open, role]);

  const { data: catalog } = useQuery({
    queryKey: ["roles", "catalog"],
    queryFn: () => apiFetch<Permission[]>("/roles/catalog"),
    enabled: open,
  });

  const grouped = new Map<string, Permission[]>();
  for (const p of catalog ?? []) {
    const list = grouped.get(p.resource) ?? [];
    list.push(p);
    grouped.set(p.resource, list);
  }

  const togglePermission = (key: string) =>
    setForm((prev) => ({
      ...prev,
      permission_keys: prev.permission_keys.includes(key)
        ? prev.permission_keys.filter((k) => k !== key)
        : [...prev.permission_keys, key],
    }));

  const save = useApiMutation({
    errorTitle: isEdit ? "Could not update this role" : "Could not create this role",
    mutationFn: () =>
      isEdit
        ? apiFetch<Role>(`/roles/${role!.id}`, {
            method: "PATCH",
            body: JSON.stringify({
              name: form.name.trim(),
              grants_full_access: form.grants_full_access,
              permission_keys: form.permission_keys,
            }),
          })
        : apiFetch<Role>("/roles", {
            method: "POST",
            body: JSON.stringify({
              name: form.name.trim(),
              grants_full_access: form.grants_full_access,
              permission_keys: form.permission_keys,
            }),
          }),
    onSuccess: (saved) => {
      qc.invalidateQueries({ queryKey: ["roles"] });
      qc.invalidateQueries({ queryKey: ["agents"] });
      toast.success(isEdit ? "Role updated" : "Role created", { description: saved.name });
      setOpen(false);
    },
  });

  const del = useApiMutation({
    errorTitle: "Could not delete this role",
    mutationFn: () =>
      apiFetch(`/roles/${role!.id}`, {
        method: "DELETE",
        headers: { "If-Match": `"${role!.version}"` },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["roles"] });
      qc.invalidateQueries({ queryKey: ["agents"] });
      toast.success("Role deleted", { description: role!.name });
      setOpen(false);
    },
  });

  return (
    <EntityDrawer
      open={open}
      onOpenChange={setOpen}
      trigger={trigger}
      icon={ShieldPlus}
      title={isEdit ? "Edit role" : "Create role"}
      description={isEdit ? role!.name : "Pick what this role can do, then assign it to a teammate."}
      submitLabel={isEdit ? "Save changes" : "Create role"}
      canSubmit={form.name.trim().length > 0}
      isPending={save.isPending}
      onSubmit={() => save.mutate()}
      destructiveAction={
        isEdit ? (
          <Button
            type="button"
            variant="ghost"
            className="text-destructive hover:text-destructive"
            disabled={del.isPending}
            onClick={() => del.mutate()}
          >
            <Trash2 className="mr-2 h-4 w-4" />
            Delete role
          </Button>
        ) : undefined
      }
    >
      <TextField
        id="role-name"
        label="Name"
        placeholder="Sales Lead"
        value={form.name}
        onChange={(v) => setForm((p) => ({ ...p, name: v }))}
        required
      />

      <Field
        label="Full access"
        hint="Bypasses ownership entirely -- sees and edits everything in the organization, same as today's admin. Every organization must keep at least one active user with this."
      >
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={form.grants_full_access}
            onChange={(e) => setForm((p) => ({ ...p, grants_full_access: e.target.checked }))}
          />
          Grants full access to the organization
        </label>
      </Field>

      <Field label="Permissions" hint="Ignored while full access is checked above.">
        <div className="space-y-3 rounded-lg border border-border/60 p-3">
          {[...grouped.entries()].map(([resource, perms]) => (
            <div key={resource}>
              <p className={labelClass}>{resource}</p>
              <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
                {perms.map((p) => {
                  const key = `${p.resource}.${p.action}`;
                  return (
                    <label key={key} className="flex items-center gap-1.5 text-sm" title={p.description}>
                      <input
                        type="checkbox"
                        checked={form.permission_keys.includes(key)}
                        onChange={() => togglePermission(key)}
                        disabled={form.grants_full_access}
                      />
                      {p.action}
                    </label>
                  );
                })}
              </div>
            </div>
          ))}
          {!catalog ? <p className="text-xs text-muted-foreground">Loading…</p> : null}
        </div>
      </Field>
    </EntityDrawer>
  );
}
