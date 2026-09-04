"""Repository ports — implemented by infrastructure (CLAUDE.md §36)."""

from __future__ import annotations

from typing import Protocol

from domain.common.ids import GameId
from domain.world.game import Game


class GameRepository(Protocol):
    def save(self, game: Game) -> None: ...

    def get(self, game_id: GameId) -> Game: ...
