"""Call notes: transcript in, structured follow-up out.

Three nodes rather than one big prompt, because the steps genuinely differ in kind and each one
benefits from seeing the previous step's *conclusion* rather than re-deriving it:

    summarise -> extract_actions -> recommend

``summarise`` reads raw transcript and produces prose plus a sentiment judgement.
``extract_actions`` reads the transcript again but now knows what the call was about, which is
what stops it inventing filler tasks from small talk. ``recommend`` never sees the transcript at
all -- it reasons over the summary and the agreed actions, so its date suggestion follows what was
concluded rather than the last thing that happened to be said.

Pure, per this package's rule: no database handle, no ``organization_id``. The caller writes the
result (see ``apps/worker/worker_app.py::call_notes``).
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from ..client import complete_json
from ..config import ai_settings
from ..prompts import CALL_ACTION_ITEMS, CALL_RECOMMENDATION, CALL_SUMMARY
from ..usage import UsageRecord

logger = logging.getLogger(__name__)

#: A long call can run past the model's context window, and the opening and closing minutes carry
#: almost all of the signal anyway (who they are, what they want; what was agreed).
MAX_TRANSCRIPT_CHARS = 24_000

Sentiment = Literal["positive", "neutral", "negative"]
Priority = Literal["high", "normal", "low"]
Outcome = Literal[
    "interested",
    "not_interested",
    "callback_requested",
    "meeting_booked",
    "no_answer",
    "wrong_number",
    "unclear",
]


# --- Model-facing schemas --------------------------------------------------


class _Summary(BaseModel):
    summary: str = Field(description="Three to five sentences on what happened")
    sentiment: Sentiment
    outcome: Outcome


class ActionItem(BaseModel):
    title: str = Field(description="Short imperative title, e.g. 'Send the revised quote'")
    detail: str | None = Field(default=None, description="One line of context, if useful")
    priority: Priority = "normal"


class _ActionItems(BaseModel):
    action_items: list[ActionItem] = Field(default_factory=list)


class _Recommendation(BaseModel):
    suggested_next_action: str
    suggested_followup_date: str = Field(description="YYYY-MM-DD, never in the past")


# --- Public result ---------------------------------------------------------


class CallNotes(BaseModel):
    """What the caller persists onto the ``calls`` row and its follow-on records."""

    summary: str
    sentiment: Sentiment
    outcome: Outcome
    action_items: list[ActionItem] = Field(default_factory=list)
    suggested_next_action: str = ""
    suggested_followup_date: str | None = None


# --- Graph -----------------------------------------------------------------


def _merge(left: Any, right: Any) -> Any:
    """Last write wins. Nodes here each own distinct keys, so there is nothing to reconcile."""
    return right if right is not None else left


class CallNotesState(TypedDict, total=False):
    transcript: str
    today: str
    duration_seconds: int | None
    summary: Annotated[_Summary | None, _merge]
    actions: Annotated[_ActionItems | None, _merge]
    recommendation: Annotated[_Recommendation | None, _merge]
    usage: UsageRecord


def _truncate(transcript: str) -> str:
    if len(transcript) <= MAX_TRANSCRIPT_CHARS:
        return transcript
    head = MAX_TRANSCRIPT_CHARS * 2 // 3
    tail = MAX_TRANSCRIPT_CHARS - head
    return (
        transcript[:head]
        + "\n\n[... middle of the call omitted for length ...]\n\n"
        + transcript[-tail:]
    )


async def _summarise(state: CallNotesState) -> CallNotesState:
    parsed, usage = await complete_json(
        model=ai_settings.openai_chat_model,
        system=CALL_SUMMARY,
        user=f"Call transcript:\n\n{_truncate(state['transcript'])}",
        schema_model=_Summary,
    )
    state["usage"].add(usage)
    return {"summary": parsed}


async def _extract_actions(state: CallNotesState) -> CallNotesState:
    summary = state["summary"]
    parsed, usage = await complete_json(
        model=ai_settings.openai_chat_model,
        system=CALL_ACTION_ITEMS,
        user=(
            f"Call summary:\n{summary.summary}\n\n"
            f"Sentiment: {summary.sentiment}\nOutcome: {summary.outcome}\n\n"
            f"Transcript:\n\n{_truncate(state['transcript'])}"
        ),
        schema_model=_ActionItems,
    )
    state["usage"].add(usage)
    return {"actions": parsed}


async def _recommend(state: CallNotesState) -> CallNotesState:
    summary = state["summary"]
    actions = state["actions"]
    rendered = (
        "\n".join(f"- [{a.priority}] {a.title}" for a in actions.action_items)
        or "(no actions were agreed)"
    )
    parsed, usage = await complete_json(
        model=ai_settings.openai_chat_model,
        system=CALL_RECOMMENDATION,
        user=(
            f"Today is {state['today']}.\n\n"
            f"Call summary:\n{summary.summary}\n\n"
            f"Sentiment: {summary.sentiment}\nOutcome: {summary.outcome}\n\n"
            f"Agreed actions:\n{rendered}"
        ),
        schema_model=_Recommendation,
    )
    state["usage"].add(usage)
    return {"recommendation": parsed}


def build_graph():
    """Compile the graph. Module-level compilation is deliberate: it is cheap, stateless, and
    shared across every call the process handles."""
    graph = StateGraph(CallNotesState)
    graph.add_node("summarise", _summarise)
    graph.add_node("extract_actions", _extract_actions)
    graph.add_node("recommend", _recommend)
    graph.add_edge(START, "summarise")
    graph.add_edge("summarise", "extract_actions")
    graph.add_edge("extract_actions", "recommend")
    graph.add_edge("recommend", END)
    return graph.compile()


_GRAPH = None


def _graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


def _validate_followup_date(raw: str | None, today: str) -> str | None:
    """A date in the past would create a task that is overdue the moment it is written, so the
    prompt's "never in the past" instruction is enforced here rather than trusted."""
    if not raw:
        return None
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        logger.warning("call_notes_bad_followup_date value=%r", raw)
        return None
    if parsed < date.fromisoformat(today):
        logger.info("call_notes_followup_date_in_past value=%s today=%s", raw, today)
        return today
    return raw


async def run(
    *,
    transcript: str,
    today: str | None = None,
    duration_seconds: int | None = None,
) -> tuple[CallNotes, UsageRecord]:
    """Analyse one call. Returns the notes and what they cost."""
    if not transcript or not transcript.strip():
        raise ValueError("transcript is required")

    today = today or date.today().isoformat()
    usage = UsageRecord(feature="call_notes", model=ai_settings.openai_chat_model)

    final = await _graph().ainvoke(
        {
            "transcript": transcript,
            "today": today,
            "duration_seconds": duration_seconds,
            "usage": usage,
        }
    )

    summary: _Summary = final["summary"]
    actions: _ActionItems = final["actions"]
    recommendation: _Recommendation = final["recommendation"]

    notes = CallNotes(
        summary=summary.summary,
        sentiment=summary.sentiment,
        outcome=summary.outcome,
        action_items=actions.action_items,
        suggested_next_action=recommendation.suggested_next_action,
        suggested_followup_date=_validate_followup_date(
            recommendation.suggested_followup_date, today
        ),
    )
    return notes, usage
