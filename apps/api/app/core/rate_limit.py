"""SlowAPI limiter singleton.

Kept in its own module so routers can import it without a circular dependency on ``app.main``.

**Keying.** Requests are bucketed per access token rather than per client IP -- otherwise every
user behind one NAT or corporate proxy shares a single quota. The token is hashed rather than
used directly so credentials never reach the limiter's storage or any log line.

The default limit is applied by ``SlowAPIMiddleware``, which runs *before* endpoint
dependencies resolve, so ``request.state.user`` is not yet populated at that point. Hashing the
raw bearer token sidesteps that ordering problem entirely: it is available from the header on
the way in, is stable for the life of a session, and cannot be forged into someone else's
bucket without holding their token.
"""

from __future__ import annotations

import hashlib

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.core.config import settings

#: Probes must never be throttled -- an orchestrator that gets a 429 will cycle the pod.
EXEMPT_PATHS = frozenset({"/health", "/health/live", "/health/ready"})


def rate_limit_key(request: Request) -> str:
    """Bucket by authenticated session when possible, else by client address."""
    # Set once the auth dependency has run (decorator-scoped limits see this).
    user = getattr(request.state, "user", None)
    if user is not None and getattr(user, "sub", None):
        return f"user:{user.sub}"

    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        if token:
            return "token:" + hashlib.sha256(token.encode("utf-8")).hexdigest()[:32]

    return f"ip:{get_remote_address(request)}"


limiter = Limiter(
    key_func=rate_limit_key,
    default_limits=[settings.rate_limit_default] if settings.rate_limit_enabled else [],
    enabled=settings.rate_limit_enabled,
    headers_enabled=True,
)

# This slowapi build has no `default_limits_exempt_when`, so probe routes opt out
# individually with `@limiter.exempt` (see app/api/health.py).
