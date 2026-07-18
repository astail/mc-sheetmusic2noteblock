from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_healthz_returns_200():
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}
