"""Task 5 event-feed formatting guards: static asset string checks only.

app.js is plain browser JS (no Node toolchain exists), so these tests assert
the formatter table contains the wire event_type keys and the exact payload
field names from src/domain/events/events.py (BaseEvent.to_payload serializes
dataclass fields verbatim into the JSON payload).
"""
from fastapi.testclient import TestClient

from interfaces.api.app import create_app
from interfaces.web.mount import mount_web


def _app_js() -> str:
    client = TestClient(mount_web(create_app(agent_mode="fake", gm_mode="fake")))
    response = client.get("/assets/app.js")
    assert response.status_code == 200
    return response.text


def test_formatter_table_covers_all_wire_event_types() -> None:
    js = _app_js()
    # Wire event_type is snake_case (BaseEvent.event_type in domain/events/base.py).
    for event_type in (
        "game_created",
        "game_started",
        "initiative_rolled",
        "combat_started",
        "turn_started",
        "turn_ended",
        "attack_requested",
        "attack_resolved",
        "damage_applied",
        "character_defeated",
        "action_rejected",
        "combat_ended",
    ):
        assert f"{event_type}:" in js


def test_attack_resolved_line_uses_verified_payload_fields() -> None:
    # AttackResolved payload: attacker_id, target_id, roll, attack_bonus,
    # total, target_ac, hit, critical (domain/events/events.py).
    js = _app_js()
    for field in (
        "attacker_id",
        "target_id",
        "roll",
        "attack_bonus",
        "total",
        "target_ac",
        "hit",
        "critical",
    ):
        assert field in js


def test_damage_applied_line_uses_verified_payload_fields() -> None:
    # DamageApplied payload: character_id, amount, hp_before, hp_after.
    js = _app_js()
    for field in ("character_id", "amount", "hp_before", "hp_after"):
        assert field in js


def test_defeated_and_rejected_lines_use_verified_payload_fields() -> None:
    # CharacterDefeated: character_id; ActionRejected: actor_id, action_type, reason;
    # CombatEnded: winner_side, round_number (domain/events/events.py).
    js = _app_js()
    for field in (
        "character_id",
        "actor_id",
        "action_type",
        "reason",
        "winner_side",
        "round_number",
    ):
        assert field in js


def test_turn_lines_are_terse_with_actor_and_round() -> None:
    # TurnStarted/TurnEnded payload: round_number, actor_id.
    js = _app_js()
    assert "actor_id" in js
    assert "round_number" in js


def test_unknown_event_type_falls_back_to_raw_payload_json() -> None:
    js = _app_js()
    # Never lie by omission: unknown types render the type plus compact JSON.
    assert "`— ${envelope.event_type}" in js
    assert "JSON.stringify(payload)" in js


def test_event_feed_uses_textcontent_only() -> None:
    js = _app_js()
    assert "item.textContent" in js
    assert "innerHTML" not in js
