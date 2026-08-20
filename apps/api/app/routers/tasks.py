from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import SupabaseRest, get_sb

router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskPatch(BaseModel):
    status: str | None = None
    due_date: str | None = None
    due_time: str | None = None
    snoozed_until: str | None = None
    outcome_note: str | None = None
    notes: str | None = None


@router.patch("/{task_id}")
async def patch_task(
    task_id: str,
    body: TaskPatch,
    sb: SupabaseRest = Depends(get_sb),
):
    patch = body.model_dump(exclude_none=True)
    if patch.get("status") == "completed":
        patch["completed_at"] = datetime.now(timezone.utc).isoformat()
    rows = await sb.request(
        "PATCH",
        "/tasks",
        params={"id": f"eq.{task_id}"},
        json_body=patch,
        prefer="return=representation",
    )
    return rows[0] if isinstance(rows, list) and rows else rows


@router.get("/{task_id}")
async def get_task(task_id: str, sb: SupabaseRest = Depends(get_sb)):
    rows = await sb.request("GET", "/tasks", params={"select": "*", "id": f"eq.{task_id}"})
    if not rows:
        raise HTTPException(404, "Task not found")
    return rows[0]
