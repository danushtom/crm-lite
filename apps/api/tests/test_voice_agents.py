"""Voice agent CRUD, compliance gating, and the outbound-call consent gate.

Row visibility for `calls` is RLS's job; these tests cover the application-layer gates on top
-- full-access-only writes, the per-org compliance acknowledgment, and the per-contact consent
check that must happen before a real (billable, regulated) phone call is placed.
"""

from __future__ import annotations

from app.core.config import API_V1_PREFIX as V1
from app.core.config import settings
from tests.conftest import FakeResult

ADMIN_ROLE = {"id": "role-admin-1", "name": "Admin", "grants_full_access": True, "role_permissions": []}
AGENT_ROLE = {
    "id": "role-agent-1",
    "name": "Agent",
    "grants_full_access": False,
    "role_permissions": [{"permissions": {"resource": "voice_agents", "action": "read"}}],
}

ORG_ACKED = {"id": "org-1", "name": "Acme Inc", "ai_calling_compliance_ack_at": "2026-09-01T00:00:00Z"}
ORG_NOT_ACKED = {"id": "org-1", "name": "Acme Inc", "ai_calling_compliance_ack_at": None}

VOICE_AGENT_ROW = {
    "id": "va-1",
    "name": "Sales Bot",
    "system_prompt": "You are a helpful sales rep.",
    "direction": "outbound",
    "voice_id": None,
    "platform": "vapi",
    "platform_assistant_id": "assistant-123",
    "phone_number_id": "pn-1",
    "disclosure_script": "You're speaking with Sales Bot, an AI assistant from Acme Inc. This call may be recorded.",
    "is_active": True,
    "version": 1,
}


def as_admin(fake_db, test_user):
    fake_db.responses["GET users"] = FakeResult(
        [{"id": test_user.sub, "role_id": ADMIN_ROLE["id"], "is_active": True, "roles": ADMIN_ROLE, "organization_id": "org-1"}]
    )


def as_agent(fake_db, test_user):
    fake_db.responses["GET users"] = FakeResult(
        [{"id": test_user.sub, "role_id": AGENT_ROLE["id"], "is_active": True, "roles": AGENT_ROLE, "organization_id": "org-1"}]
    )


# --- List -----------------------------------------------------------------------


def test_any_authenticated_user_can_list_voice_agents(authed_client, fake_db, test_user):
    as_agent(fake_db, test_user)
    fake_db.responses["GET voice_agents"] = FakeResult([VOICE_AGENT_ROW])

    response = authed_client.get(f"{V1}/voice-agents")

    assert response.status_code == 200
    assert response.json()[0]["name"] == "Sales Bot"


# --- Create -----------------------------------------------------------------------


def test_a_non_admin_cannot_create_a_voice_agent(authed_client, fake_db, test_user):
    as_agent(fake_db, test_user)

    response = authed_client.post(
        f"{V1}/voice-agents",
        json={"name": "Should Not Exist", "system_prompt": "hi", "direction": "outbound"},
    )

    assert response.status_code == 403
    assert not [c for c in fake_db.calls if c[0] == "POST" and c[1] == "voice_agents"]


