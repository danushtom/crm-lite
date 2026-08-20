import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@dracara/ui";

export default function ReportsPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-semibold tracking-tight">Reports</h1>
      <Card>
        <CardHeader>
          <CardTitle>Pipeline analytics</CardTitle>
          <CardDescription>Funnel and win/loss rollups mirror dashboard aggregates.</CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Use <span className="font-medium text-foreground">/reports</span> for deeper slices — charts above reuse{" "}
          <code className="rounded bg-muted px-1 py-0.5 text-xs">GET /dashboard</code> data from the API.
        </CardContent>
      </Card>
    </div>
  );
}
