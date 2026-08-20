import logging
import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.limits import limiter
from app.routers import (
    agents,
    auth_google,
    companies,
    contacts,
    dashboard,
    health,
    leads,
    meetings,
    notifications,
    opportunities,
    tasks,
)

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Dracara Growth OS API", version="0.1.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


app.add_middleware(RequestIDMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list or ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth_google.router)
app.include_router(companies.router)
app.include_router(contacts.router)
app.include_router(leads.router)
app.include_router(tasks.router)
app.include_router(meetings.router)
app.include_router(opportunities.router)
app.include_router(dashboard.router)
app.include_router(notifications.router)
app.include_router(agents.router)


@app.get("/")
async def root():
    return {"service": "dracara-growth-os-api", "docs": "/docs"}
