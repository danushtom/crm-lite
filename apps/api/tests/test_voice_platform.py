"""The Vapi adapter's outgoing payload shape.

`create_assistant()`'s `serverUrl` must point at the webhook route that actually exists
(voice_webhooks.py's consolidated `/voice-webhooks/platform/events`) -- a mismatch here means
every real call silently 404s on every status update and tool-call callback, since Vapi has no
way to reach this API at all. That exact mismatch existed once (a leftover
`platform/tool-call` path from an earlier draft that used separate routes per event type) and
would only have been caught against a live account; this test pins it down without one.
"""

from __future__ import annotations

import json

import pytest

from app.core.config import settings
from app.services import voice_platform


class FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.content = json.dumps(self._json).encode()
        self.text = json.dumps(self._json)

    def json(self):
        return self._json


class FakeHttpClient:
    def __init__(self, response: FakeResponse | None = None):
        self.response = response or FakeResponse(200, {"id": "assistant-123"})
        self.calls: list[tuple[str, str, dict]] = []

    async def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.response


@pytest.mark.asyncio
async def test_create_assistant_points_serverurl_at_the_real_webhook_route(monkeypatch):
    monkeypatch.setattr(settings, "voice_platform_api_key", "test-key", raising=False)
    monkeypatch.setattr(settings, "api_public_base_url", "https://example.ngrok.io", raising=False)
    fake_client = FakeHttpClient()
    monkeypatch.setattr("app.services.voice_platform.get_http_client", lambda: fake_client)

    await voice_platform.create_assistant(
        name="Sales Bot", system_prompt="hi", disclosure_script="This call may be recorded.", voice_id=None
    )

    _, _, kwargs = fake_client.calls[0]
    assert kwargs["json"]["serverUrl"] == "https://example.ngrok.io/api/v1/voice-webhooks/platform/events"


@pytest.mark.asyncio
async def test_create_assistant_binds_disclosure_to_first_message_not_system_prompt(monkeypatch):
    """The whole point of disclosure_script being a separate argument: it must always end up
    as the platform's dedicated greeting field, never mixed into the admin's system prompt."""
    monkeypatch.setattr(settings, "voice_platform_api_key", "test-key", raising=False)
    fake_client = FakeHttpClient()
    monkeypatch.setattr("app.services.voice_platform.get_http_client", lambda: fake_client)

    await voice_platform.create_assistant(
        name="Sales Bot",
        system_prompt="Be a helpful rep. Never mention discounts.",
        disclosure_script="This call may be recorded.",
        voice_id=None,
    )

    _, _, kwargs = fake_client.calls[0]
    body = kwargs["json"]
    assert body["firstMessage"] == "This call may be recorded."
    assert body["model"]["messages"][0]["content"] == "Be a helpful rep. Never mention discounts."
    assert "This call may be recorded." not in body["model"]["messages"][0]["content"]
