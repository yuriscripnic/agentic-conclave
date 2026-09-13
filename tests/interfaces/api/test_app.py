"""Integration tests for the FastAPI adapter (`interfaces.api.app`)."""
from fastapi.testclient import TestClient

from interfaces.api.app import create_app


def _idem(key: str) -> dict[str, str]:
    return {"Idempotency-Key": key}


def test_health_route() -> None:
    client = TestClient(create_app(agent_mode="fake", gm_mode="fake"))

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_game_returns_session() -> None:
    client = TestClient(create_app(agent_mode="fake", gm_mode="fake"))

    response = client.post("/api/v1/games", json={"seed": 7}, headers=_idem("idem-1"))

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["game_id"]
    assert body["view"]["campaign_name"] == "The Forgotten Ruins"
    assert body["view"]["status"] == "running"
    assert body["opening"] is not None  # fake GM narrates combat open


def test_create_game_idempotent_replay() -> None:
    client = TestClient(create_app(agent_mode="fake", gm_mode="fake"))

    first = client.post("/api/v1/games", json={"seed": 7}, headers=_idem("idem-2"))
    second = client.post("/api/v1/games", json={"seed": 7}, headers=_idem("idem-2"))

    assert first.json()["game_id"] == second.json()["game_id"]
    assert second.json() == first.json()


def test_create_game_without_key_creates_new_game() -> None:
    client = TestClient(create_app(agent_mode="fake", gm_mode="fake"))

    a = client.post("/api/v1/games", json={"seed": 7})
    b = client.post("/api/v1/games", json={"seed": 7})

    assert a.json()["game_id"] != b.json()["game_id"]
