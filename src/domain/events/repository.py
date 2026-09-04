"""Port for event persistence — implemented in the infrastructure layer.

The write path is GameRepository.save (events travel with the aggregate so
they commit atomically); this protocol is read-only.
"""

from __future__ import annotations

from typing import Protocol

from domain.common.ids import GameId
from domain.events.collector import EventEnvelope


class EventRepository(Protocol):
    def get_events(self, game_id: GameId) -> list[EventEnvelope]: ...
