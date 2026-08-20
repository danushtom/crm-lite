from fastapi.testclient import TestClient

from app.main import app


def test_health_live():
    client = TestClient(app)
    r = client.get("/health/live")
    assert r.status_code == 200
    assert r.json()["live"] is True


def test_health_basic():
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_root():
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert "docs" in r.json()
