// @ts-nocheck
"use client";

import { useChat, type UIMessage } from "@ai-sdk/react";
import { Sparkles, Send, Bot, User, X } from "lucide-react";
import { Button, Input, cn } from "@dracara/ui";
import { useEffect, useRef } from "react";

export function AskAiDrawer({
  open,
  onOpenChange,
  contextData,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  contextData?: any;
}) {
  const { messages, input, handleInputChange, handleSubmit, isLoading } = useChat({
    api: "/api/chat",
    body: {
      context: contextData,
    },
  });

  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isLoading]);

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
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 text-white">
              <Sparkles className="h-4 w-4" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-foreground">Ask AI</h2>
              <p className="text-[11px] text-muted-foreground">Powered by your CRM data</p>
            </div>
          </div>
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => onOpenChange(false)}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* Messages */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center space-y-3 text-center opacity-70">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted/50">
                <Sparkles className="h-6 w-6 text-muted-foreground" />
              </div>
              <p className="text-sm text-muted-foreground max-w-[250px]">
                Ask me anything about your current pipeline, leads, or deals.
              </p>
            </div>
          ) : (
            messages.map((m: UIMessage) => (
              <div key={m.id} className={cn("flex gap-3", m.role === "user" ? "flex-row-reverse" : "flex-row")}>
                <div className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-full", m.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted border border-border text-foreground")}>
                  {m.role === "user" ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
                </div>
                <div className={cn("rounded-2xl px-4 py-2.5 max-w-[80%] text-sm", m.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted/50 border border-border/50 text-foreground")}>
                  <p className="whitespace-pre-wrap leading-relaxed">{m.content}</p>
                </div>
              </div>
            ))
          )}
          {isLoading && (
            <div className="flex gap-3">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted border border-border text-foreground">
                <Bot className="h-4 w-4" />
              </div>
              <div className="rounded-2xl bg-muted/50 border border-border/50 px-4 py-3 max-w-[80%]">
                <div className="flex gap-1">
                  <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/40 animate-bounce" />
                  <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/40 animate-bounce [animation-delay:0.2s]" />
                  <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/40 animate-bounce [animation-delay:0.4s]" />
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Input */}
        <div className="border-t border-border p-4 bg-card/50 backdrop-blur">
          <form 
            onSubmit={(e) => {
              e.preventDefault();
              if (input.trim()) handleSubmit(e);
            }} 
            className="relative flex items-center"
          >
            <Input
              value={input}
              onChange={handleInputChange}
              placeholder="Ask about your deals..."
              className="pr-12 bg-card rounded-full h-11"
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
