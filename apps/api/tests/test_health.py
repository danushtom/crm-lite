"""Probe endpoints."""


def test_health_live(client):
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["live"] is True


def test_health_basic(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_is_not_rate_limit_logged(client):
    """Probes must stay unauthenticated so orchestrators can reach them."""
    for _ in range(3):
        assert client.get("/health").status_code == 200
