"""The public lead-capture endpoint.

This is the only unauthenticated write path in the API, so the tests that matter are the ones
about what a key holder cannot do: reach another tenant, learn anything from the response, or
set fields the server is supposed to decide.
"""

from __future__ import annotations

from app.core.config import API_V1_PREFIX as V1
from app.domain.attribution import channel_label, derive_lead_source, platform_label
from tests.conftest import FakeResult

CAPTURE = f"{V1}/lead-capture"

KEY_ROW = {
    "id": "key-1",
    "organization_id": "org-1",
    "owner_id": "user-owner",
    "is_active": True,
}

SUBMISSION = {
    "full_name": "Priya Raman",
    "email": "priya@northwind.example",
    "company_name": "Northwind Labs",
    "utm_source": "facebook",
    "utm_medium": "cpc",
    "utm_campaign": "q3-mvp-launch",
    "utm_content": "carousel-b",
    "landing_page_url": "https://dracara.dev/mvp?utm_source=facebook",
}

ADMIN_ROLE = {"id": "role-admin-1", "name": "Admin", "grants_full_access": True, "role_permissions": []}
AGENT_ROLE = {"id": "role-agent-1", "name": "Agent", "grants_full_access": False, "role_permissions": []}


def as_role(fake_db, test_user, role):
    fake_db.responses["GET users"] = FakeResult(
        [{"id": test_user.sub, "role_id": role["id"], "is_active": True, "roles": role, "organization_id": "org-1"}]
    )


def wire_capture(fake_db, key_row=KEY_ROW):
    """Every lookup the happy path makes, in the order it makes them."""
    fake_db.responses["GET lead_capture_keys"] = FakeResult([key_row] if key_row else [])
    fake_db.responses["GET users"] = FakeResult([{"id": "user-owner"}])
    fake_db.responses["GET companies"] = FakeResult([{"id": "company-1"}])
    fake_db.responses["POST contacts"] = FakeResult({"id": "contact-1"})
    fake_db.responses["POST leads"] = FakeResult({"id": "lead-1"})
    fake_db.responses["POST activities"] = FakeResult({"id": "activity-1"})
    fake_db.responses["POST notifications"] = FakeResult({"id": "notification-1"})
    fake_db.responses["PATCH lead_capture_keys"] = FakeResult({"id": "key-1"})


def posted(fake_db, table):
    return [c for c in fake_db.calls if c[0] == "POST" and c[1] == table]


# --- The capture itself --------------------------------------------------------------


def test_a_submission_creates_a_contact_and_a_lead(authed_client, fake_db):
    wire_capture(fake_db)

    response = authed_client.post(CAPTURE, json=SUBMISSION, headers={"X-Capture-Key": "lck_abc"})

    assert response.status_code == 202
    contact = posted(fake_db, "contacts")[0][2]["payload"]
    assert contact["full_name"] == "Priya Raman"
    assert contact["utm_campaign"] == "q3-mvp-launch"
    assert contact["utm_content"] == "carousel-b"
    assert contact["landing_page_url"].startswith("https://dracara.dev/mvp")
    assert posted(fake_db, "leads")[0][2]["payload"]["primary_contact_id"] == "contact-1"


def test_the_organization_comes_from_the_key_not_the_body(authed_client, fake_db):
    """The whole tenant boundary for this endpoint. RLS is not in play -- the write runs on the
    service-role client -- so if the body could influence which organization is written to,
    anyone holding any key could write into any tenant."""
    wire_capture(fake_db)

    response = authed_client.post(
        CAPTURE,
        json={**SUBMISSION, "organization_id": "org-somebody-else"},
        headers={"X-Capture-Key": "lck_abc"},
    )

    # StrictAPIModel rejects the unknown field outright rather than ignoring it.
    assert response.status_code == 422
    assert not posted(fake_db, "contacts")


def test_owner_id_cannot_be_supplied_by_the_submitter(authed_client, fake_db):
    wire_capture(fake_db)

    response = authed_client.post(
        CAPTURE,
        json={**SUBMISSION, "owner_id": "user-someone-else"},
        headers={"X-Capture-Key": "lck_abc"},
    )

    assert response.status_code == 422


