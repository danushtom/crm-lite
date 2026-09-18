"use client";

import * as Sentry from "@sentry/nextjs";
import { useEffect } from "react";

/** Last-resort boundary for errors thrown in the root layout itself. */
export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui, sans-serif", display: "grid", placeItems: "center", minHeight: "100vh" }}>
        <div style={{ textAlign: "center", maxWidth: 420, padding: 16 }}>
          <h1 style={{ fontSize: 20, fontWeight: 600 }}>Something went wrong</h1>
          <p style={{ color: "#6b7280", fontSize: 14 }}>
            The error has been reported. Try again, and if it keeps happening, contact support
            {error.digest ? ` with reference ${error.digest}` : ""}.
          </p>
          <button
            onClick={() => reset()}
            style={{ marginTop: 12, padding: "8px 16px", borderRadius: 8, background: "#0A1128", color: "white", border: 0 }}
          >
            Try again
          </button>
        </div>
      </body>
    </html>
  );
}
