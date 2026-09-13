"""Game aggregate — authoritative current state (CLAUDE.md §10, §11)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from domain.character.character import Character
from domain.common.errors import CharacterNotFoundError, ValidationError
from domain.common.ids import CampaignId, CharacterId, GameId, LocationId


class GameStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    ENDED = "ended"


@dataclass
class Game:
    game_id: GameId
    campaign_id: CampaignId
    campaign_name: str
    seed: int
    characters: dict[CharacterId, Character] = field(default_factory=dict)
    party_ids: list[CharacterId] = field(default_factory=list)
    enemy_ids: list[CharacterId] = field(default_factory=list)
    status: GameStatus = GameStatus.CREATED
    # Per-character world placement. Empty until a world catalog is supplied;
    # a missing entry means "no placement" (legacy single-scene games).
    placements: dict[CharacterId, LocationId] = field(default_factory=dict)
    # Persistence metadata: stamped (+1) by the repository after each committed
    # save; the optimistic-lock token for atomic writes. Domain rules never read it.
    version: int = 0

    def add_party_member(self, character: Character) -> None:
        self._add_member(character)
        self.party_ids.append(character.id)

    def add_enemy(self, character: Character) -> None:
        self._add_member(character)
        self.enemy_ids.append(character.id)

    def _add_member(self, character: Character) -> None:
        if self.status is not GameStatus.CREATED:
            raise ValidationError(
                "cannot modify the roster after the game has started"
            )
        if character.id in self.characters:
            raise ValidationError(
                f"character '{character.id}' already exists in this game"
            )
        if self.find_character_by_name(character.name) is not None:
            raise ValidationError(
                f"a character named '{character.name}' already exists"
            )
        self.characters[character.id] = character

    def get_character(self, character_id: CharacterId) -> Character:
        character = self.characters.get(character_id)
        if character is None:
            raise CharacterNotFoundError(f"no character with id '{character_id}'")
        return character

    def find_character_by_name(self, name: str) -> Character | None:
        lowered = name.strip().lower()
        for character in self.characters.values():
            if character.name.lower() == lowered:
                return character
        return None

    def side_of(self, character_id: CharacterId) -> str:
        if character_id in self.party_ids:
            return "party"
        if character_id in self.enemy_ids:
            return "enemies"
        raise CharacterNotFoundError(f"character '{character_id}' is not a combatant")

    def opponents_of(self, character_id: CharacterId) -> list[CharacterId]:
        if self.side_of(character_id) == "party":
            return list(self.enemy_ids)
        return list(self.party_ids)

    @property
    def living_party_ids(self) -> list[CharacterId]:
        return [
            cid for cid in self.party_ids if not self.characters[cid].is_defeated()
        ]

    @property
    def living_enemy_ids(self) -> list[CharacterId]:
        return [
            cid for cid in self.enemy_ids if not self.characters[cid].is_defeated()
        ]

    def mark_started(self) -> None:
        self.status = GameStatus.RUNNING

    def mark_ended(self) -> None:
        self.status = GameStatus.ENDED

    def place(self, character_id: CharacterId, location_id: LocationId) -> None:
        self.get_character(character_id)
        self.placements[character_id] = location_id

    def location_of(self, character_id: CharacterId) -> LocationId | None:
        return self.placements.get(character_id)

    def residents_of(self, location_id: LocationId) -> list[CharacterId]:
        return [
            cid
            for cid in (*self.party_ids, *self.enemy_ids)
            if cid in self.characters
            and not self.characters[cid].is_defeated()
            and self.placements.get(cid) == location_id
        ]
