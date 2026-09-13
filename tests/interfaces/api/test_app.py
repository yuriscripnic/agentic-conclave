"""Integration tests for the FastAPI adapter (`interfaces.api.app`)."""
import pytest
from fastapi.testclient import TestClient

from interfaces.api.app import create_app


def _idem(key: str) -> dict[str, str]:
    return {"Idempotency-Key": key}


_CLIENT_KWARGS = {"raise_server_exceptions": False}


def _fake_client() -> TestClient:
    return TestClient(create_app(agent_mode="fake", gm_mode="fake"), **_CLIENT_KWARGS)


def _fmt_client() -> TestClient:
    return TestClient(create_app(agent_mode="fake", gm_mode="fake"), **_CLIENT_KWARGS)


@pytest.fixture()
def client() -> TestClient:
    return _fmt_client()


@pytest.fixture()
def game_id(client: TestClient) -> str:
    response = client.post("/api/v1/games", json={"seed": 7}, headers=_idem("create-1"))
    assert response.status_code == 201, response.text
    return response.json()["game_id"]


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


def _view(client: TestClient, game_id: str):
    response = client.get(f"/api/v1/games/{game_id}")
    assert response.status_code == 200, response.text
    return response.json()


def test_get_game_view(game_id: str, client: TestClient) -> None:
    view = _view(client, game_id)

    assert view["game_id"] == game_id
    assert len(view["party"]) >= 1


def test_get_status(game_id: str, client: TestClient) -> None:
    response = client.get(f"/api/v1/games/{game_id}/status")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    assert body["combat"]["round_number"] >= 1
    assert body["game_over"] is False


def test_get_events(game_id: str, client: TestClient) -> None:
    response = client.get(f"/api/v1/games/{game_id}/events")

    assert response.status_code == 200, response.text
    types = [event["event_type"] for event in response.json()["events"]]
    assert "combat_started" in types
    assert "attack_requested" not in types  # nothing has happened yet


def test_attack_action_via_actions_route(game_id: str, client: TestClient) -> None:
    enemy_name = _view(client, game_id)["enemies"][0]["name"]

    response = client.post(
        f"/api/v1/games/{game_id}/actions",
        json={"action_type": "attack", "target": enemy_name},
        headers=_idem(f"atk-{game_id}"),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["accepted"] is True
    assert body["error_code"] == ""
    assert body["events"]
    assert body["view"]["party"]


def test_action_idempotent_replay_returns_first_report(game_id: str, client: TestClient) -> None:
    enemy_name = _view(client, game_id)["enemies"][0]["name"]

    first = client.post(
        f"/api/v1/games/{game_id}/actions",
        json={"action_type": "attack", "target": enemy_name},
        headers=_idem("atk-repeat"),
    )
    second = client.post(
        f"/api/v1/games/{game_id}/actions",
        json={"action_type": "attack", "target": enemy_name},
        headers=_idem("atk-repeat"),
    )

    assert first.status_code == second.status_code == 200
    assert second.json() == first.json()


def test_action_on_unknown_target_maps_to_404(game_id: str, client: TestClient) -> None:
    response = client.post(
        f"/api/v1/games/{game_id}/actions", json={"action_type": "attack", "target": "Nobody"}
    )

    assert response.status_code == 404
    assert response.json()["error"] == "character_not_found"


def test_say_input_roundtrips_gm(game_id: str, client: TestClient) -> None:
    response = client.post(
        f"/api/v1/games/{game_id}/input", json={"text": "say hello there"}, headers=_idem("say-1")
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kind"] == "say"


def test_empty_input_reports_kind_without_execution(game_id: str, client: TestClient) -> None:
    response = client.post(f"/api/v1/games/{game_id}/input", json={"text": "  "})

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "empty"
    assert body["report"] is None


def test_attack_via_input_end_to_end(game_id: str, client: TestClient) -> None:
    enemy_name = _view(client, game_id)["enemies"][0]["name"]

    response = client.post(
        f"/api/v1/games/{game_id}/input",
        json={"text": f"attack {enemy_name}"},
        headers=_idem(f"input-atk-{game_id}"),
    )

    body = response.json()
    assert body["kind"] == "attack"
    assert body["report"] is not None
    assert body["report"]["accepted"] is True


def test_input_idempotent_replay(game_id: str, client: TestClient) -> None:
    enemy_name = _view(client, game_id)["enemies"][0]["name"]

    first = client.post(
        f"/api/v1/games/{game_id}/input",
        json={"text": f"attack {enemy_name}"},
        headers=_idem("input-repeat"),
    )
    second = client.post(
        f"/api/v1/games/{game_id}/input",
        json={"text": f"attack {enemy_name}"},
        headers=_idem("input-repeat"),
    )

    assert first.status_code == second.status_code == 200
    assert second.json() == first.json()
