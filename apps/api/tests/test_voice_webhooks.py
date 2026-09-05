"""Voice platform webhook: signature verification, and the critical security property that a
payload's own claims are never trusted for tenant scoping -- only a server-side, DB-resolved
lookup keyed by our own call_id is.
"""

from __future__ import annotations

import hashlib
import hmac
import json

from app.core.config import API_V1_PREFIX as V1
from app.core.config import settings
from app.core.webhook_security import verify_platform_signature
from tests.conftest import FakeResult

SECRET = "test-webhook-secret"


def sign(body: bytes) -> str:
    return hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


# --- Pure signature verification ------------------------------------------------------


def test_valid_signature_verifies(monkeypatch):
    monkeypatch.setattr(settings, "voice_platform_webhook_secret", SECRET, raising=False)
    body = b'{"hello":"world"}'
    assert verify_platform_signature(body, sign(body)) is True


def test_tampered_body_fails_verification(monkeypatch):
    monkeypatch.setattr(settings, "voice_platform_webhook_secret", SECRET, raising=False)
    body = b'{"hello":"world"}'
    other_body = b'{"hello":"tampered"}'
    assert verify_platform_signature(other_body, sign(body)) is False


def test_missing_signature_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "voice_platform_webhook_secret", SECRET, raising=False)
    assert verify_platform_signature(b"{}", None) is False


def test_missing_secret_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "voice_platform_webhook_secret", "", raising=False)
    body = b"{}"
    assert verify_platform_signature(body, sign(body)) is False


# --- Route-level: invalid signature never reaches the handler logic -----------------


def test_invalid_signature_is_401(authed_client, monkeypatch):
    monkeypatch.setattr(settings, "voice_platform_webhook_secret", SECRET, raising=False)
    body = json.dumps({"message": {"type": "status-update"}}).encode()

    response = authed_client.post(
        f"{V1}/voice-webhooks/platform/events",
        content=body,
        headers={"Content-Type": "application/json", "X-Vapi-Signature": "wrong"},
    )

    assert response.status_code == 401


# --- The critical property: a claimed org in the payload is never trusted -----------


def test_org_is_resolved_from_our_own_call_row_not_the_payload(authed_client, fake_db, monkeypatch):
    monkeypatch.setattr(settings, "voice_platform_webhook_secret", SECRET, raising=False)
    fake_db.responses["GET calls"] = FakeResult(
        {"id": "call-1", "organization_id": "real-org", "lead_id": None, "provider_call_id": None}
    )
    fake_db.responses["GET permissions"] = FakeResult([])  # unrelated table, harmless if hit

    body = json.dumps(
        {
            "message": {
                "type": "tool-calls",
                "call": {"id": "provider-call-xyz", "metadata": {"call_id": "call-1", "organization_id": "attacker-claimed-org"}},
                "toolCalls": [
                    {"id": "tc-1", "function": {"name": "check_consent", "arguments": {"contact_id": "contact-1"}}}
                ],
            }
        }
    ).encode()

    response = authed_client.post(
        f"{V1}/voice-webhooks/platform/events",
        content=body,
        headers={"Content-Type": "application/json", "X-Vapi-Signature": sign(body)},
    )

    assert response.status_code == 200
    contacts_call = [c for c in fake_db.calls if c[0] == "GET" and c[1] == "contacts"][0]
    assert contacts_call[2]["params"]["organization_id"] == "eq.real-org"
    assert "attacker-claimed-org" not in str(contacts_call[2]["params"])


def test_unknown_call_id_is_ignored_not_errored(authed_client, fake_db, monkeypatch):
    monkeypatch.setattr(settings, "voice_platform_webhook_secret", SECRET, raising=False)
    fake_db.responses["GET calls"] = FakeResult(None)
    fake_db.responses["GET phone_numbers"] = FakeResult(None)

    body = json.dumps(
        {"message": {"type": "status-update", "call": {"id": "x", "metadata": {"call_id": "does-not-exist"}}}}
    ).encode()

    response = authed_client.post(
        f"{V1}/voice-webhooks/platform/events",
        content=body,
        headers={"Content-Type": "application/json", "X-Vapi-Signature": sign(body)},
    )

    assert response.status_code == 200
    assert response.json() == {"ignored": True}


def test_a_second_terminal_event_for_an_already_finalized_call_does_not_double_finalize(authed_client, fake_db, monkeypatch):
    """Vapi-style platforms can fire both a status-update and a separate end-of-call-report for
    the same call, and any webhook can be redelivered -- finalize_call() must not run twice, or
    a lead gets two identical activity-timeline entries for one call."""
    monkeypatch.setattr(settings, "voice_platform_webhook_secret", SECRET, raising=False)
    fake_db.responses["GET calls"] = FakeResult(
        {"id": "call-1", "organization_id": "org-1", "lead_id": "lead-1", "status": "completed"}
    )
    fake_db.responses["PATCH calls"] = FakeResult(
        {"id": "call-1", "organization_id": "org-1", "lead_id": "lead-1", "status": "completed", "summary": "already done"}
    )

    body = json.dumps(
        {
            "message": {
                "type": "end-of-call-report",
                "call": {"id": "pc-1", "status": "completed", "metadata": {"call_id": "call-1"}},
                "summary": "a second report for the same call",
            }
        }
    ).encode()

    response = authed_client.post(
        f"{V1}/voice-webhooks/platform/events",
        content=body,
        headers={"Content-Type": "application/json", "X-Vapi-Signature": sign(body)},
    )

    assert response.status_code == 200
    assert not [c for c in fake_db.calls if c[0] == "POST" and c[1] == "activities"]
    assert not [c for c in fake_db.calls if c[0] == "POST" and c[1] == "notifications"]


def test_status_update_finalizes_a_completed_call(authed_client, fake_db, monkeypatch):
    monkeypatch.setattr(settings, "voice_platform_webhook_secret", SECRET, raising=False)
    fake_db.responses["GET calls"] = FakeResult(
        {"id": "call-1", "organization_id": "org-1", "lead_id": None, "provider_call_id": "pc-1"}
    )
    fake_db.responses["PATCH calls"] = FakeResult(
        {"id": "call-1", "organization_id": "org-1", "lead_id": None, "status": "completed"}
    )

    body = json.dumps(
        {
            "message": {
                "type": "end-of-call-report",
                "call": {"id": "pc-1", "status": "completed", "metadata": {"call_id": "call-1"}},
                "artifact": {"recordingUrl": "https://example.com/rec.mp3", "transcript": "hello"},
                "durationSeconds": 42,
            }
        }
    ).encode()

    response = authed_client.post(
        f"{V1}/voice-webhooks/platform/events",
        content=body,
        headers={"Content-Type": "application/json", "X-Vapi-Signature": sign(body)},
    )

    assert response.status_code == 200
    payload = [c for c in fake_db.calls if c[0] == "PATCH" and c[1] == "calls"][0][2]["payload"]
    assert payload["status"] == "completed"
    assert payload["duration_seconds"] == 42
    # lead_id is None on this call, so finalize_call should not attempt an activities insert.
    assert not [c for c in fake_db.calls if c[0] == "POST" and c[1] == "activities"]
