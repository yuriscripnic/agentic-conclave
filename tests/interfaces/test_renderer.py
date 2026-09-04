# tests/interfaces/test_renderer.py
from io import StringIO

from rich.console import Console

from application.views import (
    CharacterView,
    CombatView,
    GameView,
    InitiativeEntryView,
)
from domain.common.ids import EventId, GameId
from domain.events.collector import EventEnvelope
from interfaces.cli.renderer import describe_event, render_game_view


def _console() -> tuple[Console, StringIO]:
    buffer = StringIO()
    return Console(file=buffer, width=100, force_terminal=False), buffer


def _view() -> GameView:
    return GameView(
        game_id="game-1",
        campaign_name="The Forgotten Ruins",
        status="running",
        party=[
            CharacterView(
                id="c1",
                name="Arin",
                character_class="fighter",
                level=1,
                hp_current=12,
                hp_max=12,
                armor_class=16,
                conditions=[],
                is_defeated=False,
            )
        ],
        enemies=[
            CharacterView(
                id="c2",
                name="Goblin",
                character_class=None,
                level=1,
                hp_current=3,
                hp_max=7,
                armor_class=13,
                conditions=[],
                is_defeated=False,
            )
        ],
        combat=CombatView(
            round_number=1,
            status="active",
            active_actor_id="c1",
            initiative_order=[
                InitiativeEntryView(character_id="c1", name="Arin", total=5),
                InitiativeEntryView(character_id="c2", name="Goblin", total=3),
            ],
        ),
    )


def test_render_game_view_shows_rosters_and_combat() -> None:
    console, buffer = _console()
    render_game_view(console, _view())
    output = buffer.getvalue()
    assert "Arin" in output
    assert "Goblin" in output
    assert "Round 1" in output
    assert "12/12" in output
    assert "3/7" in output
    assert "Arin (5)" in output


def test_render_game_view_without_combat() -> None:
    console, buffer = _console()
    view = GameView(
        game_id="game-1",
        campaign_name="Ruins",
        status="created",
        party=[],
        enemies=[],
        combat=None,
    )
    render_game_view(console, view)
    assert "Ruins" in buffer.getvalue()


def _envelope(event_type: str, payload: dict[str, object]) -> EventEnvelope:
    return EventEnvelope(
        sequence=1,
        event_id=EventId.generate(),
        game_id=GameId.generate(),
        occurred_at="2026-01-01T00:00:00+00:00",
        event_type=event_type,
        payload=payload,
    )


def test_describe_attack_resolved() -> None:
    line = describe_event(
        _envelope(
            "attack_resolved",
            {
                "attacker_id": "c1",
                "target_id": "c2",
                "roll": 15,
                "attack_bonus": 5,
                "total": 20,
                "target_ac": 13,
                "hit": True,
                "critical": False,
            },
        ),
        {"c1": "Arin", "c2": "Goblin"},
    )
    assert line == "⚔ Arin attacks Goblin: d20 15 +5 = 20 vs AC 13 — HIT"


def test_describe_damage_and_defeat() -> None:
    damage = describe_event(
        _envelope(
            "damage_applied",
            {"character_id": "c2", "amount": 4, "hp_before": 7, "hp_after": 3},
        ),
        {"c2": "Goblin"},
    )
    assert damage == "💥 Goblin takes 4 damage (7 → 3)"

    defeat = describe_event(
        _envelope("character_defeated", {"character_id": "c2"}), {"c2": "Goblin"}
    )
    assert defeat == "☠ Goblin is defeated!"


def test_describe_rejection_and_combat_end() -> None:
    rejected = describe_event(
        _envelope(
            "action_rejected",
            {"actor_id": "c1", "action_type": "attack", "reason": "not your turn"},
        ),
        {},
    )
    assert rejected == "✗ Action rejected: not your turn"

    ended = describe_event(
        _envelope("combat_ended", {"winner_side": "party", "round_number": 2}), {}
    )
    assert ended == "🏆 party wins the combat in round 2!"


def test_undescribed_events_return_none() -> None:
    assert (
        describe_event(
            _envelope("turn_started", {"round_number": 1, "actor_id": "c1"}), {}
        )
        is None
    )
