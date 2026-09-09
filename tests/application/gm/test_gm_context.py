"""build_gm_context tests — persona, hard rules, scene, digest, history (spec D7)."""

from application.gm.conversation import GmMessage
from application.gm.director import build_gm_context, digest_lines
from application.gm.profiles import GmProfile
from application.views import CharacterView, GameView
from domain.common.ids import EventId, GameId
from domain.events.collector import EventEnvelope

_PROFILE = GmProfile(
    name="The Dungeon Master",
    style="Terse, vivid second-person narration.",
    narration_max_chars=280,
    reply_max_chars=200,
    history_limit=12,
)

_GAME_ID = GameId("00000000-0000-0000-0000-000000000001")

_NAMES = {
    "11111111-1111-1111-1111-111111111111": "Arin",
    "22222222-2222-2222-2222-222222222222": "Orc Brute",
}


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


def _envelope(sequence: int, event_type: str, payload: dict[str, object]) -> EventEnvelope:
    return EventEnvelope(
        sequence=sequence,
        event_id=EventId.generate(),
        game_id=_GAME_ID,
        occurred_at="2026-09-08T00:00:00+00:00",
        event_type=event_type,
        payload=payload,
    )


def test_system_prompt_carries_persona_and_hard_rules() -> None:
    system, _user = build_gm_context(_PROFILE, _view(), [], (), "narrate_open")
    assert "You are The Dungeon Master" in system
    assert "Terse, vivid second-person narration." in system
    assert "never invent dice results" in system
    assert "Never propose or execute game actions" in system


def test_user_prompt_contains_task_scene_digest_and_history() -> None:
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
    ]
    digest = digest_lines(events, _NAMES)
    history = (GmMessage(speaker="player", text="Parley?"),)
    _system, user = build_gm_context(
        _PROFILE, _view(), digest, history, "react_to_events"
    )
    assert "Task: react_to_events" in user
    assert "- Arin (fighter): 12/12 HP" in user
    assert "- Orc Brute (?): 18/18 HP" in user
    assert "- Arin landed a CRITICAL hit on Orc Brute (25 vs AC 13)." in user
    assert "- player: Parley?" in user
    assert "Narrate a short reaction" in user


def test_user_prompt_excludes_non_notable_event_detail() -> None:
    """§20 leak check: a plain hit's numbers never reach the prompt."""
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
    ]
    digest = digest_lines(events, _NAMES)
    _system, user = build_gm_context(
        _PROFILE, _view(), digest, (), "react_to_events"
    )
    assert "15" not in user
    assert "25 vs AC 13" in user
