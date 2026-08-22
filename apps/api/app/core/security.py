"""Supabase access-token verification.

Supports both project signing modes:

* **asymmetric** (ES256/RS256) -- the current Supabase default. Public keys are fetched from
  the project JWKS and cached; no shared secret exists or is needed.
* **legacy symmetric** (HS256) -- verified with ``SUPABASE_JWT_SECRET``.

Unverified decoding is never performed. A token whose signature we cannot check is rejected.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

import anyio
import jwt
from jwt import PyJWKClient

from app.core.config import settings
from app.core.errors import ServiceUnavailableError, UnauthorizedError

ASYMMETRIC_ALGS = frozenset({"ES256", "RS256"})
SYMMETRIC_ALGS = frozenset({"HS256"})

_jwk_client: PyJWKClient | None = None
_jwk_lock = threading.Lock()


@dataclass(frozen=True, slots=True)
class TokenUser:
    """Identity claims extracted from a verified access token."""

    sub: str
    email: str | None = None
    role: str | None = None

    @property
    def id(self) -> str:
        return self.sub


def _get_jwk_client() -> PyJWKClient:
    """Lazily build a cached JWKS client for this project's asymmetric signing keys."""
    global _jwk_client
    if _jwk_client is None:
        with _jwk_lock:
            if _jwk_client is None:
                if not settings.supabase_url:
                    raise ServiceUnavailableError("SUPABASE_URL is not configured")
                _jwk_client = PyJWKClient(
                    settings.jwks_url,
                    cache_keys=True,
                    max_cached_keys=8,
                    lifespan=settings.jwks_cache_seconds,
                )
    return _jwk_client


def reset_jwk_client() -> None:
    """Drop the cached JWKS client (used by tests and after key rotation)."""
    global _jwk_client
    with _jwk_lock:
        _jwk_client = None


def _claims_to_user(payload: dict[str, Any]) -> TokenUser:
    sub = payload.get("sub")
    if not sub or not isinstance(sub, str):
        raise UnauthorizedError("Token is missing a subject claim")
    email = payload.get("email")
    role = payload.get("role")
    return TokenUser(
        sub=sub,
        email=email if isinstance(email, str) else None,
        role=role if isinstance(role, str) else None,
    )


def decode_access_token(token: str) -> TokenUser:
    """Verify a Supabase access token and return its identity claims."""
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise UnauthorizedError(f"Malformed token header: {exc}") from exc

    alg = header.get("alg")
    decode_options = {"require": ["exp", "sub"]}

    if alg in ASYMMETRIC_ALGS:
        try:
            signing_key = _get_jwk_client().get_signing_key_from_jwt(token)
        except jwt.PyJWTError as exc:
            raise UnauthorizedError(f"Unknown signing key: {exc}") from exc
        except (ServiceUnavailableError, UnauthorizedError):
            raise
        except Exception as exc:  # JWKS endpoint unreachable
            raise ServiceUnavailableError(f"Unable to fetch signing keys: {exc}") from exc
        key: Any = signing_key.key
        algorithms = sorted(ASYMMETRIC_ALGS)
    elif alg in SYMMETRIC_ALGS:
        secret = settings.supabase_jwt_secret.strip()
        if not secret:
            raise UnauthorizedError(
                "Token is HS256-signed but SUPABASE_JWT_SECRET is not configured. Set it, or "
                "switch the project to asymmetric (ES256) signing keys."
            )
        key = secret
        algorithms = ["HS256"]
    else:
        raise UnauthorizedError(f"Unsupported token algorithm: {alg}")

    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=algorithms,
            audience="authenticated",
            issuer=settings.jwt_issuer,
            options=decode_options,
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Access token has expired") from exc
    except jwt.PyJWTError as exc:
        raise UnauthorizedError(f"Invalid token: {exc}") from exc

    return _claims_to_user(payload)


async def decode_access_token_async(token: str) -> TokenUser:
    """Async wrapper -- JWKS fetches block, so keep them off the event loop."""
    return await anyio.to_thread.run_sync(decode_access_token, token)
