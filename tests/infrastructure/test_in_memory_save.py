# tests/infrastructure/test_in_memory_save.py
"""In-memory repositories implement the same save contract as PostgreSQL (spec §10)."""

from domain.common.ids import CampaignId, GameId
from domain.events.collector import EventCollector
from domain.events.events import GameCreated
from domain.world.game import Game
from infrastructure.events.in_memory import InMemoryEventRepository
from infrastructure.persistence.in_memory import InMemoryGameRepository


def _game() -> Game:
    return Game(
        game_id=GameId.generate(),
        campaign_id=CampaignId.generate(),
        campaign_name="Ruins",
        seed=42,
    )


def test_save_stamps_version_and_persists_events() -> None:
    event_store = InMemoryEventRepository()
    repository = InMemoryGameRepository(event_store)
    game = _game()
    collector = EventCollector(game_id=game.game_id)
    collector.record(GameCreated(campaign_id=game.campaign_id, seed=42))
    pending = collector.drain()

    repository.save(game, pending)

    assert game.version == 1
    assert repository.get(game.game_id) is game
    assert [e.event_type for e in event_store.get_events(game.game_id)] == [
        "game_created"
    ]


def test_save_with_empty_pending_events_is_normal() -> None:
    event_store = InMemoryEventRepository()
    repository = InMemoryGameRepository(event_store)
    game = _game()

    repository.save(game, [])

    assert repository.get(game.game_id) is game
    assert game.version == 1
    assert event_store.get_events(game.game_id) == []


def test_version_increments_across_saves() -> None:
    event_store = InMemoryEventRepository()
    repository = InMemoryGameRepository(event_store)
    game = _game()

    repository.save(game, [])
    repository.save(game, [])

    assert game.version == 2
