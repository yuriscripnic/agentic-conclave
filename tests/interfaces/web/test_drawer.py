"""Task 6 human input drawer guards: static asset string checks only.

app.js is plain browser JS (no Node toolchain exists), and game.html is a
pure shell, so these tests assert the drawer markup ids exist, both POST
paths use fresh crypto.randomUUID() idempotency keys, the drawer is
disabled while a submit is in flight, and an immediate refresh runs after
each successful POST.
"""
import re
from collections import Counter

from fastapi.testclient import TestClient

from interfaces.api.app import create_app
from interfaces.web.mount import mount_web


def _client() -> TestClient:
    return TestClient(mount_web(create_app(agent_mode="fake", gm_mode="fake")))


def _app_js() -> str:
    response = _client().get("/assets/app.js")
    assert response.status_code == 200
    return response.text


def _game_html() -> str:
    response = _client().get("/games/any-id")
    assert response.status_code == 200
    return response.text


def test_game_html_has_drawer_markup() -> None:
    html = _game_html()
    assert 'id="input-drawer"' in html
    assert 'id="speak-textarea"' in html
    assert 'id="attack-target"' in html
    assert 'id="attack-weapon"' in html


def test_drawer_is_collapsed_by_default() -> None:
    # <details> without an `open` attribute renders collapsed.
    html = _game_html()
    assert "<details" in html
    assert re.search(r"<details[^>]*\bopen\b", html) is None


def test_gm_strip_sits_above_the_feed() -> None:
    html = _game_html()
    assert html.index('id="gm-strip"') < html.index('id="event-feed"')


def test_drawer_posts_to_input_and_actions_paths() -> None:
    js = _app_js()
    assert "POST /api/v1/games/${currentGameId}/input" in js
    assert "POST /api/v1/games/${currentGameId}/actions" in js


def test_both_posts_use_fresh_idempotency_keys() -> None:
    js = _app_js()
    speak_body = js.split("async function submitSpeak", 1)[1]
    speak_body = speak_body.split("async function submitAttack", 1)[0]
    attack_body = js.split("async function submitAttack", 1)[1]
    attack_body = attack_body.split("function wireDrawer", 1)[0]
    header = '"Idempotency-Key": crypto.randomUUID()'
    assert header in speak_body
    assert header in attack_body


def test_drawer_disabled_while_in_flight() -> None:
    js = _app_js()
    assert "function setDrawerDisabled(disabled)" in js
    assert "setDrawerDisabled(true)" in js
    assert "setDrawerDisabled(false)" in js


def test_immediate_refresh_after_each_successful_post() -> None:
    js = _app_js()
    assert "async function refreshOnce(" in js
    assert js.count("await refreshOnce(currentGameId, errorEl)") == 2
    # The refresh reuses the same in-flight guard as the poller, and a POST
    # issued while a poll is in flight still gets exactly one refresh later.
    # The former `refreshPendingReentry` flag has been removed: the deferred
    # refresh is set unconditionally on guard-miss, and the recursion
    # terminates because the flag is cleared before the single recursive call.
    assert "if (pollInFlight) {" in js
    assert "refreshPending = true;" in js
    assert "refreshPendingReentry" not in js
    # Both finally blocks that release the in-flight guard consume the flag:
    # the polling tick's and refreshOnce's own. (The `let` declaration is
    # excluded by anchoring to the consumption statements.)
    assert len(re.findall(r"^\s+refreshPending = false;", js, re.MULTILINE)) == 2


def test_no_target_option_has_explicit_empty_value() -> None:
    js = _app_js()
    populate = js.split("function populateTargetSelect", 1)[1].split("\nfunction ", 1)[0]
    assert 'noTarget.value = "";' in populate


def test_target_select_populates_from_latest_view() -> None:
    js = _app_js()
    assert "populateTargetSelect(view);" in js
    populate = js.split("function populateTargetSelect", 1)[1].split("\nfunction ", 1)[0]
    for field in ("party", "enemies", "name", "hp_current", "hp_max", "member.id"):
        assert field in populate


def test_single_top_level_declaration_per_name() -> None:
    # JS last-declaration-wins across let/const/function alike: a repeated
    # `let` is a parse-time SyntaxError that kills the whole script. The
    # optional `async ` prefix is included so `async function` names cannot
    # slip past a duplicate of an already-declared name.
    counter = Counter(
        re.findall(
            r"^(?:async )?(?:let|const|class|function) ([A-Za-z_$][\w$]*)",
            _app_js(),
            re.MULTILINE,
        )
    )
    duplicates = [name for name, count in counter.items() if count > 1]
    assert duplicates == [], duplicates


def test_single_drawer_function_declarations() -> None:
    # JS last-declaration-wins: duplicate declarations would shadow behavior.
    js = _app_js()
    for name in ("submitSpeak", "submitAttack", "populateTargetSelect", "refreshOnce"):
        assert len(re.findall(rf"^(?:async )?function {name}\(", js, re.MULTILINE)) == 1, name


def test_drawer_uses_textcontent_only() -> None:
    js = _app_js()
    assert "innerHTML" not in js
