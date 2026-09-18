"use client";

import * as Sentry from "@sentry/nextjs";
import { Button } from "@dracara/ui";
import { useEffect } from "react";

/** A page inside the app shell threw while rendering: keep the shell, report, offer a retry. */
export default function AppError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return (
    <div className="mx-auto max-w-md py-16 text-center">
      <h1 className="text-lg font-semibold">This page hit an error</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        It has been reported. Try again, or go back and carry on elsewhere.
        {error.digest ? ` Reference: ${error.digest}` : ""}
      </p>
      <Button className="mt-4" onClick={() => reset()}>
        Try again
      </Button>
    </div>
  );
}
