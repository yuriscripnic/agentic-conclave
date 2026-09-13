# tests/infrastructure/test_postgres_mapping.py
"""Aggregate ↔ row mapping roundtrips through domain constructors (spec §6)."""

import uuid

import pytest

from domain.character.abilities import AbilityScores
from domain.character.character import Character, CharacterClass, CharacterType
from domain.character.inventory import Inventory
from domain.character.vitals import HitPoints
from domain.character.weapon import Weapon
from domain.common.errors import ValidationError
from domain.common.ids import CampaignId, CharacterId, EventId, GameId, LocationId
from domain.events.collector import EventEnvelope
from domain.world.game import Game, GameStatus
from infrastructure.persistence.postgres.mapping import (
    event_to_row,
    game_from_row,
    game_to_row,
    row_to_event,
)


def _weapon() -> Weapon:
    return Weapon(
        weapon_id="longsword",
        name="Longsword",
        damage_die_count=1,
        damage_die_size=8,
    )


def _character(
    name: str,
    character_type: CharacterType,
    hp: int = 12,
) -> Character:
    return Character(
        id=CharacterId.generate(),
        name=name,
        character_type=character_type,
        character_class=(
            CharacterClass.FIGHTER
            if character_type is CharacterType.PLAYER_CHARACTER
            else None
        ),
        level=1,
        ability_scores=AbilityScores(
            strength=16,
            dexterity=13,
            constitution=15,
            intelligence=10,
            wisdom=12,
            charisma=9,
        ),
        armor_class=16,
        speed_ft=30,
        hit_points=HitPoints(current=hp, maximum=hp),
        conditions=("prone",),
        inventory=Inventory(gold=25),
        equipped_weapon=_weapon()
        if character_type is CharacterType.PLAYER_CHARACTER
        else None,
    )


def _full_game() -> Game:
    game = Game(
        game_id=GameId.generate(),
        campaign_id=CampaignId.generate(),
        campaign_name="The Forgotten Ruins",
        seed=42,
    )
    game.add_party_member(_character("Arin", CharacterType.PLAYER_CHARACTER, hp=12))
    game.add_enemy(_character("Goblin", CharacterType.MONSTER, hp=7))
    game.get_character(game.enemy_ids[0]).apply_damage(7)  # hp clamps to 0: defeated
    game.mark_started()
    game.version = 2  # simulate an aggregate that has already been saved twice
    return game


def test_game_roundtrip_preserves_every_field() -> None:
    game = _full_game()
    row = game_to_row(game)

    assert row["id"] == str(game.game_id)
    assert row["campaign_id"] == str(game.campaign_id)
    assert row["seed"] == 42
    assert row["version"] == 2
    assert row["status"] == "running"

    rebuilt = game_from_row(row)
    assert rebuilt.game_id == game.game_id
    assert rebuilt.campaign_id == game.campaign_id
    assert rebuilt.campaign_name == game.campaign_name
    assert rebuilt.seed == game.seed
    assert rebuilt.status is GameStatus.RUNNING
    assert rebuilt.version == 2
    assert rebuilt.party_ids == game.party_ids
    assert rebuilt.enemy_ids == game.enemy_ids

    for original in game.characters.values():
        clone = rebuilt.characters[original.id]
        assert clone.name == original.name
        assert clone.character_type is original.character_type
        assert clone.character_class is original.character_class
        assert clone.ability_scores == original.ability_scores
        assert clone.hit_points == original.hit_points
        assert clone.conditions == original.conditions
        assert clone.inventory == original.inventory
        assert clone.equipped_weapon == original.equipped_weapon
        assert clone.is_defeated() == original.is_defeated()


def test_row_document_holds_characters_and_sides() -> None:
    game = _full_game()
    document = game_to_row(game)["state"]
    assert isinstance(document, dict)
    assert len(document["characters"]) == 2
    assert document["party_ids"] == [str(cid) for cid in game.party_ids]
    assert document["enemy_ids"] == [str(cid) for cid in game.enemy_ids]
    assert document["characters"][0]["equipped_weapon"]["weapon_id"] == "longsword"
    assert document["characters"][0]["inventory"]["gold"] == 25
    assert document["status"] == "running"


def test_roundtrip_from_uuid_row_values() -> None:
    """psycopg returns uuid.UUID for uuid columns; the mapping must accept them."""
    game = _full_game()
    row = game_to_row(game)
    row["id"] = uuid.UUID(str(row["id"]))
    row["campaign_id"] = uuid.UUID(str(row["campaign_id"]))

    rebuilt = game_from_row(row)
    assert rebuilt.game_id == game.game_id


def test_corrupt_row_raises_validation_error() -> None:
    game = _full_game()

    tampered = game_to_row(game)
    tampered["state"]["characters"][0]["hit_points"]["maximum"] = 0  # domain-invalid
    with pytest.raises(ValidationError, match="corrupt persisted state"):
        game_from_row(tampered)

    missing = game_to_row(game)
    del missing["state"]["characters"][0]["name"]
    with pytest.raises(ValidationError, match="corrupt persisted state"):
        game_from_row(missing)


def test_event_envelope_roundtrip() -> None:
    game_id = GameId.generate()
    envelope = EventEnvelope(
        sequence=7,
        event_id=EventId.generate(),
        game_id=game_id,
        occurred_at="2026-01-01T00:00:00+00:00",
        event_type="attack_resolved",
        payload={"attacker_id": "a", "hit": True, "amount": 4},
    )
    row = event_to_row(game_id, envelope)
    assert row["game_id"] == str(game_id)
    assert row["sequence"] == 7
    assert row["event_type"] == "attack_resolved"
    assert row["payload"] == {"attacker_id": "a", "hit": True, "amount": 4}

    rebuilt = row_to_event(row, game_id)
    assert rebuilt == envelope


def test_game_state_document_carries_placements() -> None:
    game = Game(
        game_id=GameId.generate(),
        campaign_id=CampaignId.generate(),
        campaign_name="Ruins",
        seed=1,
    )
    fighter = _character("Arin", CharacterType.PLAYER_CHARACTER)
    game.add_party_member(fighter)
    location = LocationId.generate()
    game.place(fighter.id, location)

    row = game_to_row(game)
    assert row["state"]["placements"] == {str(fighter.id): str(location)}

    rebuilt = game_from_row(
        {
            "id": str(game.game_id),
            "campaign_id": str(game.campaign_id),
            "campaign_name": game.campaign_name,
            "seed": game.seed,
            "version": game.version,
            "status": game.status.value,
            "state": row["state"],
        }
    )
    assert rebuilt.placements == {fighter.id: location}


def test_game_from_row_defaults_missing_placements() -> None:
    with pytest.raises(ValidationError):
        game_from_row(
            {
                "id": str(GameId.generate()),
                "campaign_id": str(CampaignId.generate()),
                "campaign_name": "Ruins",
                "seed": 1,
                "version": 0,
                "status": "created",
                "state": {},
            }
        )
