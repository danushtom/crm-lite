from datetime import date, timedelta

from fastapi import APIRouter, Depends

from app.deps import SupabaseRest, TokenUser, get_current_user, get_sb

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _unwrap_rpc(rows: object) -> dict:
    """PostgREST wraps RPC returning jsonb as [{dashboard_metrics: {...}}]."""
    if isinstance(rows, list) and rows:
        row = rows[0]
        if isinstance(row, dict) and "dashboard_metrics" in row:
            return row["dashboard_metrics"]
        return row  # type: ignore[return-value]
    if isinstance(rows, dict):
        return rows.get("dashboard_metrics") or rows  # type: ignore[return-value]
    return {}


@router.get("")
async def dashboard(sb: SupabaseRest = Depends(get_sb)):
    rows = await sb.request("POST", "/rpc/dashboard_metrics", json_body={}, prefer="return=representation")
    data = _unwrap_rpc(rows)
    # Normalize hot_leads json array to plain list for JSON clients
    hot = data.get("hot_leads_needing_action")
    if isinstance(hot, list):
        data["hot_leads_needing_action"] = [str(x) for x in hot]
    return data


@router.get("/followups")
async def dashboard_followups(
    sb: SupabaseRest = Depends(get_sb),
    user: TokenUser = Depends(get_current_user),
):
    tasks_raw = await sb.request(
        "GET",
        "/tasks",
        params={
            "select": "*",
            "owner_id": f"eq.{user.sub}",
            "order": "due_date.asc",
        },
    )
    today = date.today().isoformat()
    return {
        "today": [t for t in tasks_raw if t.get("due_date") == today],
        "overdue": [
            t
            for t in tasks_raw
            if t.get("due_date") and str(t["due_date"]) < today and t.get("status") == "pending"
        ],
        "upcoming": [
            t
            for t in tasks_raw
            if t.get("due_date")
            and today <= str(t["due_date"]) <= (date.today() + timedelta(days=14)).isoformat()
        ],
    }
