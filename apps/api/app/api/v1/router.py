"""Aggregates every v1 endpoint module into one mountable router.

Adding a resource means creating a module under ``endpoints/`` and registering it here --
``main.py`` never changes.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import (
    agents,
    auth,
    companies,
    contacts,
    dashboard,
    leads,
    meetings,
    notifications,
    opportunities,
    proposals,
    roles,
    tasks,
)

api_router = APIRouter()

# Order determines the grouping shown in the generated documentation.
api_router.include_router(auth.router)
api_router.include_router(dashboard.router)
api_router.include_router(leads.router)
api_router.include_router(opportunities.router)
api_router.include_router(proposals.router)
api_router.include_router(companies.router)
api_router.include_router(contacts.router)
api_router.include_router(tasks.router)
api_router.include_router(meetings.router)
api_router.include_router(notifications.router)
api_router.include_router(roles.router)
api_router.include_router(agents.router)
