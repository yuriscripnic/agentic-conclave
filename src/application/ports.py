"""Repository ports — implemented by infrastructure (CLAUDE.md §36)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from domain.common.ids import GameId
from domain.events.collector import EventEnvelope
from domain.world.game import Game


class GameRepository(Protocol):
    def save(self, game: Game, pending_events: Sequence[EventEnvelope]) -> None:
        """Atomically persist the aggregate and append pending events.

        Single transaction (spec §7): optimistic-lock the row on game.version,
        insert pending events, commit; on success stamp game.version += 1.
        A version conflict raises ConcurrentGameModification and persists nothing.
        pending_events may be empty (e.g. add_character persists with no events).
        """

    def get(self, game_id: GameId) -> Game: ...
