"""Perception projection tests — the §20 information-asymmetry boundary."""

from dataclasses import fields, replace

import pytest

from application.agents.perception import (
    AgentNotInCombatError,
    OpponentBrief,
    build_perception,
    first_living_opponent,
)
from application.views import (
    CharacterView,
    CombatView,
    GameView,
    InitiativeEntryView,
)


def _character(character_id: str, name: str, *, defeated: bool = False) -> CharacterView:
    return CharacterView(
        id=character_id,
        name=name,
        character_class=None if name == "Goblin" else "fighter",
        level=1,
        hp_current=0 if defeated else 5,
        hp_max=12,
        armor_class=16,
        conditions=[],
        is_defeated=defeated,
    )


def _view(*, active: str = "brix", goblin_defeated: bool = False) -> GameView:
    combat = CombatView(
        round_number=2,
        status="active",
        active_actor_id=active,
        initiative_order=[
            InitiativeEntryView(character_id="brix", name="Brix", total=18),
            InitiativeEntryView(character_id="gob", name="Goblin", total=9),
        ],
    )
    return GameView(
        game_id="g1",
        campaign_name="The Forgotten Ruins",
        status="running",
        party=[_character("arin", "Arin"), _character("brix", "Brix")],
        enemies=[_character("gob", "Goblin", defeated=goblin_defeated)],
        combat=combat,
    )


def test_perception_projects_self_and_opponent_briefs() -> None:
    perception = build_perception(_view(), "brix")
    assert perception.round_number == 2
    assert perception.active_actor_id == "brix"
    assert perception.self_view.id == "brix"
    assert perception.self_view.hp_current == 5
    assert perception.opponents == (
        OpponentBrief(id="gob", name="Goblin", is_defeated=False),
    )
    assert perception.initiative_order == ("Brix", "Goblin")


def test_opponent_briefs_carry_no_hp_or_ac() -> None:
    perception = build_perception(_view(), "brix")
    brief_fields = {field.name for field in fields(OpponentBrief)}
    assert brief_fields == {"id", "name", "is_defeated"}
    brief = perception.opponents[0]
    assert not hasattr(brief, "hp_current")
    assert not hasattr(brief, "armor_class")


def test_not_your_turn_raises() -> None:
    with pytest.raises(AgentNotInCombatError):
        build_perception(_view(active="arin"), "brix")


def test_no_active_combat_raises() -> None:
    view = _view(active="brix")
    with pytest.raises(AgentNotInCombatError):
        build_perception(replace(view, combat=None), "brix")


def test_enemy_side_actor_is_supported() -> None:
    perception = build_perception(_view(active="gob"), "gob")
    assert perception.self_view.id == "gob"
    assert {opponent.id for opponent in perception.opponents} == {"arin", "brix"}


def test_first_living_opponent_from_party_side() -> None:
    assert first_living_opponent(_view(), "brix") == "gob"


def test_first_living_opponent_returns_none_when_all_defeated() -> None:
    assert first_living_opponent(_view(goblin_defeated=True), "brix") is None


def test_first_living_opponent_from_enemy_side() -> None:
    assert first_living_opponent(_view(active="gob"), "gob") == "arin"
