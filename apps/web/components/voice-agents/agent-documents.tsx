"use client";

import { Button, cn, toolbarButton } from "@dracara/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Trash2, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { apiFetch } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useApiMutation } from "@/lib/use-api-mutation";
import type { VoiceAgentDocument } from "@dracara/types";

/**
 * The agent's knowledge base: pricing sheets, FAQs and scripts it can quote from mid-call.
 *
 * All three endpoints (list/upload/delete) shipped with the backend and had no UI, so the
 * "uploaded documents" half of the agent dataset was unreachable. `apiFetch` already passes a
 * FormData body through untouched, so no new fetch plumbing is needed here.
 */
export function AgentDocuments({ voiceAgentId }: { voiceAgentId: string }) {
  const qc = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const [pendingName, setPendingName] = useState<string | null>(null);

  const { data: documents, isLoading } = useQuery({
    queryKey: ["voice-agents", voiceAgentId, "documents"],
    queryFn: () => apiFetch<VoiceAgentDocument[]>(`/voice-agents/${voiceAgentId}/documents`),
  });

  const invalidate = () =>
    qc.invalidateQueries({ queryKey: ["voice-agents", voiceAgentId, "documents"] });

  const upload = useApiMutation({
    errorTitle: "Could not upload this document",
    mutationFn: (file: File) => {
      const body = new FormData();
      body.append("file", file);
      return apiFetch<VoiceAgentDocument>(`/voice-agents/${voiceAgentId}/documents`, {
        method: "POST",
        body,
      });
    },
    onSuccess: (doc) => {
      invalidate();
      toast.success("Document uploaded", { description: doc.filename });
    },
    onSettled: () => {
      setPendingName(null);
      // Clear the input so re-picking the same file still fires a change event.
      if (fileInput.current) fileInput.current.value = "";
    },
  });

  const remove = useApiMutation({
    errorTitle: "Could not delete this document",
    mutationFn: (documentId: string) =>
      apiFetch(`/voice-agents/${voiceAgentId}/documents/${documentId}`, { method: "DELETE" }),
    onSuccess: () => {
      invalidate();
      toast.success("Document deleted");
    },
  });

  return (
    <div className="space-y-2">
      <input
        ref={fileInput}
        type="file"
        className="hidden"
        accept=".pdf,.txt,.md,.csv,.docx"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (!file) return;
          setPendingName(file.name);
          upload.mutate(file);
        }}
      />

      <Button
        type="button"
        variant="outline"
        className={cn(toolbarButton, "w-full justify-center")}
        disabled={upload.isPending}
        onClick={() => fileInput.current?.click()}
      >
        <Upload className="h-3.5 w-3.5" />
        {upload.isPending ? `Uploading ${pendingName}…` : "Upload document"}
      </Button>

      {isLoading ? (
        <p className="text-xs text-muted-foreground">Loading documents…</p>
      ) : (documents ?? []).length === 0 ? (
        <p className="text-xs text-muted-foreground">
          No documents yet. Upload a pricing sheet, FAQ or script for the agent to draw on.
        </p>
      ) : (
        <ul className="space-y-1">
          {documents!.map((doc) => (
            <li
              key={doc.id}
              className="flex items-center gap-2 rounded-md border border-border/60 px-2.5 py-1.5"
            >
              <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
              <a
                href={doc.file_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex-1 truncate text-xs font-medium text-foreground hover:underline"
              >
                {doc.filename}
              </a>
              <span className="shrink-0 text-[11px] text-muted-foreground">
                {formatDate(doc.created_at)}
              </span>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-6 w-6 shrink-0 text-muted-foreground hover:text-destructive"
                aria-label={`Delete ${doc.filename}`}
                disabled={remove.isPending}
                onClick={() => remove.mutate(doc.id)}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
