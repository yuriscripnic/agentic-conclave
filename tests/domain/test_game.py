import pytest

from domain.character.abilities import AbilityScores
from domain.character.character import Character, CharacterClass, CharacterType
from domain.character.vitals import HitPoints
from domain.common.errors import CharacterNotFoundError, ValidationError
from domain.common.ids import CampaignId, CharacterId, GameId
from domain.common.ids import LocationId
from domain.world.game import Game, GameStatus


def _member(
    name: str,
    character_type: CharacterType,
    hp: int = 10,
) -> Character:
    return Character(
        id=CharacterId.generate(),
        name=name,
        character_type=character_type,
        character_class=CharacterClass.FIGHTER
        if character_type is CharacterType.PLAYER_CHARACTER
        else None,
        level=1,
        ability_scores=AbilityScores(
            strength=10,
            dexterity=10,
            constitution=10,
            intelligence=10,
            wisdom=10,
            charisma=10,
        ),
        armor_class=13,
        speed_ft=30,
        hit_points=HitPoints(current=hp, maximum=hp),
    )


def _game() -> Game:
    return Game(
        game_id=GameId.generate(),
        campaign_id=CampaignId.generate(),
        campaign_name="Test",
        seed=1,
    )


def test_add_party_member_and_enemy() -> None:
    game = _game()
    arin = _member("Arin", CharacterType.PLAYER_CHARACTER)
    goblin = _member("Goblin", CharacterType.MONSTER)
    game.add_party_member(arin)
    game.add_enemy(goblin)

    assert game.characters[arin.id] is arin
    assert game.party_ids == [arin.id]
    assert game.enemy_ids == [goblin.id]
    assert game.status is GameStatus.CREATED


def test_duplicate_id_and_name_are_rejected() -> None:
    game = _game()
    arin = _member("Arin", CharacterType.PLAYER_CHARACTER)
    game.add_party_member(arin)

    with pytest.raises(ValidationError):
        game.add_party_member(arin)  # same id
    with pytest.raises(ValidationError):
        game.add_party_member(_member("arin", CharacterType.PLAYER_CHARACTER))


def test_get_character_raises_for_unknown_id() -> None:
    game = _game()
    with pytest.raises(CharacterNotFoundError):
        game.get_character(CharacterId.generate())


def test_find_character_by_name_is_case_insensitive() -> None:
    game = _game()
    arin = _member("Arin", CharacterType.PLAYER_CHARACTER)
    game.add_party_member(arin)
    assert game.find_character_by_name("aRIN") is arin
    assert game.find_character_by_name("nobody") is None


def test_side_of_and_opponents_of() -> None:
    game = _game()
    arin = _member("Arin", CharacterType.PLAYER_CHARACTER)
    goblin = _member("Goblin", CharacterType.MONSTER)
    game.add_party_member(arin)
    game.add_enemy(goblin)

    assert game.side_of(arin.id) == "party"
    assert game.side_of(goblin.id) == "enemies"
    assert game.opponents_of(arin.id) == [goblin.id]
    assert game.opponents_of(goblin.id) == [arin.id]
    with pytest.raises(CharacterNotFoundError):
        game.side_of(CharacterId.generate())


def test_living_lists_filter_defeated() -> None:
    game = _game()
    arin = _member("Arin", CharacterType.PLAYER_CHARACTER)
    goblin1 = _member("Goblin-1", CharacterType.MONSTER)
    goblin2 = _member("Goblin-2", CharacterType.MONSTER)
    game.add_party_member(arin)
    game.add_enemy(goblin1)
    game.add_enemy(goblin2)

    goblin1.apply_damage(999)
    assert game.living_enemy_ids == [goblin2.id]
    assert game.living_party_ids == [arin.id]


def test_roster_cannot_change_after_start() -> None:
    game = _game()
    game.mark_started()
    with pytest.raises(ValidationError):
        game.add_party_member(_member("Late", CharacterType.PLAYER_CHARACTER))


def test_status_transitions() -> None:
    game = _game()
    game.mark_started()
    assert game.status is GameStatus.RUNNING
    game.mark_ended()
    assert game.status is GameStatus.ENDED


def test_game_version_defaults_to_zero_and_is_persistence_metadata() -> None:
    game = _game()
    assert game.version == 0
    # Persistence metadata: stamped by the repository, never read by rules.
    game.version = 3
    assert game.version == 3


def test_placements_place_and_residents() -> None:
    game = _game()
    first = _member("Arin", CharacterType.PLAYER_CHARACTER)
    second = _member("Brix", CharacterType.PLAYER_CHARACTER)
    game.add_party_member(first)
    game.add_party_member(second)
    location = LocationId.generate()

    game.place(first.id, location)

    assert game.location_of(first.id) == location
    assert game.location_of(second.id) is None
    assert game.residents_of(location) == [first.id]


def test_place_unknown_character_is_rejected() -> None:
    game = _game()
    with pytest.raises(CharacterNotFoundError):
        game.place(CharacterId.generate(), LocationId.generate())


def test_residents_only_count_living_combatants() -> None:
    game = _game()
    fighter = _member("Arin", CharacterType.PLAYER_CHARACTER)
    goblin = _member("Goblin", CharacterType.MONSTER, hp=1)
    game.add_party_member(fighter)
    game.add_enemy(goblin)
    location = LocationId.generate()
    game.place(fighter.id, location)
    game.place(goblin.id, location)
    goblin.apply_damage(1)
    assert game.residents_of(location) == [fighter.id]
