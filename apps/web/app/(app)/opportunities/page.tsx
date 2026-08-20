import { KanbanBoard } from "@/components/pipeline/kanban-board";
import { OpportunitiesToolbar } from "@/components/pipeline/opportunities-toolbar";

export default function OpportunitiesBoardPage() {
  return (
    <div className="-mt-1 space-y-3">
      <OpportunitiesToolbar />
      <KanbanBoard />
    </div>
  );
}
