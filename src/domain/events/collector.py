"""Collects events in sequence for a single game."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from domain.common.ids import EventId, GameId
from domain.events.base import GameEvent


@dataclass(frozen=True)
class EventEnvelope:
    sequence: int
    event_id: EventId
    game_id: GameId
    occurred_at: str
    event_type: str
    payload: dict[str, object]


class EventCollector:
    def __init__(
        self, game_id: GameId, clock: Callable[[], datetime] | None = None
    ) -> None:
        self._game_id = game_id
        self._clock: Callable[[], datetime] = clock or (lambda: datetime.now(UTC))
        self._sequence = 0
        self._pending: list[EventEnvelope] = []
        self._recorded: list[EventEnvelope] = []

    def record(self, event: GameEvent) -> EventEnvelope:
        self._sequence += 1
        envelope = EventEnvelope(
            sequence=self._sequence,
            event_id=EventId.generate(),
            game_id=self._game_id,
            occurred_at=self._clock().isoformat(),
            event_type=event.event_type,
            payload=event.to_payload(),
        )
        self._pending.append(envelope)
        self._recorded.append(envelope)
        return envelope

    @property
    def events(self) -> list[EventEnvelope]:
        return list(self._recorded)

    def drain(self) -> list[EventEnvelope]:
        drained = self._pending
        self._pending = []
        return drained
