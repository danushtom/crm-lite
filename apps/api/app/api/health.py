"""Operational probes.

Deliberately unversioned and mounted at the root: orchestrators and load balancers address a
fixed path, and probe URLs should not move when the API version does.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Response, status

from app.core.config import settings
from app.core.rate_limit import limiter
from app.db.supabase import get_http_client
from app.schemas.dashboard import HealthStatus, LivenessStatus, ReadinessStatus

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"], include_in_schema=True)


@router.get("/health", response_model=HealthStatus, summary="Basic health check")
@limiter.exempt
async def health() -> HealthStatus:
    return HealthStatus(status="ok")


@router.get(
    "/health/live",
    response_model=LivenessStatus,
    summary="Liveness probe",
    description="Returns as long as the process is running; never touches dependencies.",
)
@limiter.exempt
async def live() -> LivenessStatus:
    return LivenessStatus(live=True)


async def _probe(client: httpx.AsyncClient, url: str, headers: dict[str, str] | None = None) -> bool:
    try:
        response = await client.get(url, headers=headers or {}, timeout=5.0)
        return response.status_code < 500
    except Exception as exc:
        logger.warning("readiness probe failed url=%s error=%s", url, exc)
        return False


@router.get(
    "/health/ready",
    response_model=ReadinessStatus,
    summary="Readiness probe",
    description=(
        "Verifies configuration and upstream reachability. Token verification requires *either* "
        "the project JWKS (asymmetric ES256/RS256 keys, the current default) *or* "
        "SUPABASE_JWT_SECRET (legacy HS256) -- only one."
    ),
    responses={503: {"model": ReadinessStatus, "description": "Not ready to serve traffic"}},
)
@limiter.exempt
async def ready(response: Response) -> ReadinessStatus:
    missing = []
    if not settings.supabase_url:
        missing.append("SUPABASE_URL")
    if not settings.supabase_anon_key:
        missing.append("SUPABASE_ANON_KEY")
    if missing:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessStatus(ready=False, missing=missing)

    anon_headers = {
        "apikey": settings.supabase_anon_key,
        "Authorization": f"Bearer {settings.supabase_anon_key}",
    }
    client = get_http_client()
    rest_ok = await _probe(client, settings.rest_base_url + "/", anon_headers)
    jwks_ok = await _probe(client, settings.jwks_url, anon_headers)

    has_secret = bool(settings.supabase_jwt_secret.strip())
    can_verify = jwks_ok or has_secret
    ready_now = rest_ok and can_verify

    result = ReadinessStatus(
        ready=ready_now,
        supabase_rest_reachable=rest_ok,
        jwks_reachable=jwks_ok,
        hs256_secret_configured=has_secret,
    )
    if not ready_now:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        if not can_verify:
            result.detail = (
                "No way to verify access tokens: project JWKS is unreachable and "
                "SUPABASE_JWT_SECRET is unset."
            )
        else:
            result.detail = "The Supabase REST endpoint is unreachable."
    return result
