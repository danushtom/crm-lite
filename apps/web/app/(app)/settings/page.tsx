export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-semibold tracking-tight">Settings</h1>
      <div className="rounded-xl border border-border bg-card p-6 text-sm">
        <h2 className="font-semibold">Google Calendar</h2>
        <p className="mt-2 text-muted-foreground">
          OAuth token exchange is handled by the FastAPI route <code className="rounded bg-muted px-1 py-0.5 text-xs">POST /auth/google</code>{" "}
          once <code className="rounded bg-muted px-1 py-0.5 text-xs">GOOGLE_CLIENT_ID</code> and related variables are set.
        </p>
      </div>
    </div>
  );
}
