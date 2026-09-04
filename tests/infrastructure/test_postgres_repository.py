# tests/infrastructure/test_postgres_repository.py
"""Optimistic locking, atomic saves, and event integrity against real PostgreSQL."""

import copy

import pytest

from domain.character.abilities import AbilityScores
from domain.character.character import Character, CharacterClass, CharacterType
from domain.character.vitals import HitPoints
from domain.character.weapon import Weapon
from domain.common.errors import (
    ConcurrentGameModification,
    GameNotFoundError,
    PersistenceError,
)
from domain.common.ids import CampaignId, CharacterId, EventId, GameId
from domain.events.collector import EventEnvelope
from domain.world.game import Game
from infrastructure.persistence.postgres.connection import connect
from infrastructure.persistence.postgres.repository import (
    PostgresEventRepository,
    PostgresGameRepository,
)


def _party_member() -> Character:
    return Character(
        id=CharacterId.generate(),
        name="Arin",
        character_type=CharacterType.PLAYER_CHARACTER,
        character_class=CharacterClass.FIGHTER,
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
        hit_points=HitPoints(current=12, maximum=12),
        equipped_weapon=Weapon(
            weapon_id="longsword", name="Longsword",
            damage_die_count=1, damage_die_size=8,
        ),
    )


def _game() -> Game:
    game = Game(
        game_id=GameId.generate(),
        campaign_id=CampaignId.generate(),
        campaign_name="Ruins",
        seed=42,
    )
    game.add_party_member(_party_member())
    return game


def _envelope(game_id: GameId, sequence: int, event_type: str) -> EventEnvelope:
    return EventEnvelope(
        sequence=sequence,
        event_id=EventId.generate(),
        game_id=game_id,
        occurred_at="2026-01-01T00:00:00+00:00",
        event_type=event_type,
        payload={"sequence": sequence},
    )


def test_save_and_get_roundtrip_full_aggregate(postgres_url: str) -> None:
    connection = connect(postgres_url)
    repository = PostgresGameRepository(connection)
    game = _game()
    game.mark_started()
    game.get_character(game.party_ids[0]).apply_damage(5)

    repository.save(game, [])
    loaded = repository.get(game.game_id)

    assert loaded.game_id == game.game_id
    assert loaded.status == game.status
    assert loaded.version == game.version
    original = game.get_character(game.party_ids[0])
    clone = loaded.get_character(loaded.party_ids[0])
    assert clone.name == original.name
    assert clone.hit_points == original.hit_points
    assert clone.equipped_weapon == original.equipped_weapon
    connection.close()


def test_save_stamps_version_incrementally(postgres_url: str) -> None:
    connection = connect(postgres_url)
    repository = PostgresGameRepository(connection)
    game = _game()

    assert game.version == 0
    repository.save(game, [])
    assert game.version == 1
    repository.save(game, [])
    assert game.version == 2
    assert repository.get(game.game_id).version == 2
    connection.close()


def test_stale_version_save_raises_and_persists_nothing(postgres_url: str) -> None:
    connection = connect(postgres_url)
    repository = PostgresGameRepository(connection)
    game = _game()
    repository.save(game, [])  # version -> 1

    stale = copy.deepcopy(game)
    stale.get_character(stale.party_ids[0]).apply_damage(9)
    stale.version = 0  # pretend this replica never saw the first save

    with pytest.raises(ConcurrentGameModification):
        repository.save(stale, [])

    loaded = repository.get(game.game_id)
    assert loaded.version == 1
    assert loaded.get_character(loaded.party_ids[0]).hit_points.current == 12
    connection.close()


def test_events_are_contiguous_across_saves(postgres_url: str) -> None:
    connection = connect(postgres_url)
    games = PostgresGameRepository(connection)
    events = PostgresEventRepository(connection)
    game = _game()
    game.mark_started()

    games.save(
        game,
        [
            _envelope(game.game_id, 1, "game_created"),
            _envelope(game.game_id, 2, "game_started"),
        ],
    )
    games.save(game, [_envelope(game.game_id, 3, "combat_started")])

    stored = events.get_events(game.game_id)
    assert [e.sequence for e in stored] == [1, 2, 3]
    assert [e.event_type for e in stored] == [
        "game_created",
        "game_started",
        "combat_started",
    ]
    assert all(e.game_id == game.game_id for e in stored)
    connection.close()


def test_duplicate_sequence_insert_is_rejected(postgres_url: str) -> None:
    connection = connect(postgres_url)
    games = PostgresGameRepository(connection)
    game = _game()
    games.save(game, [_envelope(game.game_id, 1, "game_created")])

    with pytest.raises(PersistenceError):
        games.save(game, [_envelope(game.game_id, 1, "game_started")])

    loaded = games.get(game.game_id)
    assert loaded.version == 1  # the failed save left the aggregate untouched
    connection.close()


def test_get_events_for_unknown_game_is_empty(postgres_url: str) -> None:
    connection = connect(postgres_url)
    events = PostgresEventRepository(connection)
    assert events.get_events(GameId.generate()) == []
    connection.close()


def test_get_unknown_game_raises_game_not_found(postgres_url: str) -> None:
    connection = connect(postgres_url)
    repository = PostgresGameRepository(connection)
    with pytest.raises(GameNotFoundError):
        repository.get(GameId.generate())
    connection.close()
