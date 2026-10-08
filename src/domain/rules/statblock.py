"""Monster statblock value object: the enemy shape the encounter loader maps."""

from __future__ import annotations

from dataclasses import dataclass

from domain.common.errors import ValidationError
from domain.rules.progression import MAX_LEVEL, MIN_LEVEL


@dataclass(frozen=True)
class Statblock:
    statblock_id: str
    name: str
    level: int
    strength: int
    dexterity: int
    constitution: int
    intelligence: int
    wisdom: int
    charisma: int
    armor_class: int
    speed_ft: int
    max_hp: int
    weapon_id: str

    def __post_init__(self) -> None:
        if not self.statblock_id.strip():
            raise ValidationError("statblock_id must be a non-empty string")
        if not self.name.strip():
            raise ValidationError("statblock name must be a non-empty string")
        if not self.weapon_id.strip():
            raise ValidationError("statblock weapon_id must be a non-empty string")
        if not MIN_LEVEL <= self.level <= MAX_LEVEL:
            raise ValidationError(
                f"statblock level must be between {MIN_LEVEL} and {MAX_LEVEL}, "
                f"got {self.level}"
            )
        for field in (
            "strength",
            "dexterity",
            "constitution",
            "intelligence",
            "wisdom",
            "charisma",
            "armor_class",
            "speed_ft",
            "max_hp",
        ):
            value = getattr(self, field)
            if value < 1:
                raise ValidationError(
                    f"statblock {field} must be at least 1, got {value}"
                )
