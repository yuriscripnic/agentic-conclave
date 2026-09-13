"""Data-driven locations: the authoritative world graph (pure domain)."""

from dataclasses import dataclass

from domain.common.ids import LocationId


@dataclass(frozen=True)
class LocationExit:
    direction: str
    destination: LocationId


@dataclass(frozen=True)
class Location:
    id: LocationId
    name: str
    description: str
    exits: tuple[LocationExit, ...]

    def exit(self, direction: str) -> LocationExit | None:
        wanted = direction.casefold()
        for candidate in self.exits:
            if candidate.direction.casefold() == wanted:
                return candidate
        return None

    def is_exit_to(self, direction: str) -> LocationId | None:
        found = self.exit(direction)
        return found.destination if found else None


@dataclass
class WorldMap:
    locations: dict[LocationId, Location]
    start_id: LocationId
    # Optional " where the encounter enemies wait" marker from config; the
    # application layer uses it to place monsters at session build time.
    enemies_at: LocationId | None = None

    def get(self, location_id: LocationId) -> Location:
        return self.locations[location_id]

    def by_name(self, name: str) -> Location | None:
        wanted = name.casefold()
        for location in self.locations.values():
            if location.name.casefold() == wanted:
                return location
        return None
