"""Deal health: is this opportunity stalling, and what should the owner do about it?

    compute_signals -> (conditional) -> assess -> recommend
                    \\-> END when the deal is plainly healthy

The conditional edge is the point of using a graph here. This runs nightly across every open
opportunity in every organization, and most deals on most nights are fine: touched this week, no
overdue tasks, moved stage recently. ``compute_signals`` decides that in pure Python for free, and
only the deals with an actual risk signal reach a model. Without that gate the job's cost scales
with total pipeline size instead of with the number of deals worth looking at.

Pure, per this package's rule: the caller supplies already-gathered data and persists the result
(see ``apps/worker/worker_app.py::deal_health``).
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from ..client import complete_json
from ..config import ai_settings
from ..prompts import DEAL_HEALTH
from ..usage import UsageRecord

logger = logging.getLogger(__name__)

RiskLevel = Literal["low", "medium", "high"]

#: Thresholds that decide whether a deal is worth a model call. Tuned to be generous -- a false
#: "worth looking at" costs a fraction of a cent, a false "healthy" hides a dying deal.
STALE_ACTIVITY_DAYS = 10
STALE_STAGE_DAYS = 21
LOW_SCORE = 40


class DealInput(BaseModel):
    """One opportunity, as gathered by the caller."""

    opportunity_id: str
    stage: str
    estimated_value: float | None = None
    currency: str = "INR"
    days_in_stage: int = 0
    days_since_last_activity: int | None = None
    overdue_task_count: int = 0
    open_task_count: int = 0
    score: float | None = None
    recent_activity: list[str] = Field(default_factory=list)
    company_name: str | None = None


class DealHealth(BaseModel):
    """What the caller writes to ``deal_health_snapshots``."""

    opportunity_id: str
    risk_level: RiskLevel
    reasons: list[str] = Field(default_factory=list)
    suggested_action: str = ""
    #: True when the verdict came from the deterministic gate rather than a model call. Useful
    #: when reading a snapshot back: a gated "low" means "nothing looked wrong", not "a model
    #: considered this deal and cleared it".
    assessed_by_model: bool = False


class _Assessment(BaseModel):
    risk_level: RiskLevel
    reasons: list[str] = Field(
        description="Each reason must cite a specific signal from the data provided"
    )


class _Recommendation(BaseModel):
    suggested_action: str = Field(description="One specific intervention for this week")


def _merge(left: Any, right: Any) -> Any:
    return right if right is not None else left


class DealHealthState(TypedDict, total=False):
    deal: DealInput
    signals: Annotated[list[str] | None, _merge]
    assessment: Annotated[_Assessment | None, _merge]
    recommendation: Annotated[_Recommendation | None, _merge]
    usage: UsageRecord


def _render(deal: DealInput) -> str:
    activity = "\n".join(f"- {a}" for a in deal.recent_activity[:10]) or "(none recorded)"
    last_touch = (
        f"{deal.days_since_last_activity} days ago"
        if deal.days_since_last_activity is not None
        else "never"
    )
    value = f"{deal.estimated_value:,.0f} {deal.currency}" if deal.estimated_value else "not set"
    return (
        f"Company: {deal.company_name or 'unknown'}\n"
        f"Stage: {deal.stage} (for {deal.days_in_stage} days)\n"
        f"Estimated value: {value}\n"
        f"Weighted score: {deal.score if deal.score is not None else 'not scored'}\n"
        f"Last activity: {last_touch}\n"
        f"Open tasks: {deal.open_task_count} ({deal.overdue_task_count} overdue)\n"
        f"Recent activity:\n{activity}"
    )


def _compute_signals(state: DealHealthState) -> DealHealthState:
    """Deterministic risk signals. No model call, no cost."""
    deal = state["deal"]
    signals: list[str] = []

    if deal.days_since_last_activity is None:
        signals.append("No activity has ever been logged on this deal")
    elif deal.days_since_last_activity >= STALE_ACTIVITY_DAYS:
        signals.append(f"No contact in {deal.days_since_last_activity} days")

    if deal.days_in_stage >= STALE_STAGE_DAYS:
        signals.append(f"Has not moved stage in {deal.days_in_stage} days")

    if deal.overdue_task_count > 0:
        signals.append(f"{deal.overdue_task_count} overdue follow-up task(s)")

    if deal.score is not None and deal.score < LOW_SCORE:
        signals.append(f"Weighted score is low ({deal.score:.0f})")

    if deal.open_task_count == 0:
        signals.append("No next step is scheduled")

    return {"signals": signals}


def _route(state: DealHealthState) -> str:
    return "assess" if state.get("signals") else END


async def _assess(state: DealHealthState) -> DealHealthState:
    parsed, usage = await complete_json(
        model=ai_settings.openai_chat_model,
        system=DEAL_HEALTH,
        user=(
            f"{_render(state['deal'])}\n\n"
            "Automated checks already flagged:\n"
            + "\n".join(f"- {s}" for s in state["signals"])
        ),
        schema_model=_Assessment,
    )
    state["usage"].add(usage)
    return {"assessment": parsed}


async def _recommend(state: DealHealthState) -> DealHealthState:
    assessment = state["assessment"]
    parsed, usage = await complete_json(
        model=ai_settings.openai_chat_model,
        system=DEAL_HEALTH,
        user=(
            f"{_render(state['deal'])}\n\n"
            f"Assessed risk: {assessment.risk_level}\n"
            f"Because:\n" + "\n".join(f"- {r}" for r in assessment.reasons) + "\n\n"
            "Give the owner one specific intervention they can carry out this week."
        ),
        schema_model=_Recommendation,
    )
    state["usage"].add(usage)
    return {"recommendation": parsed}


def build_graph():
    graph = StateGraph(DealHealthState)
    graph.add_node("compute_signals", _compute_signals)
    graph.add_node("assess", _assess)
    graph.add_node("recommend", _recommend)
    graph.add_edge(START, "compute_signals")
    graph.add_conditional_edges("compute_signals", _route, {"assess": "assess", END: END})
    graph.add_edge("assess", "recommend")
    graph.add_edge("recommend", END)
    return graph.compile()


_GRAPH = None


def _graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


async def run(deal: DealInput) -> tuple[DealHealth, UsageRecord]:
    """Assess one opportunity. Cheap deals never reach a model -- see the module docstring."""
    usage = UsageRecord(feature="deal_health", model=ai_settings.openai_chat_model)
    final = await _graph().ainvoke({"deal": deal, "usage": usage})

    assessment: _Assessment | None = final.get("assessment")
    if assessment is None:
        return (
            DealHealth(
                opportunity_id=deal.opportunity_id,
                risk_level="low",
                reasons=["No stall signals: recent contact, on schedule, next step booked"],
                suggested_action="",
                assessed_by_model=False,
            ),
            usage,
        )

    recommendation: _Recommendation | None = final.get("recommendation")
    return (
        DealHealth(
            opportunity_id=deal.opportunity_id,
            risk_level=assessment.risk_level,
            reasons=assessment.reasons,
            suggested_action=recommendation.suggested_action if recommendation else "",
            assessed_by_model=True,
        ),
        usage,
    )
