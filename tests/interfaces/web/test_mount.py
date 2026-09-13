"""Tests for the static web UI mount (`interfaces.web.mount`)."""
from fastapi.testclient import TestClient

from interfaces.api.app import create_app
from interfaces.web.mount import mount_web


def _client() -> TestClient:
    return TestClient(mount_web(create_app(agent_mode="fake", gm_mode="fake")))


def test_index_serves_html_shell() -> None:
    response = _client().get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Agentic Conclave" in response.text


def test_game_shell_accepts_any_id() -> None:
    response = _client().get("/games/some-unknown-id")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_static_app_js_is_served() -> None:
    response = _client().get("/assets/app.js")
    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]


def test_api_routes_still_reachable_after_mount() -> None:
    response = _client().get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
