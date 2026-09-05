"""Agent (team) management endpoints. Admin-only."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Request, Response, status

from app.api.deps import AdminDbDep, AdminDep, DbDep
from app.core.config import settings
from app.core.errors import UpstreamError
from app.core.pagination import Page, PageParamsDep
from app.core.concurrency import IfMatchDep, set_etag, update_guarded
from app.core.rate_limit import limiter
from app.db.supabase import get_http_client
from app.schemas.agents import Agent, AgentInvite, AgentInviteResult, AgentPerformance, AgentUpdate
from app.schemas.common import ERROR_RESPONSES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["Agents"])

_AGENT_SELECT = "*,roles(name)"


def _agent_from_row(row: dict[str, Any]) -> Agent:
    role_name = (row.get("roles") or {}).get("name", "")
    return Agent.model_validate({**row, "role_name": role_name})


@router.get(
    "",
    response_model=Page[Agent],
    summary="List agents",
    description="Requires a role with full organization access.",
    responses=ERROR_RESPONSES,
)
async def list_agents(db: DbDep, page: PageParamsDep, _admin: AdminDep) -> Page[Agent]:
    result = await db.select(
        "users",
        params={
            "select": _AGENT_SELECT,
            "order": "created_at.desc,id.desc",
            "limit": str(page.limit),
            "offset": str(page.offset),
        },
        count=True,
    )
    return Page.build([_agent_from_row(u) for u in result.rows], page, result.count)


@router.post(
    "/invite",
    response_model=AgentInviteResult,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Invite an agent by email",
    description=(
        "Sends a Supabase Auth invitation. Requires a role with full organization access and "
        "a configured service-role key. Returns 202: the invitation is dispatched "
        "asynchronously by Supabase."
    ),
    responses=ERROR_RESPONSES,
)
@limiter.limit("10/minute")
async def invite_agent(
    request: Request,
    body: AgentInvite,
    admin_db: AdminDbDep,
    _admin: AdminDep,
) -> AgentInviteResult:
    # admin_db's own construction (get_admin_db -> SupabaseAdminClient()) already raises
    # ServiceUnavailableError when the service-role key is missing, before this body runs --
    # no separate check needed here.

    # A single-use, expiring, email-pinned token -- not the organization id or role
    # themselves -- is what goes into the invitee's signup metadata. handle_new_user()
    # redeems it. Metadata on a public signup call is client-settable, so the organization
    # and role a new user ends up with must never be read directly from it.
    invite_result = await admin_db.insert(
        "org_invites",
        {
            "organization_id": _admin["organization_id"],
            "email": str(body.email),
            "role_id": body.role_id,
            "created_by": _admin["id"],
        },
    )
    invite_token = invite_result.one("Invite")["id"]

    client = get_http_client()
    try:
        response = await client.post(
            f"{settings.auth_base_url}/invite",
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
                "Content-Type": "application/json",
            },
            json={
                "email": str(body.email),
                "data": {
                    "full_name": body.full_name or "",
                    "invite_token": str(invite_token),
                },
            },
        )
    except httpx.HTTPError as exc:
        await admin_db.delete("org_invites", {"id": f"eq.{invite_token}"})
        raise UpstreamError("Could not reach the authentication service") from exc

    if response.status_code >= 400:
        logger.error("agent_invite_failed status=%s body=%s", response.status_code, response.text)
        # The token was never sent anywhere -- don't leave a redeemable, unconsumed invite
        # sitting around for its full 7-day expiry.
        await admin_db.delete("org_invites", {"id": f"eq.{invite_token}"})
        raise UpstreamError("The authentication service rejected the invitation")

    payload = response.json() if response.content else {}
    return AgentInviteResult(
        id=payload.get("id"),
        email=str(body.email),
        role_id=body.role_id,
        invited_at=payload.get("invited_at") or payload.get("created_at"),
    )


@router.get(
    "/{agent_id}/performance",
    response_model=AgentPerformance,
    summary="Agent performance rollup",
    description="Requires a role with full organization access. Counts are computed upstream, not by fetching rows.",
    responses=ERROR_RESPONSES,
)
async def agent_performance(agent_id: str, db: DbDep, _admin: AdminDep) -> AgentPerformance:
    async def count(table: str, params: dict[str, str]) -> int:
        result = await db.select(
            table, params={**params, "select": "id", "limit": "1"}, count=True
        )
        return result.count or 0

    assigned = await count("leads", {"owner_id": f"eq.{agent_id}"})
    wins = await count("leads", {"owner_id": f"eq.{agent_id}", "stage": "eq.won"})
    stage_moves = await count(
        "activities", {"performed_by": f"eq.{agent_id}", "type": "eq.stage_change"}
    )
    meetings = await count("meetings", {"owner_id": f"eq.{agent_id}"})

    return AgentPerformance(
        agent_id=agent_id,
        assigned_leads=assigned,
        stage_moves_logged=stage_moves,
        meetings_count=meetings,
        wins=wins,
        win_rate=round(wins / assigned, 4) if assigned else 0.0,
    )


@router.get(
    "/{agent_id}",
    response_model=Agent,
    summary="Get an agent",
    description="Requires a role with full organization access.",
    responses=ERROR_RESPONSES,
)
async def get_agent(agent_id: str, db: DbDep, response: Response, _admin: AdminDep) -> Agent:
    result = await db.select("users", params={"select": _AGENT_SELECT, "id": f"eq.{agent_id}"})
    row = result.one("Agent")
    set_etag(response, row)
    return _agent_from_row(row)


@router.patch(
    "/{agent_id}",
    response_model=Agent,
    summary="Change an agent's role, name, timezone or access",
    description=(
        "Requires a role with full organization access. The database refuses to demote or "
        "deactivate the organization's last full-access user, so it cannot lock itself out."
    ),
    responses=ERROR_RESPONSES,
)
async def update_agent(
    agent_id: str,
    body: AgentUpdate,
    db: DbDep,
    response: Response,
    if_match: IfMatchDep,
    _admin: AdminDep,
) -> Agent:
    changes = AgentUpdate.model_validate(body.changes()).model_dump(
        exclude_unset=True, mode="json"
    )
    if not changes:
        return await get_agent(agent_id, db, response, _admin)

    row = await update_guarded(
        db,
        "users",
        record_id=agent_id,
        changes=changes,
        if_match=if_match,
        what="Agent",
        select=_AGENT_SELECT,
    )
    set_etag(response, row)
    return _agent_from_row(row)