def test_creating_a_voice_agent_without_compliance_ack_is_blocked(authed_client, fake_db, test_user):
    as_admin(fake_db, test_user)
    fake_db.responses["GET organizations"] = FakeResult(ORG_NOT_ACKED)

    response = authed_client.post(
        f"{V1}/voice-agents",
        json={"name": "Sales Bot", "system_prompt": "hi", "direction": "outbound"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "compliance_ack_required"
    assert not [c for c in fake_db.calls if c[0] == "POST" and c[1] == "voice_agents"]


def test_an_admin_can_create_a_voice_agent(authed_client, fake_db, test_user, monkeypatch):
    monkeypatch.setattr(settings, "voice_platform_api_key", "", raising=False)
    as_admin(fake_db, test_user)
    fake_db.responses["GET organizations"] = FakeResult(ORG_ACKED)
    fake_db.responses["POST voice_agents"] = FakeResult({**VOICE_AGENT_ROW, "platform_assistant_id": None})

    response = authed_client.post(
        f"{V1}/voice-agents",
        json={"name": "Sales Bot", "system_prompt": "You are a helpful sales rep.", "direction": "outbound"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Sales Bot"
    # Disclosure is server-generated from the org's real name, not admin-supplied.
    payload = [c for c in fake_db.calls if c[0] == "POST" and c[1] == "voice_agents"][0][2]["payload"]
    assert "Acme Inc" in payload["disclosure_script"]
    # No platform key configured -- the agent still exists, just not yet wired to a platform.
    assert not [c for c in fake_db.calls if c[0] == "PATCH" and c[1] == "voice_agents"]


def test_creating_a_voice_agent_assigns_its_phone_number(authed_client, fake_db, test_user, monkeypatch):
    """phone_numbers.assigned_voice_agent_id is what inbound routing keys off (see
    voice_webhooks.py) -- assigning a number to an agent must keep it in sync, not just set
    the forward reference on voice_agents.phone_number_id."""
    monkeypatch.setattr(settings, "voice_platform_api_key", "", raising=False)
    as_admin(fake_db, test_user)
    fake_db.responses["GET organizations"] = FakeResult(ORG_ACKED)
    fake_db.responses["POST voice_agents"] = FakeResult({**VOICE_AGENT_ROW, "phone_number_id": "pn-1"})

    response = authed_client.post(
        f"{V1}/voice-agents",
        json={"name": "Sales Bot", "system_prompt": "hi", "direction": "outbound", "phone_number_id": "pn-1"},
    )

    assert response.status_code == 201
    phone_patch = [c for c in fake_db.calls if c[0] == "PATCH" and c[1] == "phone_numbers"][0]
    assert phone_patch[2]["params"]["id"] == "eq.pn-1"
    assert phone_patch[2]["payload"] == {"assigned_voice_agent_id": "va-1"}


def test_updating_a_voice_agents_phone_number_releases_the_old_one(authed_client, fake_db, test_user):
    as_admin(fake_db, test_user)
    fake_db.responses["GET voice_agents"] = FakeResult({**VOICE_AGENT_ROW, "phone_number_id": "pn-old"})
    fake_db.responses["PATCH voice_agents"] = FakeResult({**VOICE_AGENT_ROW, "phone_number_id": "pn-new"})

    response = authed_client.patch(f"{V1}/voice-agents/va-1", json={"phone_number_id": "pn-new"})

    assert response.status_code == 200
    phone_patches = [c for c in fake_db.calls if c[0] == "PATCH" and c[1] == "phone_numbers"]
    released = [c for c in phone_patches if c[2]["payload"].get("assigned_voice_agent_id") is None]
    assigned = [c for c in phone_patches if c[2]["payload"].get("assigned_voice_agent_id") == "va-1"]
    assert released and released[0][2]["params"]["id"] == "eq.pn-old"
    assert assigned and assigned[0][2]["params"]["id"] == "eq.pn-new"


# --- Compliance ack -----------------------------------------------------------------


def test_a_non_admin_cannot_acknowledge_compliance(authed_client, fake_db, test_user):
    as_agent(fake_db, test_user)

    response = authed_client.post(f"{V1}/voice-agents/compliance-ack")

    assert response.status_code == 403


def test_an_admin_can_acknowledge_compliance(authed_client, fake_db, test_user):
    as_admin(fake_db, test_user)
    fake_db.responses["PATCH organizations"] = FakeResult(ORG_ACKED)

    response = authed_client.post(f"{V1}/voice-agents/compliance-ack")

    assert response.status_code == 200
    assert response.json()["acknowledged"] is True


# --- Outbound call placement: the consent gate --------------------------------------


def test_a_non_admin_cannot_place_a_call(authed_client, fake_db, test_user):
    as_agent(fake_db, test_user)

    response = authed_client.post(f"{V1}/voice-agents/va-1/calls", json={"contact_id": "contact-1"})

    assert response.status_code == 403


def test_an_outbound_call_is_blocked_without_consent(authed_client, fake_db, test_user):
    as_admin(fake_db, test_user)
    fake_db.responses["GET organizations"] = FakeResult(ORG_ACKED)
    fake_db.responses["GET voice_agents"] = FakeResult(VOICE_AGENT_ROW)
    fake_db.responses["GET contacts"] = FakeResult({"phone": "+15551234567", "ai_call_consent": False})
    fake_db.responses["GET phone_numbers"] = FakeResult({"e164_number": "+15550001111"})
    fake_db.responses["POST calls"] = FakeResult(
        {"id": "call-1", "organization_id": "org-1", "lead_id": None, "status": "no_consent_blocked"}
    )

    response = authed_client.post(f"{V1}/voice-agents/va-1/calls", json={"contact_id": "contact-1"})

    assert response.status_code == 403
    assert response.json()["code"] == "no_consent"
    calls_insert = [c for c in fake_db.calls if c[0] == "POST" and c[1] == "calls"][0][2]["payload"]
    assert calls_insert["status"] == "no_consent_blocked"


def test_an_outbound_call_requires_the_agent_to_be_platform_configured(authed_client, fake_db, test_user):
    as_admin(fake_db, test_user)
    fake_db.responses["GET organizations"] = FakeResult(ORG_ACKED)
    fake_db.responses["GET voice_agents"] = FakeResult({**VOICE_AGENT_ROW, "platform_assistant_id": None})

    response = authed_client.post(f"{V1}/voice-agents/va-1/calls", json={"contact_id": "contact-1"})

    assert response.status_code == 501
    assert not [c for c in fake_db.calls if c[0] == "POST" and c[1] == "calls"]


def test_an_outbound_call_requires_the_contact_to_have_a_phone_number(authed_client, fake_db, test_user):
    as_admin(fake_db, test_user)
    fake_db.responses["GET organizations"] = FakeResult(ORG_ACKED)
    fake_db.responses["GET voice_agents"] = FakeResult(VOICE_AGENT_ROW)
    fake_db.responses["GET contacts"] = FakeResult({"phone": None, "ai_call_consent": True})
    fake_db.responses["GET phone_numbers"] = FakeResult({"e164_number": "+15550001111"})

    response = authed_client.post(f"{V1}/voice-agents/va-1/calls", json={"contact_id": "contact-1"})

    assert response.status_code == 501
    assert not [c for c in fake_db.calls if c[0] == "POST" and c[1] == "calls"]


def test_a_lead_id_from_another_organization_is_rejected(authed_client, fake_db, test_user):
    """lead_id is client-supplied; without this check it would still get written onto the
    calls row (calls.organization_id comes from voice_agents, not from lead_id), and
    finalize_call() would then write an activity/notification into a lead that belongs to a
    different organization entirely."""
    as_admin(fake_db, test_user)
    fake_db.responses["GET organizations"] = FakeResult(ORG_ACKED)
    fake_db.responses["GET voice_agents"] = FakeResult(VOICE_AGENT_ROW)
    fake_db.responses["GET contacts"] = FakeResult({"phone": "+15551234567", "ai_call_consent": True})
    fake_db.responses["GET phone_numbers"] = FakeResult({"e164_number": "+15550001111"})
    fake_db.responses["GET leads"] = FakeResult(None)  # not visible to this org under RLS

    response = authed_client.post(
        f"{V1}/voice-agents/va-1/calls", json={"contact_id": "contact-1", "lead_id": "someone-elses-lead"}
    )

    assert response.status_code == 403
    assert not [c for c in fake_db.calls if c[0] == "POST" and c[1] == "calls"]


def test_a_platform_failure_marks_the_call_failed_not_stuck_queued(authed_client, fake_db, test_user, monkeypatch):
    monkeypatch.setattr(settings, "voice_platform_api_key", "", raising=False)
    as_admin(fake_db, test_user)
    fake_db.responses["GET organizations"] = FakeResult(ORG_ACKED)
    fake_db.responses["GET voice_agents"] = FakeResult(VOICE_AGENT_ROW)
    fake_db.responses["GET contacts"] = FakeResult({"phone": "+15551234567", "ai_call_consent": True})
    fake_db.responses["GET phone_numbers"] = FakeResult({"e164_number": "+15550001111"})
    fake_db.responses["POST calls"] = FakeResult({"id": "call-1", "organization_id": "org-1"})

    response = authed_client.post(f"{V1}/voice-agents/va-1/calls", json={"contact_id": "contact-1"})

    assert response.status_code == 501  # voice platform not configured -> NotConfiguredError
    patch_payload = [c for c in fake_db.calls if c[0] == "PATCH" and c[1] == "calls"][0][2]["payload"]
    assert patch_payload["status"] == "failed"
