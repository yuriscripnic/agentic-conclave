"""Deterministic travel resolution (spec Task 4).

LLMs and humans propose; TravelService decides: the actor must exist and be
alive, combat must not be active, and the named exit must exist from their
current location. Rejections emit ActionRejected and never mutate state.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from domain.common.errors import CharacterNotFoundError
from domain.common.ids import CharacterId, LocationId
from domain.events.base import BaseEvent
from domain.events.collector import EventCollector
from domain.events.events import ActionRejected
from domain.world.game import Game
from domain.world.locations import Location, WorldMap


@dataclass(frozen=True)
class CharacterArrived(BaseEvent):
    character_id: CharacterId
    to_location_id: LocationId
    from_location_id: LocationId | None


@dataclass(frozen=True)
class TravelProposal:
    actor_id: CharacterId
    direction: str


@dataclass(frozen=True)
class TravelResolution:
    accepted: bool
    reason: str
    location: Location | None
    events: tuple[BaseEvent, ...] = field(default_factory=tuple)


class TravelService:
    def __init__(self, world: WorldMap) -> None:
        self._world = world

    def resolve(
        self,
        game: Game,
        proposal: TravelProposal,
        *,
        combat_active: bool,
        collector: EventCollector,
    ) -> TravelResolution:
        try:
            actor = game.get_character(proposal.actor_id)
        except CharacterNotFoundError:
            return self._reject(game, proposal, collector, "unknown_character")
        if actor.is_defeated():
            return self._reject(game, proposal, collector, "unknown_character")
        if combat_active:
            return self._reject(game, proposal, collector, "combat_active")

        here = game.location_of(proposal.actor_id)
        destination_id: LocationId | None = None
        if here is not None:
            destination_id = self._world.get(here).is_exit_to(proposal.direction)
        if destination_id is None:
            return self._reject(game, proposal, collector, "unknown_exit")

        arrival = CharacterArrived(
            character_id=proposal.actor_id,
            to_location_id=destination_id,
            from_location_id=here,
        )
        collector.record(arrival)
        game.place(proposal.actor_id, destination_id)
        return TravelResolution(
            accepted=True,
            reason="",
            location=self._world.get(destination_id),
            events=(arrival,),
        )

    def _reject(
        self,
        game: Game,
        proposal: TravelProposal,
        collector: EventCollector,
        reason: str,
    ) -> TravelResolution:
        collector.record(
            ActionRejected(actor_id=proposal.actor_id, action_type="travel", reason=reason)
        )
        return TravelResolution(accepted=False, reason=reason, location=None, events=())
