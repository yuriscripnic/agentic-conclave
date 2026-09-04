"""In-memory GameRepository for MVP-0; PostgreSQL arrives in Plan 2."""

from __future__ import annotations

from domain.common.errors import GameNotFoundError
from domain.common.ids import GameId
from domain.world.game import Game


class InMemoryGameRepository:
    def __init__(self) -> None:
        self._games: dict[GameId, Game] = {}

    def save(self, game: Game) -> None:
        self._games[game.game_id] = game

    def get(self, game_id: GameId) -> Game:
        game = self._games.get(game_id)
        if game is None:
            raise GameNotFoundError(f"no game with id '{game_id}'")
        return game
