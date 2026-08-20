import logging

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/health/live")
async def live():
    return {"live": True}


@router.get("/health/ready")
async def ready():
    """Fails fast when mandatory backend env is missing."""
    missing = []
    if not settings.supabase_url:
        missing.append("SUPABASE_URL")
    if not settings.supabase_anon_key:
        missing.append("SUPABASE_ANON_KEY")
    if not settings.supabase_jwt_secret:
        missing.append("SUPABASE_JWT_SECRET")
    if missing:
        return JSONResponse({"ready": False, "missing": missing}, status_code=503)
    ok_rest = False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{settings.supabase_url.rstrip('/')}/rest/v1/",
                headers={
                    "apikey": settings.supabase_anon_key,
                    "Authorization": f"Bearer {settings.supabase_anon_key}",
                },
            )
            ok_rest = r.status_code < 500
    except Exception as e:
        logger.warning("readiness rest ping failed: %s", e)
        ok_rest = False
    return {"ready": ok_rest, "supabase_rest_reachable": ok_rest}
