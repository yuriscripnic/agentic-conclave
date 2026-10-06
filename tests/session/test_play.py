# tests/session/test_play.py
"""advance/apply_input engine tests (spec §4.1): the CLI loop's semantics."""

from pathlib import Path

from session import SessionConfig, advance, apply_input, build_session, open_session


def _drain(session) -> list:
    pendings = []
    while (pending := advance(session)) is not None:
        pendings.append(pending)
    return pendings


def test_advance_drains_until_a_human_turn() -> None:
    session = open_session(SessionConfig(seed=42))

    _drain(session)

    view = session.game_service.get_view(session.game_id)
    assert view.status == "running"
    assert view.combat is not None and view.combat.status == "active"
    actor = view.combat.active_actor_id
    assert actor is not None
    assert all(member.id != actor for member in view.enemies)


def test_advance_drives_agent_turns_and_party_chatter() -> None:
    session = open_session(SessionConfig(seed=42, agent_mode="fake", gm_mode="fake"))

    seen_agent = False
    while True:
        pending = advance(session)
        if pending is None or pending.kind == "agent":
            seen_agent = pending is not None
            break
    assert seen_agent
    assert session.party_board.recent(limit=8)


def test_apply_input_attack_resolves_target() -> None:
    session = open_session(SessionConfig(seed=42))
    _drain(session)

    outcome = apply_input(session, "attack goblin scout")

    assert outcome.kind == "attack"
    assert outcome.turn_report is not None
    assert outcome.turn_report.accepted is True
    assert outcome.gm_result is None  # GM off on this session


def test_apply_input_unknown_target_submits_nothing() -> None:
    session = open_session(SessionConfig(seed=42))
    _drain(session)
    before = len(session.game_service.get_events(session.game_id))

    outcome = apply_input(session, "attack balrog")

    assert outcome.kind == "no_target"
    assert outcome.turn_report is None
    after = len(session.game_service.get_events(session.game_id))
    assert before == after  # no state change


def test_apply_input_say_with_gm_off_records_no_result() -> None:
    session = open_session(SessionConfig(seed=42, gm_mode="off"))
    _drain(session)

    outcome = apply_input(session, "say hold the line")

    assert outcome.kind == "say"
    assert outcome.gm_result is None


def test_apply_input_say_with_gm_fake_returns_reaction() -> None:
    session = open_session(SessionConfig(seed=42, agent_mode="fake", gm_mode="fake"))
    _drain(session)

    outcome = apply_input(session, "say hold the line")

    assert outcome.kind == "say"
    assert outcome.gm_result is not None
    assert outcome.gm_result.npc_reply == "Talk is for the weak. Say your last words!"


def test_apply_input_passthrough_kinds() -> None:
    session = open_session(SessionConfig(seed=42))
    _drain(session)

    quit_outcome = apply_input(session, "/quit")
    assert quit_outcome.kind == "command"
    assert quit_outcome.argument == "/quit"
    unknown = apply_input(session, "dance")
    assert unknown.kind == "unknown"
    assert unknown.argument == "dance"
    assert apply_input(session, "   ").kind == "empty"

def test_go_travels_when_world_configured() -> None:
    session = build_session(SessionConfig(seed=42, world_path=Path("world.toml")))
    outcome = apply_input(session, "go north")
    assert outcome.kind == "travel"
    assert outcome.turn_report is not None
    assert outcome.turn_report.view.scene.name == "Eastern Tower"
    # enemy waits there: combat auto-opened
    assert outcome.turn_report.view.combat is not None


def test_go_unknown_exit_refuses_travel() -> None:
    session = build_session(SessionConfig(seed=42, world_path=Path("world.toml")))
    outcome = apply_input(session, "go west")
    assert outcome.kind == "unknown_exit"
    assert outcome.turn_report.view.scene.name == "Ruined Courtyard"


def test_go_without_world_reports_error() -> None:
    session = build_session(SessionConfig(seed=42))
    outcome = apply_input(session, "go north")
    assert outcome.kind == "error"


_COLOCATED_WORLD = """
[world]
start = "courtyard"
enemies_at = "courtyard"

[[locations]]
id = "courtyard"
name = "Ruined Courtyard"
description = "Enemies wait here but no fight has started."
"""


def test_attack_outside_combat_reports_feedback(tmp_path) -> None:
    """A resolvable target with no active combat must not be a silent no-op (§28)."""
    world = tmp_path / "world.toml"
    world.write_text(_COLOCATED_WORLD)
    session = build_session(SessionConfig(seed=42, world_path=world))

    outcome = apply_input(session, "attack Goblin Scout")

    assert outcome.kind == "error"
    assert "combat" in (outcome.error or "").lower()
