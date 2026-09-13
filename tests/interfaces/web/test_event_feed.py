"""Task 5 event-feed formatting guards: static asset string checks only.

app.js is plain browser JS (no Node toolchain exists), so these tests assert
the formatter table contains the wire event_type keys and the exact payload
field names from src/domain/events/events.py (BaseEvent.to_payload serializes
dataclass fields verbatim into the JSON payload).

Field assertions are scoped to the specific formatter's table entry substring
(not the whole file) so they fail if the formatter stops using those fields.
"""
import re

from fastapi.testclient import TestClient

from interfaces.api.app import create_app
from interfaces.web.mount import mount_web


def _app_js() -> str:
    client = TestClient(mount_web(create_app(agent_mode="fake", gm_mode="fake")))
    response = client.get("/assets/app.js")
    assert response.status_code == 200
    return response.text


def _formatter_entry(js: str, event_type: str) -> str:
    """The source substring of one EVENT_FORMATTERS table entry.

    Spans from the `event_type:` key to the next entry key or the table's
    closing brace — so field assertions below apply inside that entry only.
    """
    match = re.search(rf"^\s+{event_type}: ", js, re.MULTILINE)
    assert match, f"EVENT_FORMATTERS has no {event_type} entry"
    rest = js[match.end() :]
    next_key = re.search(r"^\s+[a-z_]+: ", rest, re.MULTILINE)
    closing = re.search(r"^\};", rest, re.MULTILINE)
    candidates = [m.start() for m in (next_key, closing) if m]
    return rest[: min(candidates)] if candidates else rest


def test_single_format_event_declaration() -> None:
    # A second (later) formatEvent declaration would shadow the formatter
    # table at runtime (JS last-declaration-wins).
    js = _app_js()
    assert len(re.findall(r"^function formatEvent\(", js, re.MULTILINE)) == 1


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
    entry = _formatter_entry(_app_js(), "attack_resolved")
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
        assert field in entry


def test_damage_applied_line_uses_verified_payload_fields() -> None:
    # DamageApplied payload: character_id, amount, hp_before, hp_after.
    entry = _formatter_entry(_app_js(), "damage_applied")
    for field in ("character_id", "amount", "hp_before", "hp_after"):
        assert field in entry


def test_defeated_line_uses_verified_payload_fields() -> None:
    # CharacterDefeated payload: character_id (domain/events/events.py).
    entry = _formatter_entry(_app_js(), "character_defeated")
    assert "character_id" in entry


def test_rejected_line_uses_verified_payload_fields() -> None:
    # ActionRejected payload: actor_id, action_type, reason.
    entry = _formatter_entry(_app_js(), "action_rejected")
    for field in ("actor_id", "action_type", "reason"):
        assert field in entry


def test_combat_ended_line_uses_verified_payload_fields() -> None:
    # CombatEnded payload: winner_side, round_number.
    entry = _formatter_entry(_app_js(), "combat_ended")
    for field in ("winner_side", "round_number"):
        assert field in entry


def test_turn_lines_are_terse_with_actor_and_round() -> None:
    # TurnStarted/TurnEnded payload: round_number, actor_id.
    for event_type in ("turn_started", "turn_ended"):
        entry = _formatter_entry(_app_js(), event_type)
        for field in ("actor_id", "round_number"):
            assert field in entry


def test_unknown_event_type_falls_back_to_raw_payload_json() -> None:
    js = _app_js()
    # Never lie by omission: unknown types render the type plus compact JSON.
    assert "`— ${envelope.event_type}" in js
    assert "JSON.stringify(payload)" in js


def test_event_feed_uses_textcontent_only() -> None:
    js = _app_js()
    assert "item.textContent" in js
    assert "innerHTML" not in js
