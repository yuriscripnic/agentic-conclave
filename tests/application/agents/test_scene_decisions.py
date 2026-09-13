"""map_scene_decision + validate_scene_decision (Task 7)."""

import pytest

from application.agents.scene_decisions import (
    InvalidSceneDecisionError,
    map_scene_decision,
    validate_scene_decision,
)
from domain.character.abilities import AbilityScores
from domain.character.character import Character, CharacterClass, CharacterType
from domain.character.vitals import HitPoints
from domain.common.ids import CampaignId, CharacterId, GameId, LocationId
from domain.world.game import Game
from domain.world.locations import Location, LocationExit, WorldMap


def _world() -> WorldMap:
    tower = Location(id=LocationId.generate(), name="Tower", description="", exits=())
    courtyard = Location(
        id=LocationId.generate(),
        name="Courtyard",
        description="",
        exits=(LocationExit(direction="north", destination=tower.id),),
    )
    return WorldMap(
        locations={courtyard.id: courtyard, tower.id: tower},
        start_id=courtyard.id,
    )


def _game_with_hero(world: WorldMap) -> tuple[Game, CharacterId]:
    game = Game(
        game_id=GameId.generate(),
        campaign_id=CampaignId.generate(),
        campaign_name="Test",
        seed=1,
    )
    hero = Character(
        id=CharacterId.generate(),
        name="Mira",
        character_type=CharacterType.PLAYER_CHARACTER,
        character_class=CharacterClass.WIZARD,
        level=1,
        ability_scores=AbilityScores(
            strength=10, dexterity=10, constitution=10,
            intelligence=12, wisdom=10, charisma=10,
        ),
        armor_class=12,
        speed_ft=30,
        hit_points=HitPoints(current=8, maximum=8),
    )
    game.add_party_member(hero)
    game.mark_started()
    game.place(hero.id, world.start_id)
    return game, hero.id


def test_map_valid_talk_decision() -> None:
    decision = map_scene_decision(
        {"action_type": "talk", "speech": "Hello!", "public_message": "waves"}
    )
    assert decision.action_type == "talk"
    assert decision.speech == "Hello!"


def test_map_travel_without_direction_is_rejected() -> None:
    with pytest.raises(InvalidSceneDecisionError):
        map_scene_decision({"action_type": "travel", "public_message": "off I go"})


def test_map_talk_without_speech_is_rejected() -> None:
    with pytest.raises(InvalidSceneDecisionError):
        map_scene_decision({"action_type": "talk", "public_message": "hi"})


def test_map_unknown_action_type_is_rejected() -> None:
    with pytest.raises(InvalidSceneDecisionError):
        map_scene_decision({"action_type": "hack", "public_message": "no"})


def test_validate_wait_is_legal_without_exits() -> None:
    decision = map_scene_decision({"action_type": "wait", "public_message": "rest"})
    world = _world()
    game, hero_id = _game_with_hero(world)
    assert validate_scene_decision(decision, game, world, hero_id) is None


def test_validate_travel_to_unknown_exit_is_rejected() -> None:
    decision = map_scene_decision(
        {"action_type": "travel", "exit_direction": "west", "public_message": "hmm"}
    )
    world = _world()
    game, hero_id = _game_with_hero(world)
    assert validate_scene_decision(decision, game, world, hero_id) == "unknown_exit"


def test_validate_travel_to_known_exit_is_legal() -> None:
    decision = map_scene_decision(
        {"action_type": "travel", "exit_direction": "north", "public_message": "forward"}
    )
    world = _world()
    game, hero_id = _game_with_hero(world)
    assert validate_scene_decision(decision, game, world, hero_id) is None


def test_validate_travel_through_wall_trimmed_direction() -> None:
    decision = map_scene_decision(
        {"action_type": "travel", "exit_direction": "NORTH", "public_message": "up"}
    )
    world = _world()
    game, hero_id = _game_with_hero(world)
    assert validate_scene_decision(decision, game, world, hero_id) is None
