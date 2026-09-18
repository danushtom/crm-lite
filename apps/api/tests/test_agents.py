"""Team (agent) endpoints not covered elsewhere."""

from __future__ import annotations

from app.core.config import API_V1_PREFIX as V1
from tests.conftest import FakeResult

ADMIN_ROLE = {"id": "role-admin-1", "name": "Admin", "grants_full_access": True, "role_permissions": []}


def test_performance_counts_wins_on_opportunities_where_stage_lives(authed_client, fake_db, test_user):
    fake_db.responses["GET users"] = FakeResult(
        [{"id": test_user.sub, "is_active": True, "roles": ADMIN_ROLE, "organization_id": "org-1"}]
    )
    fake_db.responses["GET leads"] = FakeResult([], count=4)
    fake_db.responses["GET opportunities"] = FakeResult([], count=1)
    fake_db.responses["GET activities"] = FakeResult([], count=0)
    fake_db.responses["GET meetings"] = FakeResult([], count=0)

    response = authed_client.get(f"{V1}/agents/agent-9/performance")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["assigned_leads"] == 4
    assert body["wins"] == 1
    assert body["win_rate"] == 0.25
    lead_filters = [c[2]["params"] for c in fake_db.calls if c[1] == "leads"]
    assert all("stage" not in params for params in lead_filters)
    wins_query = next(c[2]["params"] for c in fake_db.calls if c[1] == "opportunities")
    assert wins_query["stage"] == "eq.won"
    assert wins_query["owner_id"] == "eq.agent-9"
