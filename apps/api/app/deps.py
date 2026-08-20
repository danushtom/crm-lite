from __future__ import annotations

import json
from typing import Any

import httpx
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

security = HTTPBearer()


class TokenUser:
    __slots__ = ("sub", "email")

    def __init__(self, sub: str, email: str | None = None):
        self.sub = sub
        self.email = email


class SupabaseRest:
    def __init__(self, jwt_token: str):
        self._jwt_token = jwt_token
        self._base = settings.supabase_url.rstrip("/") + "/rest/v1"
        self._headers = {
            "apikey": settings.supabase_anon_key,
            "Authorization": f"Bearer {jwt_token}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json_body: Any = None,
        prefer: str | None = None,
    ) -> Any:
        headers = {**self._headers}
        if prefer:
            headers["Prefer"] = prefer
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.request(
                method,
                f"{self._base}{path}",
                params=params,
                content=json.dumps(json_body) if json_body is not None else None,
                headers=headers,
            )
        if r.status_code >= 400:
            detail: Any = r.text
            try:
                detail = r.json()
            except json.JSONDecodeError:
                pass
            raise HTTPException(status_code=r.status_code, detail=detail)
        if r.status_code == 204 or not r.content:
            return None
        ct = r.headers.get("content-type", "")
        if "application/json" in ct:
            return r.json()
        return r.text


def decode_jwt(token: str) -> TokenUser:
    try:
        secret = settings.supabase_jwt_secret.strip()
        if secret:
            payload = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                audience="authenticated",
                options={"require": ["exp", "sub"]},
            )
        else:
            # Dev fallback: allow claim extraction when JWT secret is not configured.
            # Supabase/PostgREST still authorizes requests using the same bearer token.
            payload = jwt.decode(
                token,
                options={"verify_signature": False, "require": ["sub"]},
                algorithms=["HS256", "RS256"],
            )
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}") from e
    sub = payload.get("sub")
    if not sub or not isinstance(sub, str):
        raise HTTPException(status_code=401, detail="Missing subject")
    email = payload.get("email")
    return TokenUser(sub=sub, email=email if isinstance(email, str) else None)


async def get_sb(creds: HTTPAuthorizationCredentials = Depends(security)) -> SupabaseRest:
    decode_jwt(creds.credentials)
    return SupabaseRest(creds.credentials)


async def get_current_user(creds: HTTPAuthorizationCredentials = Depends(security)) -> TokenUser:
    return decode_jwt(creds.credentials)


async def assert_roles(sb: SupabaseRest, user: TokenUser, allowed: set[str]) -> str:
    rows = await sb.request("GET", "/users", params={"select": "role", "id": f"eq.{user.sub}"})
    if not rows:
        raise HTTPException(403, "Profile missing")
    role = rows[0].get("role")
    if role not in allowed:
        raise HTTPException(403, "Insufficient permissions")
    assert isinstance(role, str)
    return role
