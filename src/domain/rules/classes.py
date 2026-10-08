"""Class data row: identity and hit die; features arrive at R8."""

from __future__ import annotations

from dataclasses import dataclass

from domain.character.character import CharacterClass
from domain.common.errors import ValidationError
from domain.rules.dice import DIE_SIZES


@dataclass(frozen=True)
class ClassData:
    class_id: str
    name: str
    hit_die_size: int

    def __post_init__(self) -> None:
        if self.class_id not in {member.value for member in CharacterClass}:
            raise ValidationError(
                f"class_id {self.class_id!r} is not a CharacterClass value"
            )
        if not self.name.strip():
            raise ValidationError("class name must be a non-empty string")
        if self.hit_die_size not in DIE_SIZES:
            raise ValidationError(
                f"hit die size must be one of {DIE_SIZES}, got d{self.hit_die_size}"
            )
