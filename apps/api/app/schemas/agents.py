"""Agent (team member) schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import EmailStr, Field

from app.schemas.common import APIModel, PatchModel, StrictAPIModel


class Agent(APIModel):
    id: str
    email: str
    full_name: str = ""
    role_id: str
    role_name: str = Field(description="Denormalized from the role for display; not writable here.")
    avatar_url: str | None = None
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AgentInvite(StrictAPIModel):
    email: EmailStr
    full_name: str | None = Field(default=None, max_length=200)
    role_id: str = Field(description="One of the organization's roles -- see GET /roles.")


class AgentInviteResult(APIModel):
    id: str | None = None
    email: str
    role_id: str
    invited_at: datetime | None = None


class AgentPerformance(APIModel):
    """Per-agent activity rollup (tdd.md 5.6)."""

    agent_id: str
    assigned_leads: int = Field(description="Leads currently owned by this agent.")
    stage_moves_logged: int = Field(description="Stage-change activities attributed to this agent.")
    meetings_count: int
    wins: int = Field(description="Owned leads currently in the 'won' stage.")
    win_rate: float = Field(description="wins / assigned_leads, 0 when the agent owns no leads.")


class AgentUpdate(PatchModel):
    """Admin-only changes to a team member.

    Role changes and deactivation are guarded in the database: a non-admin cannot change
    anyone's role, and the organization's last active full-access user cannot be demoted or
    switched off.
    """

    full_name: str | None = Field(default=None, max_length=200)
    role_id: str | None = None
    is_active: bool | None = None
    timezone: str | None = Field(
        default=None,
        max_length=64,
        description="IANA zone used for this user's follow-up day boundaries.",
    )
