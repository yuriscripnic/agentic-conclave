"""Tests for the static web UI mount (`interfaces.web.mount`)."""
from fastapi.testclient import TestClient

from interfaces.api.app import create_app
from interfaces.web.mount import STATIC_DIR, mount_web


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


def test_index_html_contains_new_game_form() -> None:
    response = _client().get("/")
    assert response.status_code == 200
    assert 'id="new-game-form"' in response.text
    assert 'id="campaign-name"' in response.text
    assert 'id="seed"' in response.text
    assert 'id="create-game"' in response.text
    assert 'id="lobby-error"' in response.text


def test_app_js_wires_create_game_request() -> None:
    response = _client().get("/assets/app.js")
    assert response.status_code == 200
    assert "crypto.randomUUID" in response.text
    assert '"POST /api/v1/games"' in response.text
    assert "Idempotency-Key" in response.text


def test_static_files_exist_and_are_non_empty() -> None:
    for name in ("index.html", "game.html", "app.js", "styles.css"):
        path = STATIC_DIR / name
        assert path.is_file(), f"missing static file: {name}"
        assert path.stat().st_size > 0, f"empty static file: {name}"


def test_app_js_polls_status_with_interval_and_stop_condition() -> None:
    response = _client().get("/assets/app.js")
    assert response.status_code == 200
    assert "2500" in response.text
    assert "game_over" in response.text


def test_app_js_filters_events_client_side_by_sequence() -> None:
    response = _client().get("/assets/app.js")
    assert response.status_code == 200
    assert "lastSeq" in response.text
    assert "sequence > lastSeq" in response.text


def test_game_html_contains_feed_and_panel_containers() -> None:
    response = _client().get("/games/any-id")
    assert response.status_code == 200
    assert 'id="event-feed"' in response.text
    assert 'id="party-panel"' in response.text
    assert 'id="enemies-panel"' in response.text
    assert 'id="combat-tracker"' in response.text
