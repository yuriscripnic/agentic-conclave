"""Notable-event selection and digest-line tests (spec D3/D4)."""

from application.gm.director import digest_lines, notable_events
from application.views import CharacterView, GameView, TurnReport
from domain.common.ids import EventId, GameId
from domain.events.collector import EventEnvelope

_GAME_ID = GameId("00000000-0000-0000-0000-000000000001")

_NAMES = {
    "11111111-1111-1111-1111-111111111111": "Arin",
    "22222222-2222-2222-2222-222222222222": "Orc Brute",
}


def _envelope(sequence: int, event_type: str, payload: dict[str, object]) -> EventEnvelope:
    return EventEnvelope(
        sequence=sequence,
        event_id=EventId.generate(),
        game_id=_GAME_ID,
        occurred_at="2026-09-08T00:00:00+00:00",
        event_type=event_type,
        payload=payload,
    )


def _view() -> GameView:
    return GameView(
        game_id="00000000-0000-0000-0000-000000000001",
        campaign_name="The Forgotten Ruins",
        status="running",
        party=[
            CharacterView(
                id="11111111-1111-1111-1111-111111111111",
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
                id="22222222-2222-2222-2222-222222222222",
                name="Orc Brute",
                character_class=None,
                level=1,
                hp_current=18,
                hp_max=18,
                armor_class=13,
                conditions=[],
                is_defeated=False,
            )
        ],
        combat=None,
    )


def _report(events: list[EventEnvelope]) -> TurnReport:
    return TurnReport(
        game_id="00000000-0000-0000-0000-000000000001",
        accepted=True,
        error_code="",
        reason="",
        events=events,
        view=_view(),
        game_over=False,
    )


def test_notable_events_picks_critical_defeat_and_combat_end() -> None:
    events = [
        _envelope(
            1,
            "attack_resolved",
            {
                "attacker_id": "11111111-1111-1111-1111-111111111111",
                "target_id": "22222222-2222-2222-2222-222222222222",
                "roll": 20,
                "attack_bonus": 5,
                "total": 25,
                "target_ac": 13,
                "hit": True,
                "critical": True,
            },
        ),
        _envelope(
            2,
            "character_defeated",
            {"character_id": "22222222-2222-2222-2222-222222222222"},
        ),
        _envelope(3, "combat_ended", {"winner_side": "party", "round_number": 3}),
    ]
    notable = notable_events(_report(events))
    assert [envelope.event_type for envelope in notable] == [
        "attack_resolved",
        "character_defeated",
        "combat_ended",
    ]


def test_notable_events_ignores_plain_hits_damage_and_rejections() -> None:
    events = [
        _envelope(
            1,
            "attack_resolved",
            {
                "attacker_id": "11111111-1111-1111-1111-111111111111",
                "target_id": "22222222-2222-2222-2222-222222222222",
                "roll": 14,
                "attack_bonus": 5,
                "total": 15,
                "target_ac": 13,
                "hit": True,
                "critical": False,
            },
        ),
        _envelope(
            2,
            "damage_applied",
            {
                "character_id": "22222222-2222-2222-2222-222222222222",
                "amount": 6,
                "hp_before": 18,
                "hp_after": 12,
            },
        ),
        _envelope(3, "action_rejected", {"reason": "no such character"}),
        _envelope(4, "initiative_rolled", {"round_number": 1}),
    ]
    assert notable_events(_report(events)) == []


def test_digest_lines_name_actors_and_outcomes() -> None:
    events = [
        _envelope(
            1,
            "attack_resolved",
            {
                "attacker_id": "11111111-1111-1111-1111-111111111111",
                "target_id": "22222222-2222-2222-2222-222222222222",
                "roll": 20,
                "attack_bonus": 5,
                "total": 25,
                "target_ac": 13,
                "hit": True,
                "critical": True,
            },
        ),
        _envelope(3, "combat_ended", {"winner_side": "party", "round_number": 3}),
    ]
    assert digest_lines(events, _NAMES) == [
        "Arin landed a CRITICAL hit on Orc Brute (25 vs AC 13).",
        "Combat ended in round 3: party wins.",
    ]


def test_digest_lines_skip_non_notable_events() -> None:
    events = [
        _envelope(
            1,
            "attack_resolved",
            {
                "attacker_id": "11111111-1111-1111-1111-111111111111",
                "target_id": "22222222-2222-2222-2222-222222222222",
                "roll": 14,
                "attack_bonus": 5,
                "total": 15,
                "target_ac": 13,
                "hit": True,
                "critical": False,
            },
        ),
        _envelope(
            2,
            "character_defeated",
            {"character_id": "22222222-2222-2222-2222-222222222222"},
        ),
    ]
    assert digest_lines(events, _NAMES) == ["Orc Brute is defeated."]
