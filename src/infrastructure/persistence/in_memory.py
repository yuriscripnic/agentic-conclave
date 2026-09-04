"""In-memory GameRepository — same save contract as the PostgreSQL implementation."""

from __future__ import annotations

from collections.abc import Sequence

from domain.common.errors import GameNotFoundError
from domain.common.ids import GameId
from domain.events.collector import EventEnvelope
from domain.world.game import Game
from infrastructure.events.in_memory import InMemoryEventRepository


class InMemoryGameRepository:
    def __init__(self, event_store: InMemoryEventRepository) -> None:
        self._event_store = event_store
        self._games: dict[GameId, Game] = {}

    def save(self, game: Game, pending_events: Sequence[EventEnvelope]) -> None:
        # The store keeps the live aggregate object (MVP-0 semantics), so a
        # version conflict is impossible here; conflict semantics are covered
        # by the PostgreSQL tests. Version stamping matches the SQL contract.
        self._games[game.game_id] = game
        for envelope in pending_events:
            self._event_store.append(game.game_id, envelope)
        game.version += 1

    def get(self, game_id: GameId) -> Game:
        game = self._games.get(game_id)
        if game is None:
            raise GameNotFoundError(f"no game with id '{game_id}'")
        return game
