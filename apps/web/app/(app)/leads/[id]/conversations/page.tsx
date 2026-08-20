"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@dracara/ui";

export default function ConversationsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">Conversations</h2>
        <p className="mt-1 text-sm text-muted-foreground">Log of all email, LinkedIn, and call discussions.</p>
      </div>

      <Card className="rounded-xl border border-border/70 shadow-[0_1px_3px_rgba(15,23,42,0.06)]">
        <CardContent className="flex flex-col items-center justify-center py-20 text-center">
          <p className="text-sm text-muted-foreground">No conversations recorded yet.</p>
        </CardContent>
      </Card>
    </div>
  );
}
