"""Port for event persistence — implemented in the infrastructure layer."""

from __future__ import annotations

from typing import Protocol

from domain.common.ids import GameId
from domain.events.collector import EventEnvelope


class EventRepository(Protocol):
    def append(self, game_id: GameId, envelope: EventEnvelope) -> None: ...

    def get_events(self, game_id: GameId) -> list[EventEnvelope]: ...
