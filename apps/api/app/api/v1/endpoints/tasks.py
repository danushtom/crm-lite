"""Task endpoints (tasks are created under a lead; these operate on existing ones)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentUserDep, DbDep
from app.core.concurrency import IfMatchDep, delete_guarded, set_etag, update_guarded
from app.core.pagination import Page, PageParamsDep
from app.domain.enums import TaskStatus
from app.schemas.common import AUTH_RESPONSES, ERROR_RESPONSES
from app.schemas.tasks import Task, TaskUpdate

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.get(
    "",
    response_model=Page[Task],
    summary="List the caller's tasks",
    responses=AUTH_RESPONSES,
)
async def list_tasks(
    db: DbDep,
    user: CurrentUserDep,
    page: PageParamsDep,
    task_status: Annotated[TaskStatus | None, Query(alias="status")] = None,
    lead_id: Annotated[str | None, Query()] = None,
    mine: Annotated[bool, Query(description="Restrict to tasks owned by the caller.")] = True,
) -> Page[Task]:
    params: dict[str, str] = {
        "select": "*",
        "order": "due_at.asc,id.desc",
        "limit": str(page.limit),
        "offset": str(page.offset),
    }
    if mine:
        params["owner_id"] = f"eq.{user.sub}"
    if task_status:
        params["status"] = f"eq.{task_status.value}"
    if lead_id:
        params["lead_id"] = f"eq.{lead_id}"

    result = await db.select("tasks", params=params, count=True)
    return Page.build([Task.model_validate(t) for t in result.rows], page, result.count)


@router.get(
    "/{task_id}",
    response_model=Task,
    summary="Get a task",
    responses=ERROR_RESPONSES,
)
async def get_task(task_id: str, db: DbDep, response: Response) -> Task:
    result = await db.select("tasks", params={"select": "*", "id": f"eq.{task_id}"})
    row = result.one("Task")
    set_etag(response, row)
    return Task.model_validate(row)


@router.patch(
    "/{task_id}",
    response_model=Task,
    summary="Update a task",
    description=(
        "Used to complete, snooze or reschedule. Setting status to 'completed' stamps "
        "completed_at server-side; moving off 'completed' clears it."
    ),
    responses=ERROR_RESPONSES,
)
async def update_task(
    task_id: str,
    body: TaskUpdate,
    db: DbDep,
    response: Response,
    if_match: IfMatchDep,
) -> Task:
    changes = TaskUpdate.model_validate(body.changes()).model_dump(exclude_unset=True, mode="json")
    if not changes:
        return await get_task(task_id, db, response)

    if "status" in changes:
        if changes["status"] == TaskStatus.COMPLETED:
            changes["completed_at"] = datetime.now(timezone.utc).isoformat()
        else:
            # Reopening a task must not leave a stale completion timestamp behind.
            changes["completed_at"] = None

    row = await update_guarded(
        db, "tasks", record_id=task_id, changes=changes, if_match=if_match, what="Task"
    )
    set_etag(response, row)
    return Task.model_validate(row)


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a task",
    description=(
        "Removes the task outright. Tasks are operational rather than part of the deal "
        "record, so there is nothing to retain; to record that one was dealt with, complete "
        "or cancel it instead."
    ),
    responses=ERROR_RESPONSES,
)
async def delete_task(task_id: str, db: DbDep, if_match: IfMatchDep) -> Response:
    await delete_guarded(db, "tasks", record_id=task_id, if_match=if_match, what="Task")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
