"""Error-map tests (contract §3): exception → HTTP status/code."""
from fastapi.testclient import TestClient

from ai.models.errors import ModelError
from domain.common.errors import (
    ConcurrentGameModification,
    GameNotFoundError,
    PersistenceError,
    ValidationError,
)
from interfaces.api.app import create_app
from interfaces.api.errors import HANDLER_TABLE


def test_handler_table_statuses() -> None:
    assert HANDLER_TABLE[type(GameNotFoundError("x"))][0] == 404
    assert HANDLER_TABLE[type(ConcurrentGameModification())][0] == 409
    assert HANDLER_TABLE[type(PersistenceError("db"))][0] == 503
    assert HANDLER_TABLE[type(ValidationError("bad"))][0] == 422
    assert HANDLER_TABLE[type(ModelError("boom"))][0] == 502
    assert HANDLER_TABLE[type(GameNotFoundError("x"))][1] == "game_not_found"


def test_unknown_game_maps_to_404() -> None:
    client = TestClient(
        create_app(agent_mode="fake", gm_mode="fake"), raise_server_exceptions=False
    )

    response = client.get("/api/v1/games/missing-game")

    assert response.status_code == 404
    assert response.json()["error"] == "game_not_found"
    assert "reason" in response.json()
