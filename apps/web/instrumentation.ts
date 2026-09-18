import * as Sentry from "@sentry/nextjs";

/**
 * Server and edge (middleware) error monitoring. Inert unless NEXT_PUBLIC_SENTRY_DSN is set.
 * sendDefaultPii stays off: no cookies, IPs or headers -- the Supabase session lives in cookies.
 */
export function register() {
  const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
  if (!dsn) return;
  Sentry.init({
    dsn,
    environment: process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT ?? process.env.NODE_ENV,
    sendDefaultPii: false,
    tracesSampleRate: 0,
  });
}

export const onRequestError = Sentry.captureRequestError;
