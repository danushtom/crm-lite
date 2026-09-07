import { KanbanBoard } from "@/components/pipeline/kanban-board";
import { OpportunitiesToolbar } from "@/components/pipeline/opportunities-toolbar";
import { OpportunitiesList } from "@/components/pipeline/opportunities-list";
import { OpportunitiesTimeline } from "@/components/pipeline/opportunities-timeline";

export default async function OpportunitiesBoardPage({
  searchParams,
}: {
  searchParams: Promise<{ view?: string }>;
}) {
  const resolvedSearchParams = await searchParams;
  const view = resolvedSearchParams.view === "list" || resolvedSearchParams.view === "timeline" ? resolvedSearchParams.view : "kanban";

  return (
    <div className="-mt-1 space-y-3">
      <OpportunitiesToolbar viewMode={view} />
      {view === "kanban" && <KanbanBoard />}
      {view === "list" && <OpportunitiesList />}
      {view === "timeline" && <OpportunitiesTimeline />}
    </div>
  );
}
