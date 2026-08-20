export default function CalendarPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-3xl font-semibold tracking-tight">Calendar</h1>
      <p className="text-muted-foreground">
        Google Calendar two-way sync hooks into FastAPI + worker jobs (see Phase 5). Configure{" "}
        <code className="rounded bg-muted px-1 py-0.5 text-xs">GOOGLE_*</code> env vars and connect from Settings.
      </p>
    </div>
  );
}