def test_consent_is_never_granted_by_a_form_submission(authed_client, fake_db):
    """An inbound form cannot consent someone to being cold-called by an AI agent. If it could,
    the consent gate on outbound calling would be bypassable by whoever controls the form."""
    wire_capture(fake_db)

    authed_client.post(
        CAPTURE,
        json={**SUBMISSION, "ai_call_consent": True},
        headers={"X-Capture-Key": "lck_abc"},
    )
    # Rejected as an unknown field; and on a clean submission it is written as False.
    fake_db.calls.clear()
    authed_client.post(CAPTURE, json=SUBMISSION, headers={"X-Capture-Key": "lck_abc"})
    assert posted(fake_db, "contacts")[0][2]["payload"]["ai_call_consent"] is False


def test_an_existing_company_is_reused_rather_than_duplicated(authed_client, fake_db):
    wire_capture(fake_db)

    authed_client.post(CAPTURE, json=SUBMISSION, headers={"X-Capture-Key": "lck_abc"})

    assert not posted(fake_db, "companies")
    assert posted(fake_db, "leads")[0][2]["payload"]["company_id"] == "company-1"


def test_an_unknown_company_is_created_in_the_resolved_organization(authed_client, fake_db):
    wire_capture(fake_db)
    fake_db.responses["GET companies"] = FakeResult([])
    fake_db.responses["POST companies"] = FakeResult({"id": "company-new"})

    authed_client.post(CAPTURE, json=SUBMISSION, headers={"X-Capture-Key": "lck_abc"})

    # companies_set_org derives organization_id from created_by, which is the owner we resolved
    # from the key -- so the new company lands in the key's organization, not anywhere else.
    assert posted(fake_db, "companies")[0][2]["payload"]["created_by"] == "user-owner"


def test_the_free_text_message_is_logged_as_a_system_activity(authed_client, fake_db):
    """actor_type 'system' with no performed_by: the prospect wrote this, not the rep it is
    assigned to."""
    wire_capture(fake_db)

    authed_client.post(
        CAPTURE,
        json={**SUBMISSION, "message": "We need an MVP by March."},
        headers={"X-Capture-Key": "lck_abc"},
    )

    activity = posted(fake_db, "activities")[0][2]["payload"]
    assert activity["description"] == "We need an MVP by March."
    assert activity["actor_type"] == "system"
    assert activity["performed_by"] is None


# --- What a bad or leaked key gets ---------------------------------------------------


def test_an_unknown_key_is_indistinguishable_from_a_good_one(authed_client, fake_db):
    """Any other status would let a key holder probe for which organizations exist."""
    wire_capture(fake_db, key_row=None)

    response = authed_client.post(CAPTURE, json=SUBMISSION, headers={"X-Capture-Key": "lck_nope"})

    assert response.status_code == 202
    assert response.json() == {"received": True}
    assert not posted(fake_db, "contacts")


def test_a_missing_key_header_writes_nothing(authed_client, fake_db):
    wire_capture(fake_db, key_row=None)

    response = authed_client.post(CAPTURE, json=SUBMISSION)

    assert response.status_code == 202
    assert not posted(fake_db, "contacts")


def test_a_revoked_key_is_filtered_in_the_query_itself(authed_client, fake_db):
    """Revocation has to take effect in the lookup, not in a Python check afterwards that a
    later edit could drop."""
    wire_capture(fake_db, key_row=None)

    authed_client.post(CAPTURE, json=SUBMISSION, headers={"X-Capture-Key": "lck_abc"})

    params = [c for c in fake_db.calls if c[0] == "GET" and c[1] == "lead_capture_keys"][0][2]["params"]
    assert params["is_active"] == "is.true"


def test_a_malformed_key_never_reaches_the_database(authed_client, fake_db):
    wire_capture(fake_db, key_row=None)

    response = authed_client.post(CAPTURE, json=SUBMISSION, headers={"X-Capture-Key": "not-a-key"})

    assert response.status_code == 202
    assert not [c for c in fake_db.calls if c[1] == "lead_capture_keys"]


