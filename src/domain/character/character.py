"""Character aggregate — what exists in the game (CLAUDE.md §16: Character ≠ Agent)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from domain.character.abilities import AbilityScores
from domain.character.inventory import Inventory
from domain.character.vitals import HitPoints
from domain.character.weapon import Weapon
from domain.common.errors import ValidationError
from domain.common.ids import CharacterId
from domain.rules.progression import MAX_LEVEL, MIN_LEVEL

MIN_AC = 1
MAX_AC = 30
MIN_SPEED_FT = 1
MAX_SPEED_FT = 120


class CharacterType(StrEnum):
    PLAYER_CHARACTER = "player_character"
    MONSTER = "monster"
    NPC = "npc"


class CharacterClass(StrEnum):
    FIGHTER = "fighter"
    ROGUE = "rogue"
    WIZARD = "wizard"
    CLERIC = "cleric"


@dataclass
class Character:
    id: CharacterId
    name: str
    character_type: CharacterType
    character_class: CharacterClass | None
    level: int
    ability_scores: AbilityScores
    armor_class: int
    speed_ft: int
    hit_points: HitPoints
    conditions: tuple[str, ...] = ()
    inventory: Inventory = field(default_factory=Inventory)
    equipped_weapon: Weapon | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValidationError("character name must be a non-empty string")
        if not MIN_LEVEL <= self.level <= MAX_LEVEL:
            raise ValidationError(
                f"level must be between {MIN_LEVEL} and {MAX_LEVEL}, got {self.level}"
            )
        if not MIN_AC <= self.armor_class <= MAX_AC:
            raise ValidationError(
                f"armor class must be between {MIN_AC} and {MAX_AC},"
                f" got {self.armor_class}"
            )
        if not MIN_SPEED_FT <= self.speed_ft <= MAX_SPEED_FT:
            raise ValidationError(
                f"speed must be between {MIN_SPEED_FT} and {MAX_SPEED_FT} feet,"
                f" got {self.speed_ft}"
            )
        if self.character_type is CharacterType.PLAYER_CHARACTER and (
            self.character_class is None
        ):
            raise ValidationError("player characters must have a character class")

    def is_defeated(self) -> bool:
        return self.hit_points.is_defeated

    def apply_damage(self, amount: int) -> None:
        self.hit_points = self.hit_points.apply_damage(amount)

    def apply_healing(self, amount: int) -> None:
        self.hit_points = self.hit_points.apply_healing(amount)

    def add_condition(self, name: str) -> None:
        if not name.strip():
            raise ValidationError("condition name must be a non-empty string")
        if name not in self.conditions:
            self.conditions = (*self.conditions, name)

    def remove_condition(self, name: str) -> None:
        if name not in self.conditions:
            raise ValidationError(f"character does not have condition '{name}'")
        self.conditions = tuple(c for c in self.conditions if c != name)
