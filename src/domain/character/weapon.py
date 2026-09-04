"""Weapon value objects; damage dice are constrained to the standard die sizes."""

from __future__ import annotations

from dataclasses import dataclass

from domain.character.abilities import AbilityType
from domain.common.errors import ValidationError
from domain.rules.dice import DIE_SIZES


@dataclass(frozen=True)
class Weapon:
    weapon_id: str
    name: str
    damage_die_count: int
    damage_die_size: int
    ability: AbilityType = AbilityType.STRENGTH
    range_ft: int = 5

    def __post_init__(self) -> None:
        if not self.weapon_id.strip():
            raise ValidationError("weapon_id must be a non-empty string")
        if not self.name.strip():
            raise ValidationError("weapon name must be a non-empty string")
        if self.damage_die_count < 1:
            raise ValidationError("damage die count must be at least 1")
        if self.damage_die_size not in DIE_SIZES:
            raise ValidationError(
                f"damage die size must be one of {DIE_SIZES}, got d{self.damage_die_size}"
            )
        if self.range_ft < 1:
            raise ValidationError("weapon range must be at least 1 foot")
