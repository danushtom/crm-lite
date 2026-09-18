"use client";

/**
 * The CRM assistant panel.
 *
 * Talks to `POST /api/v1/ai/chat` on the FastAPI backend, not to a model provider. Two things
 * changed from the previous version and both matter:
 *
 *  - It no longer sends CRM data. The old drawer posted a `contextData` blob that the server
 *    pasted into the system prompt, which let the client choose what the model saw. The backend
 *    now reads the CRM itself through the caller's own RLS-scoped connection.
 *  - It no longer uses the Vercel AI SDK. The app had `@ai-sdk/react@4` talking to a route built
 *    on `ai@3`, a mismatch papered over with `// @ts-nocheck`. Parsing the stream directly is a
 *    few more lines and removes three dependencies plus the version coupling.
 */

import { Sparkles, Send, Bot, User, X } from "lucide-react";
import { Button, Input, cn } from "@dracara/ui";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, apiStream } from "@/lib/api";

type Message = { id: string; role: "user" | "assistant"; content: string };
type ChatFrame = { delta?: string; error?: string };

const SUGGESTIONS = [
  "Which deals are stalling?",
  "What should I follow up on today?",
  "Summarise my pipeline by stage",
];

export function AskAiDrawer({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isLoading]);

  // Abandon an in-flight answer when the drawer closes, so a long reply does not keep streaming
  // into a panel nobody is looking at.
  useEffect(() => {
    if (!open) abortRef.current?.abort();
  }, [open]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const send = useCallback(
    async (question: string) => {
      const trimmed = question.trim();
      if (!trimmed || isLoading) return;

      const history = [...messages, { id: crypto.randomUUID(), role: "user" as const, content: trimmed }];
      const replyId = crypto.randomUUID();
      setMessages([...history, { id: replyId, role: "assistant", content: "" }]);
      setInput("");
      setIsLoading(true);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const stream = apiStream<ChatFrame>("/ai/chat", {
          method: "POST",
          signal: controller.signal,
          body: JSON.stringify({
            messages: history.map(({ role, content }) => ({ role, content })),
          }),
        });

        for await (const frame of stream) {
          if (frame.error) {
            setMessages((current) =>
              current.map((m) => (m.id === replyId ? { ...m, content: frame.error! } : m)),
            );
            break;
          }
          if (frame.delta) {
            setMessages((current) =>
              current.map((m) =>
                m.id === replyId ? { ...m, content: m.content + frame.delta } : m,
              ),
            );
          }
        }
      } catch (err) {
        if (controller.signal.aborted) return;
        // ApiError carries the backend's problem-details `detail`, which is written for a human --
        // a 501 here says exactly which environment variables are missing, for instance.
        const detail =
          err instanceof ApiError
            ? err.message
            : "The assistant is unavailable right now. Please try again.";
        setMessages((current) =>
          current.map((m) => (m.id === replyId ? { ...m, content: detail } : m)),
        );
      } finally {
        if (abortRef.current === controller) abortRef.current = null;
        setIsLoading(false);
      }
    },
    [isLoading, messages],
  );

  if (!open) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm transition-opacity animate-in fade-in"
        onClick={() => onOpenChange(false)}
      />

      {/* Drawer */}
      <div className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-border bg-card shadow-2xl animate-in slide-in-from-right duration-300 sm:max-w-[400px]">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-[#0B7FB3] to-purple-600 text-white">
              <Sparkles className="h-4 w-4" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-foreground">Ask AI</h2>
              <p className="text-[11px] text-muted-foreground">Reads only what you can see</p>
            </div>
          </div>
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => onOpenChange(false)}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* Messages */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center space-y-4 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted/50">
                <Sparkles className="h-6 w-6 text-muted-foreground" />
              </div>
              <p className="max-w-[250px] text-sm text-muted-foreground">
                Ask about your pipeline, leads or deals.
              </p>
              <div className="flex flex-col gap-2 pt-2">
                {SUGGESTIONS.map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    onClick={() => void send(suggestion)}
                    className="rounded-full border border-border bg-card px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((m) => (
              <div
                key={m.id}
                className={cn("flex gap-3", m.role === "user" ? "flex-row-reverse" : "flex-row")}
              >
                <div
                  className={cn(
                    "flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
                    m.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted border border-border text-foreground",
                  )}
                >
                  {m.role === "user" ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
                </div>
                <div
                  className={cn(
                    "rounded-2xl px-4 py-2.5 max-w-[80%] text-sm",
                    m.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted/50 border border-border/50 text-foreground",
                  )}
                >
                  {m.content ? (
                    <p className="whitespace-pre-wrap leading-relaxed">{m.content}</p>
                  ) : (
                    <div className="flex gap-1 py-1">
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/40" />
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/40 [animation-delay:0.2s]" />
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/40 [animation-delay:0.4s]" />
                    </div>
                  )}
                </div>
              </div>
            ))
          )}
        </div>

        {/* Input */}
        <div className="border-t border-border bg-card/50 p-4 backdrop-blur">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void send(input);
            }}
            className="relative flex items-center"
          >
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about your deals..."
              className="h-11 rounded-full bg-card pr-12"
            />
            <Button
              type="submit"
              size="icon"
              disabled={!input.trim() || isLoading}
              className="absolute right-1.5 h-8 w-8 rounded-full"
            >
              <Send className="h-4 w-4" />
            </Button>
          </form>
        </div>
      </div>
    </>
  );
}
