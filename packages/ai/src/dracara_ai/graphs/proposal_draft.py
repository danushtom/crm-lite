"""Proposal drafting: lead intelligence in, an editable first draft out.

    outline -> draft_sections -> assemble

Split because a single "write me a proposal" prompt reliably produces the same five generic
sections regardless of the deal. Deciding the structure first, from this client's actual stated
problems, then writing each section against that decision, is what makes the draft specific to the
deal rather than to the genre.

``draft_sections`` fans out across sections concurrently -- they do not depend on each other, and a
proposal with six sections would otherwise take six sequential model calls while a founder waits.

Reference material (pricing sheets, past scopes) arrives as pre-retrieved chunks from the caller.
This module never touches Qdrant: retrieval needs an ``organization_id``, and per this package's
rule, resolving a tenant is the caller's job.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from ..client import complete_json
from ..config import ai_settings
from ..prompts import PROPOSAL_OUTLINE, PROPOSAL_SECTIONS
from ..usage import UsageRecord

logger = logging.getLogger(__name__)

#: A proposal longer than this stops being read. The outline prompt is told to be selective; this
#: is the hard stop in case it is not.
MAX_SECTIONS = 7


class ProposalContext(BaseModel):
    """Everything the caller has gathered about the deal."""

    company_name: str | None = None
    project_type: str | None = None
    estimated_value: float | None = None
    currency: str = "INR"
    stage: str | None = None
    #: Free-text panels from ``lead_intelligence`` -- pain points, decision makers, notes.
    intelligence: dict[str, Any] = Field(default_factory=dict)
    requirements: list[str] = Field(default_factory=list)
    #: Text chunks retrieved from the knowledge base by the caller, already tenant-scoped.
    reference_material: list[str] = Field(default_factory=list)


class _PlannedSection(BaseModel):
    heading: str
    must_cover: str = Field(description="What this section has to say for this specific deal")


class _Outline(BaseModel):
    sections: list[_PlannedSection]
    #: A one-line read on the deal, used as the proposal's opening summary.
    positioning: str = ""


class _SectionBody(BaseModel):
    body: str


class ProposalSection(BaseModel):
    heading: str
    body: str


class ProposalDraft(BaseModel):
    """What the caller persists as a new draft proposal version."""

    title: str
    positioning: str = ""
    sections: list[ProposalSection] = Field(default_factory=list)

    def to_markdown(self) -> str:
        parts = [f"# {self.title}"]
        if self.positioning:
            parts.append(self.positioning)
        for section in self.sections:
            parts.append(f"## {section.heading}\n\n{section.body}")
        return "\n\n".join(parts)


def _merge(left: Any, right: Any) -> Any:
    return right if right is not None else left


class ProposalState(TypedDict, total=False):
    context: ProposalContext
    outline: Annotated[_Outline | None, _merge]
    sections: Annotated[list[ProposalSection] | None, _merge]
    usage: UsageRecord


def _render_context(context: ProposalContext) -> str:
    intelligence = (
        "\n".join(f"{k.replace('_', ' ').title()}: {v}" for k, v in context.intelligence.items() if v)
        or "(no intelligence recorded)"
    )
    requirements = "\n".join(f"- {r}" for r in context.requirements) or "(none captured)"
    value = (
        f"{context.estimated_value:,.0f} {context.currency}"
        if context.estimated_value
        else "not set"
    )
    reference = (
        "\n\n---\n\n".join(context.reference_material[:8])
        or "(no reference material available -- use placeholders for pricing and delivery norms)"
    )
    return (
        f"Client: {context.company_name or 'unknown'}\n"
        f"Project type: {context.project_type or 'unspecified'}\n"
        f"Estimated value: {value}\n"
        f"Current stage: {context.stage or 'unspecified'}\n\n"
        f"Lead intelligence:\n{intelligence}\n\n"
        f"Captured requirements:\n{requirements}\n\n"
        f"Agency reference material:\n{reference}"
    )


async def _outline(state: ProposalState) -> ProposalState:
    parsed, usage = await complete_json(
        model=ai_settings.openai_reasoning_model,
        system=PROPOSAL_OUTLINE,
        user=_render_context(state["context"]),
        schema_model=_Outline,
    )
    state["usage"].add(usage)
    parsed.sections = parsed.sections[:MAX_SECTIONS]
    return {"outline": parsed}


async def _draft_sections(state: ProposalState) -> ProposalState:
    context = state["context"]
    outline = state["outline"]
    rendered = _render_context(context)

    async def draft_one(planned: _PlannedSection) -> tuple[ProposalSection, Any]:
        parsed, usage = await complete_json(
            model=ai_settings.openai_reasoning_model,
            system=PROPOSAL_SECTIONS,
            user=(
                f"{rendered}\n\n"
                f"Proposal outline: {', '.join(s.heading for s in outline.sections)}\n\n"
                f"Write the section '{planned.heading}'. It must cover: {planned.must_cover}"
            ),
            schema_model=_SectionBody,
            temperature=0.4,
        )
        return ProposalSection(heading=planned.heading, body=parsed.body), usage

    results = await asyncio.gather(*(draft_one(s) for s in outline.sections))
    for _, usage in results:
        state["usage"].add(usage)
    return {"sections": [section for section, _ in results]}


def _assemble(state: ProposalState) -> ProposalState:
    # Nothing to call a model for -- the node exists so the graph has one explicit place where a
    # future change (a cover page, a T&Cs appendix) belongs.
    return {}


def build_graph():
    graph = StateGraph(ProposalState)
    graph.add_node("outline", _outline)
    graph.add_node("draft_sections", _draft_sections)
    graph.add_node("assemble", _assemble)
    graph.add_edge(START, "outline")
    graph.add_edge("outline", "draft_sections")
    graph.add_edge("draft_sections", "assemble")
    graph.add_edge("assemble", END)
    return graph.compile()


_GRAPH = None


def _graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


async def run(context: ProposalContext) -> tuple[ProposalDraft, UsageRecord]:
    """Draft a proposal. The result is a draft for a human to edit, never something to send."""
    usage = UsageRecord(feature="proposal_draft", model=ai_settings.openai_reasoning_model)
    final = await _graph().ainvoke({"context": context, "usage": usage})

    outline: _Outline = final["outline"]
    company = context.company_name or "Prospective client"
    draft = ProposalDraft(
        title=f"Proposal for {company}",
        positioning=outline.positioning,
        sections=final.get("sections") or [],
    )
    return draft, usage
