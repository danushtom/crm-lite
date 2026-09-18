"""HMAC signature verification for inbound webhooks: the voice platform and the billing provider.

No Supabase JWT exists for these calls -- the caller is an external service, not a logged-in
user (see app/api/v1/endpoints/voice_webhooks.py, which deliberately declares no auth
dependency). This is the only thing standing between an attacker and forging call/tool-call
events, so a missing or wrong secret must fail closed.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import time

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


#: How far a Standard Webhooks timestamp may drift from our clock before the delivery is
#: refused. Bounds how long a captured request stays replayable.
STANDARD_WEBHOOK_TOLERANCE_SECONDS = 5 * 60


def verify_standard_webhook(
    raw_body: bytes,
    *,
    webhook_id: str | None,
    webhook_timestamp: str | None,
    webhook_signature: str | None,
    secret: str,
    now: float | None = None,
) -> bool:
    """Standard Webhooks (https://www.standardwebhooks.com), as Dodo Payments signs them.

    The signed content is ``"{id}.{timestamp}.{body}"``; the key is the base64 part of a
    ``whsec_``-prefixed secret; the header is a space-separated list of ``v1,<base64 sig>``
    entries (several during a secret rotation), any one of which may match. Fails closed on a
    missing secret, a missing header, or a timestamp outside the tolerance window.
    """
    if not secret or not webhook_id or not webhook_timestamp or not webhook_signature:
        return False
    try:
        timestamp = int(webhook_timestamp)
    except ValueError:
        return False
    current = time.time() if now is None else now
    if abs(current - timestamp) > STANDARD_WEBHOOK_TOLERANCE_SECONDS:
        return False

    encoded_key = secret[len("whsec_"):] if secret.startswith("whsec_") else secret
    try:
        key = base64.b64decode(encoded_key)
    except (binascii.Error, ValueError):
        return False

    signed = webhook_id.encode("utf-8") + b"." + webhook_timestamp.encode("utf-8") + b"." + raw_body
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode("ascii")
    for entry in webhook_signature.split():
        version, _, signature = entry.partition(",")
        if version == "v1" and hmac.compare_digest(expected, signature):
            return True
    return False
