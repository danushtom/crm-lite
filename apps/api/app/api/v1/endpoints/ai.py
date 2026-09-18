"""AI endpoints: the CRM assistant, proposal drafting, and usage reporting.

Every LLM call in the product now enters here or through the worker -- the web app no longer talks
to a model provider at all, and no longer holds an API key. That move is the security fix: the
previous `/api/chat` route in Next.js had no session check and pasted a browser-supplied blob of
CRM data into the system prompt. Here the caller is authenticated, permission-checked, budgeted,
and the assistant reads the CRM itself through the caller's own RLS-scoped connection.

Route ordering: the literal paths below are declared before any `/{id}`-shaped route. This router
has none today, but `voice_agents.py` records what happens when that discipline lapses -- FastAPI
matches in declaration order, and a single-segment wildcard swallows its literal siblings.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Annotated, AsyncIterator

from dracara_ai.errors import AiNotConfiguredError, AiUpstreamError
from dracara_ai.graphs import assistant as assistant_graph
from dracara_ai.usage import UsageRecord
from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import StreamingResponse

from app.api.deps import AdminDbDep, AdminDep, CurrentUserDep, DbDep, ProfileDep, require_permission
from app.core.config import settings
from app.core.errors import NotConfiguredError, UpstreamError
from app.core.rate_limit import limiter
from app.schemas.ai import (
    AiStatus,
    AiUsageEntry,
    AiUsageSummary,
    ChatRequest,
    CompanyProfileOut,
    CompanyResearchOut,
    DealHealthSnapshot,
    FieldSuggestion,
    LeadBriefBody,
    LeadBriefOut,
    ResearchRequest,
    ProposalDraftRequest,
    ProposalDraftResponse,
)
from app.schemas.common import ERROR_RESPONSES
from app.services.ai import assistant_tools, budget, proposal_drafting
from app.services.ai import research as research_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["AI"])


def _require_configured() -> None:
    if not settings.ai_configured:
        raise NotConfiguredError(
            "AI features are not configured. Set AI_ENABLED=true and OPENAI_API_KEY."
        )


@router.get(
    "/status",
    response_model=AiStatus,
    summary="Whether AI features are configured in this deployment",
    responses=ERROR_RESPONSES,
)
async def ai_status(_user: CurrentUserDep) -> AiStatus:
    """Lets the web app hide AI affordances rather than offering buttons that 501."""
    configured = settings.ai_configured
    return AiStatus(
        enabled=settings.ai_enabled,
        configured=configured,
        research_configured=settings.research_configured,
        detail=(
            "AI features are ready."
            if configured
            else "Set AI_ENABLED=true and OPENAI_API_KEY to enable AI features."
        ),
    )


@router.post(
    "/chat",
    summary="Ask the CRM assistant a question (streaming)",
    description=(
        "Server-sent events. Each `data:` frame is `{\"delta\": \"...\"}` with the next piece of "
        "the answer; the stream ends with `data: [DONE]`. The assistant reads the CRM through "
        "the caller's own permissions -- it cannot see anything the caller could not open in the "
        "UI -- and no CRM data is accepted from the request body."
    ),
    responses={
        200: {
            "description": "A text/event-stream of answer fragments",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        },
        **ERROR_RESPONSES,
    },
)
# The app-wide default (300/minute) is sized for CRUD reads. A streamed completion with tool
# calls behind it costs orders of magnitude more, and AI_MONTHLY_TOKEN_BUDGET -- the real
# backstop -- defaults to 0 (disabled), so without this one authenticated session could run up
# an unbounded bill before anyone noticed.
@limiter.limit("20/minute")
async def chat(
    request: Request,
    payload: ChatRequest,
    db: DbDep,
    admin_db: AdminDbDep,
    profile: ProfileDep,
    _perm: Annotated[dict, Depends(require_permission("ai.read"))],
) -> StreamingResponse:
    _require_configured()
    organization_id = profile["organization_id"]
    user_id = profile["id"]

    # Checked before the stream opens: once headers are sent the status code is fixed, and a 429
    # arriving as a mid-stream text frame is not something a client can act on.
    await budget.assert_within_budget(admin_db, organization_id)

    # Bound to `db`, the caller's RLS-scoped client -- never `admin_db`. See assistant_tools.
    tools = assistant_tools.build_tools(db)
    usage = UsageRecord(feature="assistant", model="")

    async def stream() -> AsyncIterator[str]:
        try:
            async for delta in assistant_graph.run_stream(
                messages=[m.model_dump() for m in payload.messages],
                tools=tools,
                usage=usage,
            ):
                yield f"data: {json.dumps({'delta': delta})}\n\n"
        except (AiNotConfiguredError, AiUpstreamError) as exc:
            logger.warning("assistant_stream_failed org_id=%s error=%s", organization_id, exc)
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
        except Exception:
            logger.exception("assistant_stream_crashed org_id=%s", organization_id)
            yield f"data: {json.dumps({'error': 'The assistant failed to answer.'})}\n\n"
        finally:
            # Recorded even on failure: a crash after 3,000 tokens still cost 3,000 tokens.
            await budget.record(
                admin_db, organization_id=organization_id, usage=usage, user_id=user_id
            )
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Without this an nginx or similar in front of the API buffers the whole response and
            # the user watches a spinner instead of a stream.
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/proposals/{opportunity_id}/draft",
    response_model=ProposalDraftResponse,
    summary="Draft a proposal for an opportunity with AI",
    description=(
        "Creates a new **draft** proposal version from the lead's intelligence notes, the "
        "opportunity's requirements and any indexed reference material. Never sends anything; "
        "the draft is for a human to edit."
    ),
    responses=ERROR_RESPONSES,
)
# Tighter still: a draft fans out to one model call per section on the more expensive model.
@limiter.limit("6/minute")
async def draft_proposal(
    request: Request,
    # slowapi writes its rate-limit headers onto this. Without it, a route returning a
    # model (not a Response) raises on every *successful* call -- the limit decorator
    # fails after the work is done.
    response: Response,
    opportunity_id: str,
    payload: ProposalDraftRequest,
    db: DbDep,
    admin_db: AdminDbDep,
    profile: ProfileDep,
    _perm: Annotated[dict, Depends(require_permission("proposals.write"))],
) -> ProposalDraftResponse:
    _require_configured()
    organization_id = profile["organization_id"]
    await budget.assert_within_budget(admin_db, organization_id)

    try:
        draft, opportunity, usage = await proposal_drafting.draft_for_opportunity(
            db, opportunity_id=opportunity_id, organization_id=organization_id
        )
    except AiNotConfiguredError as exc:
        raise NotConfiguredError(str(exc)) from exc
    except AiUpstreamError as exc:
        raise UpstreamError(str(exc)) from exc

    await budget.record(
        admin_db, organization_id=organization_id, usage=usage, user_id=profile["id"]
    )

    quoted_price = payload.quoted_price
    if quoted_price is None and opportunity.get("quoted_value") is not None:
        quoted_price = float(opportunity["quoted_value"])

    proposal = await proposal_drafting.persist_draft(
        db,
        opportunity_id=opportunity_id,
        draft=draft,
        created_by=profile["id"],
        quoted_price=quoted_price,
    )

    return ProposalDraftResponse(
        proposal_id=proposal["id"],
        version=proposal["version"],
        title=draft.title,
        markdown=draft.to_markdown(),
        tokens_used=usage.total_tokens,
    )


@router.get(
    "/usage",
    response_model=AiUsageSummary,
    summary="This organization's AI usage and cost, month to date",
    responses=ERROR_RESPONSES,
)
async def ai_usage(db: DbDep, profile: ProfileDep, _admin: AdminDep) -> AiUsageSummary:
    """Read through the caller's own client: `ai_usage`'s SELECT policy already requires
    `ai.manage` within the organization, so RLS -- not this handler -- is the authority on who
    may see spend. `AdminDep` is the matching application-layer gate."""
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    result = await db.select(
        "ai_usage",
        params={
            "select": "feature,model,prompt_tokens,completion_tokens,total_tokens,cost_usd,created_at",
            "created_at": f"gte.{month_start.isoformat()}",
            "order": "created_at.desc,id.desc",
            "limit": "5000",
        },
    )

    by_feature: dict[tuple[str, str], dict[str, float]] = {}
    total_tokens = 0
    total_cost = 0.0
    for row in result.rows:
        tokens = int(row.get("total_tokens") or 0)
        cost = float(row.get("cost_usd") or 0)
        total_tokens += tokens
        total_cost += cost
        key = (row.get("feature") or "unknown", row.get("model") or "unknown")
        bucket = by_feature.setdefault(key, {"tokens": 0.0, "cost": 0.0})
        bucket["tokens"] += tokens
        bucket["cost"] += cost

    entries = [
        AiUsageEntry(
            feature=feature,
            model=model,
            total_tokens=int(data["tokens"]),
            cost_usd=round(data["cost"], 6),
        )
        for (feature, model), data in sorted(by_feature.items(), key=lambda kv: -kv[1]["tokens"])
    ]

    limit = settings.ai_monthly_token_budget
    return AiUsageSummary(
        month_start=month_start,
        total_tokens=total_tokens,
        total_cost_usd=round(total_cost, 6),
        monthly_token_budget=limit,
        budget_remaining=max(0, limit - total_tokens) if limit > 0 else None,
        by_feature=entries,
    )


@router.get(
    "/deal-health",
    response_model=list[DealHealthSnapshot],
    summary="Opportunities the nightly deal-health pass flagged",
    description=(
        "Most recent snapshot per opportunity, highest risk first. Visibility follows the "
        "opportunity itself (RLS), so a rep sees their own deals and a full-access role sees "
        "every deal in the organization."
    ),
    responses=ERROR_RESPONSES,
)
async def deal_health(
    db: DbDep,
    _perm: Annotated[dict, Depends(require_permission("opportunities.read"))],
    risk: Annotated[str | None, Query(description="Filter to one level: low, medium or high")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[DealHealthSnapshot]:
    params: dict[str, str] = {
        "select": "opportunity_id,risk_level,reasons,suggested_action,assessed_by_model,"
        "generated_at,opportunities(title,leads(companies(name)))",
        "order": "generated_at.desc,id.desc",
        "limit": str(limit),
    }
    if risk in ("low", "medium", "high"):
        params["risk_level"] = f"eq.{risk}"

    result = await db.select("deal_health_snapshots", params=params)

    # One row per opportunity: the table keeps a snapshot per day, and a reader wants today's
    # verdict, not a history. Ordered newest-first above, so the first sighting is the current one.
    seen: set[str] = set()
    snapshots: list[DealHealthSnapshot] = []
    for row in result.rows:
        opportunity_id = row.get("opportunity_id")
        if not opportunity_id or opportunity_id in seen:
            continue
        seen.add(opportunity_id)

        opportunity = row.get("opportunities") or {}
        lead = (opportunity.get("leads") or {}) if isinstance(opportunity, dict) else {}
        company = (lead.get("companies") or {}) if isinstance(lead, dict) else {}
        snapshots.append(
            DealHealthSnapshot(
                opportunity_id=opportunity_id,
                opportunity_title=opportunity.get("title") if isinstance(opportunity, dict) else None,
                company_name=company.get("name") if isinstance(company, dict) else None,
                risk_level=row.get("risk_level") or "low",
                reasons=row.get("reasons") or [],
                suggested_action=row.get("suggested_action"),
                assessed_by_model=bool(row.get("assessed_by_model")),
                generated_at=row.get("generated_at"),
            )
        )

    order = {"high": 0, "medium": 1, "low": 2}
    snapshots.sort(key=lambda s: order.get(s.risk_level, 3))
    return snapshots



# --- Company research and pre-call briefs ---------------------------------------------------
#
# Every route below first reads the company or lead through `db`, the caller's RLS-scoped
# client, so a record the caller cannot see is a 404 before anything is searched or billed.
# See app/services/ai/research.py for what is (and is not) sent to the search provider.


def _require_research_configured() -> None:
    if not settings.research_configured:
        raise NotConfiguredError(
            "Web research is not configured. Set AI_ENABLED=true, OPENAI_API_KEY and EXA_API_KEY."
        )


def _research_out(company: dict, row: dict, *, from_cache: bool) -> CompanyResearchOut:
    from dracara_ai.graphs.research import CompanyProfile

    profile = CompanyProfile.model_validate(row["profile"])
    return CompanyResearchOut(
        research_id=row["id"],
        company_id=company["id"],
        company_version=int(company.get("version") or 1),
        profile=CompanyProfileOut.model_validate(profile.model_dump()),
        suggestions=[FieldSuggestion(**s) for s in research_service.suggestions(company, profile)],
        researched_at=row.get("created_at"),
        from_cache=from_cache,
    )


@router.post(
    "/companies/{company_id}/research",
    response_model=CompanyResearchOut,
    summary="Research a company from the public web",
    description=(
        "Searches the web using only the company's name and website, and returns a cited profile "
        "plus suggested edits. Writes nothing to the company itself. Recent research is served "
        "from storage unless `force` is set."
    ),
    responses=ERROR_RESPONSES,
)
@limiter.limit("10/minute")
async def research_company(
    request: Request,
    # slowapi writes its rate-limit headers onto this. Without it, a route returning a
    # model (not a Response) raises on every *successful* call -- the limit decorator
    # fails after the work is done.
    response: Response,
    company_id: str,
    payload: ResearchRequest,
    db: DbDep,
    admin_db: AdminDbDep,
    profile: ProfileDep,
    _perm: Annotated[dict, Depends(require_permission("ai.read"))],
) -> CompanyResearchOut:
    _require_research_configured()
    organization_id = profile["organization_id"]
    await budget.assert_within_budget(admin_db, organization_id)

    try:
        company, row, usage = await research_service.research_company(
            db, admin_db, company_id=company_id, requested_by=profile["id"], force=payload.force
        )
    except AiNotConfiguredError as exc:
        raise NotConfiguredError(str(exc)) from exc
    except AiUpstreamError as exc:
        raise UpstreamError(str(exc)) from exc

    if usage is not None:
        await budget.record(admin_db, organization_id=organization_id, usage=usage, user_id=profile["id"])
    return _research_out(company, row, from_cache=usage is None)


@router.get(
    "/companies/{company_id}/research",
    response_model=CompanyResearchOut | None,
    summary="The most recent research for a company, if any",
    responses=ERROR_RESPONSES,
)
async def get_company_research(
    company_id: str,
    db: DbDep,
    _perm: Annotated[dict, Depends(require_permission("ai.read"))],
) -> CompanyResearchOut | None:
    company = await research_service._visible_company(db, company_id)
    row = await research_service.latest_research(db, company_id)
    return _research_out(company, row, from_cache=True) if row else None


@router.post(
    "/leads/{lead_id}/brief",
    response_model=LeadBriefOut,
    summary="Write a pre-call brief for a lead",
    description=(
        "Combines the lead's CRM facts with public research on its company. CRM facts are sent "
        "to the model provider only; the search provider only ever sees the company's name and "
        "website."
    ),
    responses=ERROR_RESPONSES,
)
@limiter.limit("10/minute")
async def brief_lead(
    request: Request,
    # slowapi writes its rate-limit headers onto this. Without it, a route returning a
    # model (not a Response) raises on every *successful* call -- the limit decorator
    # fails after the work is done.
    response: Response,
    lead_id: str,
    db: DbDep,
    admin_db: AdminDbDep,
    profile: ProfileDep,
    _perm: Annotated[dict, Depends(require_permission("ai.read"))],
) -> LeadBriefOut:
    _require_research_configured()
    organization_id = profile["organization_id"]
    await budget.assert_within_budget(admin_db, organization_id)

    try:
        row, usages = await research_service.brief_lead(
            db, admin_db, lead_id=lead_id, requested_by=profile["id"]
        )
    except AiNotConfiguredError as exc:
        raise NotConfiguredError(str(exc)) from exc
    except AiUpstreamError as exc:
        raise UpstreamError(str(exc)) from exc

    for usage in usages:
        await budget.record(admin_db, organization_id=organization_id, usage=usage, user_id=profile["id"])
    return LeadBriefOut(
        brief_id=row["id"],
        lead_id=lead_id,
        brief=LeadBriefBody.model_validate(row["brief"]),
        research_id=row.get("research_id"),
        created_at=row.get("created_at"),
    )


@router.get(
    "/leads/{lead_id}/brief",
    response_model=LeadBriefOut | None,
    summary="The most recent pre-call brief for a lead, if any",
    responses=ERROR_RESPONSES,
)
async def get_lead_brief(
    lead_id: str,
    db: DbDep,
    _perm: Annotated[dict, Depends(require_permission("ai.read"))],
) -> LeadBriefOut | None:
    row = await research_service.latest_brief(db, lead_id)
    if row is None:
        return None
    return LeadBriefOut(
        brief_id=row["id"],
        lead_id=lead_id,
        brief=LeadBriefBody.model_validate(row["brief"]),
        research_id=row.get("research_id"),
        created_at=row.get("created_at"),
    )
