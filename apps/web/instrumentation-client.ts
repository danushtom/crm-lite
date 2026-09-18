import * as Sentry from "@sentry/nextjs";

// Browser error monitoring. Inert unless NEXT_PUBLIC_SENTRY_DSN is set. No session replay:
// every screen in this app is customer CRM data.
const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT ?? process.env.NODE_ENV,
    sendDefaultPii: false,
    tracesSampleRate: 0,
  });
}

export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
