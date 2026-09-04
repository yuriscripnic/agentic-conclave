"""In-memory EventRepository implementation for MVP-0."""

from __future__ import annotations

from domain.common.ids import GameId
from domain.events.collector import EventEnvelope


class InMemoryEventRepository:
    def __init__(self) -> None:
        self._events: dict[GameId, list[EventEnvelope]] = {}

    def append(self, game_id: GameId, envelope: EventEnvelope) -> None:
        self._events.setdefault(game_id, []).append(envelope)

    def get_events(self, game_id: GameId) -> list[EventEnvelope]:
        return list(self._events.get(game_id, []))
