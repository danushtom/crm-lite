"""Aggregates every v1 endpoint module into one mountable router.

Adding a resource means creating a module under ``endpoints/`` and registering it here --
``main.py`` never changes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import plan_gate
from app.services.billing import FEATURE_AI, FEATURE_VOICE_AGENTS

from app.api.v1.endpoints import (
    agents,
    ai,
    auth,
    billing,
    billing_webhooks,
    bulk,
    companies,
    contacts,
    dashboard,
    imports,
    lead_capture,
    leads,
    meetings,
    notifications,
    opportunities,
    organizations,
    proposals,
    recently_deleted,
    roles,
    tasks,
    voice_agents,
    voice_webhooks,
)

api_router = APIRouter()

#: Writes on these routers need a plan in good standing (trial or paid); reads never do -- a
#: lapsed organization is read-only, not locked out. Left ungated on purpose: auth (your own
#: profile), organizations and billing (an admin must be able to pay from a lapsed workspace),
#: notifications (marking one read), lead capture (inbound leads are not lost while an
#: organization sorts out payment) and both webhook receivers.
_writable = [Depends(plan_gate())]

# Order determines the grouping shown in the generated documentation.
api_router.include_router(auth.router)
api_router.include_router(dashboard.router, dependencies=_writable)
api_router.include_router(leads.router, dependencies=_writable)
api_router.include_router(lead_capture.router)
api_router.include_router(opportunities.router, dependencies=_writable)
api_router.include_router(proposals.router, dependencies=_writable)
api_router.include_router(companies.router, dependencies=_writable)
api_router.include_router(contacts.router, dependencies=_writable)
api_router.include_router(tasks.router, dependencies=_writable)
api_router.include_router(meetings.router, dependencies=_writable)
api_router.include_router(imports.router, dependencies=_writable)
api_router.include_router(recently_deleted.router, dependencies=_writable)
api_router.include_router(bulk.router, dependencies=_writable)
api_router.include_router(notifications.router)
api_router.include_router(roles.router, dependencies=_writable)
api_router.include_router(agents.router, dependencies=_writable)
api_router.include_router(organizations.router)
api_router.include_router(billing.router)
api_router.include_router(ai.router, dependencies=[Depends(plan_gate(FEATURE_AI))])
api_router.include_router(
    voice_agents.router, dependencies=[Depends(plan_gate(FEATURE_VOICE_AGENTS))]
)
api_router.include_router(voice_webhooks.router)
api_router.include_router(billing_webhooks.router)
