"""Agent (team member) schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import EmailStr, Field

from app.domain.enums import UserRole
from app.schemas.common import APIModel, StrictAPIModel


class Agent(APIModel):
    id: str
    email: str
    full_name: str = ""
    role: UserRole = UserRole.AGENT
    avatar_url: str | None = None
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AgentInvite(StrictAPIModel):
    email: EmailStr
    full_name: str | None = Field(default=None, max_length=200)
    role: UserRole = UserRole.AGENT


class AgentInviteResult(APIModel):
    id: str | None = None
    email: str
    role: UserRole
    invited_at: datetime | None = None


class AgentPerformance(APIModel):
    """Per-agent activity rollup (tdd.md 5.6)."""

    agent_id: str
    assigned_leads: int = Field(description="Leads currently owned by this agent.")
    stage_moves_logged: int = Field(description="Stage-change activities attributed to this agent.")
    meetings_count: int
    wins: int = Field(description="Owned leads currently in the 'won' stage.")
    win_rate: float = Field(description="wins / assigned_leads, 0 when the agent owns no leads.")
