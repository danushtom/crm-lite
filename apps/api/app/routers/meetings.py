from datetime import date, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.deps import SupabaseRest, TokenUser, get_current_user, get_sb

router = APIRouter(prefix="/meetings", tags=["meetings"])


class OutcomePatch(BaseModel):
    outcome: str
    outcome_notes: str | None = None
    status: str | None = "completed"


@router.patch("/{meeting_id}/outcome")
async def patch_meeting_outcome(
    meeting_id: str,
    body: OutcomePatch,
    sb: SupabaseRest = Depends(get_sb),
    user: TokenUser = Depends(get_current_user),
):
    meeting_rows = await sb.request(
        "GET",
        "/meetings",
        params={"select": "*", "id": f"eq.{meeting_id}"},
    )
    if not meeting_rows:
        from fastapi import HTTPException

        raise HTTPException(404, "Meeting not found")
    meeting = meeting_rows[0]
    patch = body.model_dump(exclude_none=True)
    rows = await sb.request(
        "PATCH",
        "/meetings",
        params={"id": f"eq.{meeting_id}"},
        json_body=patch,
        prefer="return=representation",
    )
    mtg = rows[0] if isinstance(rows, list) and rows else rows

    # Auto-follow-up task when outcome implies next step (tdd §14.2)
    lead_id = meeting["lead_id"]
    if body.outcome in ("needs_proposal", "followup_later"):
        due = (date.today() + timedelta(days=2)).isoformat()
        await sb.request(
            "POST",
            "/tasks",
            json_body={
                "lead_id": lead_id,
                "owner_id": user.sub,
                "title": f"Follow up after meeting ({body.outcome})",
                "due_date": due,
                "status": "pending",
                "notes": body.outcome_notes,
            },
            prefer="return=representation",
        )

    return mtg
