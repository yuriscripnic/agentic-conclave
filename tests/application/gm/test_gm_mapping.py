"""map_gm_response tests — cosmetic cleanup, never a game rejection (spec D8)."""

from typing import Any

import pytest

from application.gm.director import InvalidGmResponseError, map_gm_response
from application.gm.profiles import GmProfile
from application.views import CharacterView, GameView

_PROFILE = GmProfile(
    name="DM",
    style="Terse.",
    narration_max_chars=60,
    reply_max_chars=20,
    history_limit=12,
)


def _view() -> GameView:
    return GameView(
        game_id="game-1",
        campaign_name="The Forgotten Ruins",
        status="running",
        party=[
            CharacterView(
                id="p1",
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
                id="e1",
                name="Orc Brute",
                character_class=None,
                level=1,
                hp_current=18,
                hp_max=18,
                armor_class=13,
                conditions=[],
                is_defeated=False,
            ),
            CharacterView(
                id="e2",
                name="Fallen Goblin",
                character_class=None,
                level=1,
                hp_current=0,
                hp_max=7,
                armor_class=13,
                conditions=[],
                is_defeated=True,
            ),
        ],
        combat=None,
    )


def test_map_returns_clean_narration_and_reply() -> None:
    data: dict[str, Any] = {
        "narration": "The orc growls.",
        "npc_reply": "Fresh meat!",
        "addressed_to": "Orc Brute",
    }
    assert map_gm_response(data, _PROFILE, _view()) == (
        "The orc growls.",
        "Fresh meat!",
        "Orc Brute",
    )


def test_map_collapses_whitespace_and_truncates_to_caps() -> None:
    data = {"narration": "Line one.\n  Line   two.", "npc_reply": "x" * 30}
    narration, reply, addressed = map_gm_response(data, _PROFILE, _view())
    assert narration == "Line one. Line two."
    assert reply == "x" * 20
    assert addressed is None


def test_map_drops_addressed_to_that_is_not_a_living_enemy() -> None:
    defeated = {"narration": "n", "npc_reply": "r", "addressed_to": "Fallen Goblin"}
    assert map_gm_response(defeated, _PROFILE, _view())[2] is None
    unknown = {"narration": "n", "npc_reply": "r", "addressed_to": "Ghost"}
    assert map_gm_response(unknown, _PROFILE, _view())[2] is None


def test_map_allows_missing_optional_fields() -> None:
    data = {"narration": "Silence answers you."}
    assert map_gm_response(data, _PROFILE, _view()) == (
        "Silence answers you.",
        None,
        None,
    )


def test_map_raises_when_the_response_has_no_content() -> None:
    with pytest.raises(InvalidGmResponseError):
        map_gm_response({"narration": "   "}, _PROFILE, _view())
    with pytest.raises(InvalidGmResponseError):
        map_gm_response({}, _PROFILE, _view())


def test_map_raises_on_non_string_text() -> None:
    with pytest.raises(InvalidGmResponseError):
        map_gm_response({"narration": 123}, _PROFILE, _view())