def test_the_response_never_reveals_whether_the_person_was_already_known(authed_client, fake_db):
    wire_capture(fake_db)

    known = authed_client.post(CAPTURE, json=SUBMISSION, headers={"X-Capture-Key": "lck_abc"})
    unknown = authed_client.post(CAPTURE, json=SUBMISSION, headers={"X-Capture-Key": "lck_nope"})

    assert known.json() == unknown.json() == {"received": True}


def test_oversized_fields_are_rejected(authed_client, fake_db):
    wire_capture(fake_db)

    response = authed_client.post(
        CAPTURE,
        json={**SUBMISSION, "full_name": "x" * 5000},
        headers={"X-Capture-Key": "lck_abc"},
    )

    assert response.status_code == 422
    assert not posted(fake_db, "contacts")


# --- Key management ------------------------------------------------------------------


def test_a_non_admin_cannot_list_capture_keys(authed_client, fake_db, test_user):
    """These are write credentials for the whole organization, so they are admin-only in the
    API and in RLS both."""
    as_role(fake_db, test_user, AGENT_ROLE)

    response = authed_client.get(f"{CAPTURE}/keys")

    assert response.status_code == 403


def test_an_admin_creates_a_key_with_a_server_generated_secret(authed_client, fake_db, test_user):
    as_role(fake_db, test_user, ADMIN_ROLE)
    fake_db.responses["POST lead_capture_keys"] = FakeResult(
        {"id": "key-1", "name": "Meta lead form", "key": "lck_x", "is_active": True}
    )

    response = authed_client.post(f"{CAPTURE}/keys", json={"name": "Meta lead form"})

    assert response.status_code == 201
    payload = posted(fake_db, "lead_capture_keys")[0][2]["payload"]
    assert payload["key"].startswith("lck_")
    assert len(payload["key"]) > 40
    assert payload["created_by"] == test_user.sub
    # db.insert takes no query params, so a "select" here is sent as a column and PostgREST
    # rejects the whole write ("could not find the 'select' column"). FakeDb accepts any
    # payload, so only a real request caught this the first time.
    assert "select" not in payload


def test_a_client_cannot_choose_its_own_key_value(authed_client, fake_db, test_user):
    as_role(fake_db, test_user, ADMIN_ROLE)

    response = authed_client.post(
        f"{CAPTURE}/keys", json={"name": "Mine", "key": "lck_predictable"}
    )

    assert response.status_code == 422


def test_an_admin_can_revoke_a_key(authed_client, fake_db, test_user):
    as_role(fake_db, test_user, ADMIN_ROLE)
    fake_db.responses["PATCH lead_capture_keys"] = FakeResult(
        {"id": "key-1", "name": "Meta lead form", "key": "lck_x", "is_active": False}
    )

    response = authed_client.patch(f"{CAPTURE}/keys/key-1", json={"is_active": False})

    assert response.status_code == 200
    assert response.json()["is_active"] is False


# --- Attribution mapping -------------------------------------------------------------


def test_meta_placements_collapse_to_one_platform():
    """facebook / fb / instagram / ig are the same money. Grouping on the raw utm_source
    spreads one channel across four cards."""
    assert {platform_label(s) for s in ("facebook", "fb", "instagram", "ig", "Meta")} == {"Meta"}


def test_paid_and_organic_from_the_same_platform_are_different_channels():
    assert channel_label("linkedin", "cpc") == "LinkedIn Ads"
    assert channel_label("linkedin", "organic") == "LinkedIn"


def test_an_unknown_platform_is_kept_rather_than_dropped():
    assert channel_label("producthunt", "referral") == "Producthunt"


def test_a_hand_entered_contact_falls_back_to_its_source_enum():
    assert channel_label(None, None, "cold_call") == "Cold Call"
    assert channel_label(None, None, None) == "Direct"


def test_lead_source_is_derived_from_attribution():
    assert derive_lead_source("linkedin", "cpc") == "linkedin"
    assert derive_lead_source("facebook", "cpc") == "website"
    assert derive_lead_source(None, "referral") == "referral"
    assert derive_lead_source(None, None) == "other"
