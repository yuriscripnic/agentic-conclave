"""Task 4 panel-rendering checks: static asset string guards only."""
from fastapi.testclient import TestClient

from interfaces.api.app import create_app
from interfaces.web.mount import STATIC_DIR, mount_web


def _fetch(path: str) -> str:
    client = TestClient(mount_web(create_app(agent_mode="fake", gm_mode="fake")))
    response = client.get(path)
    assert response.status_code == 200
    return response.text


def test_app_js_contains_panel_render_helpers() -> None:
    js = _fetch("/assets/app.js")
    assert "function renderParty(" in js
    assert "renderCombatTracker(" in js
    assert "rosterRow(" in js


def test_app_js_renders_defeated_condition_from_server_fields_only() -> None:
    js = _fetch("/assets/app.js")
    assert "is_defeated" in js
    # No derived rules math ("bloodied" inference, percentage thresholds).
    assert "bloodied" not in js


def test_app_js_highlights_active_actor_by_comparison() -> None:
    js = _fetch("/assets/app.js")
    assert "active_actor_id" in js
    assert "character_id === combat.active_actor_id" in js


def test_app_js_guarded_fallbacks_render_no_undefined() -> None:
    js = _fetch("/assets/app.js")
    assert '?? "-"' in js
    assert "hp_max" in js
    # hp_max == 0 guard in the bar-width helper.
    assert "hpMax <= 0" in js


def test_app_js_does_not_use_innerhtml_for_model_data() -> None:
    js = _fetch("/assets/app.js")
    assert "innerHTML" not in js


def test_game_html_contains_party_enemies_and_tracker_containers() -> None:
    html = (STATIC_DIR / "game.html").read_text()
    assert 'id="party-panel"' in html
    assert 'id="enemies-panel"' in html
    assert 'id="combat-tracker"' in html


def test_styles_css_contains_panel_and_tracker_styles() -> None:
    css = (STATIC_DIR / "styles.css").read_text()
    assert ".roster-row" in css
    assert ".hp-bar" in css
    assert ".condition-tag" in css
    assert ".defeated" in css
    assert ".initiative-entry.active-actor" in css
