"""HMAC signature verification for inbound webhooks from the voice platform.

No Supabase JWT exists for these calls -- the caller is an external service, not a logged-in
user (see app/api/v1/endpoints/voice_webhooks.py, which deliberately declares no auth
dependency). This is the only thing standing between an attacker and forging call/tool-call
events, so a missing or wrong secret must fail closed.
"""

from __future__ import annotations

import hashlib
import hmac

from app.core.config import settings


def verify_platform_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """Vapi-style: HMAC-SHA256 of the raw request body, hex-encoded, against a shared secret
    configured on both sides (VOICE_PLATFORM_WEBHOOK_SECRET / the assistant's serverUrlSecret).
    """
    secret = settings.voice_platform_webhook_secret
    if not secret or not signature_header:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header.strip())
