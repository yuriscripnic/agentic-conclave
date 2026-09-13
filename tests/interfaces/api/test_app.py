"""Integration tests for the FastAPI adapter (`interfaces.api.app`)."""
from fastapi.testclient import TestClient

from interfaces.api.app import create_app


def test_health_route() -> None:
    client = TestClient(create_app(agent_mode="fake", gm_mode="fake"))

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
