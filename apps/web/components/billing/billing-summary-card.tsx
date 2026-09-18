"use client";

import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Skeleton } from "@dracara/ui";
import { CreditCard } from "lucide-react";
import Link from "next/link";
import { useBilling } from "@/lib/billing";
import { planLabel } from "@/components/billing/plan-labels";

/** The Settings page's entry point to /settings/billing. */
export function BillingSummaryCard() {
  const { data, isLoading } = useBilling();

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div>
          <CardTitle className="text-base">Plan &amp; billing</CardTitle>
          <CardDescription>Your plan, seats, invoices and payment method.</CardDescription>
        </div>
        <CreditCard className="h-5 w-5 text-muted-foreground" aria-hidden />
      </CardHeader>
      <CardContent className="flex flex-wrap items-center justify-between gap-3">
        {isLoading || !data ? (
          <Skeleton className="h-6 w-48" />
        ) : (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <Badge variant="outline">{planLabel(data)}</Badge>
            <span className="text-muted-foreground">
              {data.seats_used} of {data.seat_limit} seats in use
            </span>
          </div>
        )}
        <Button asChild variant="outline" size="sm">
          <Link href="/settings/billing">Manage billing</Link>
        </Button>
      </CardContent>
    </Card>
  );
}
