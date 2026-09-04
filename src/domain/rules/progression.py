"""Character progression rules (Implementation Plan §4.3)."""

from __future__ import annotations

from domain.common.errors import ValidationError

MIN_LEVEL = 1
MAX_LEVEL = 20


def proficiency_bonus(level: int) -> int:
    """D&D 5e proficiency bonus: 2 + floor((level - 1) / 4)."""
    if not MIN_LEVEL <= level <= MAX_LEVEL:
        raise ValidationError(
            f"level must be between {MIN_LEVEL} and {MAX_LEVEL}, got {level}"
        )
    return 2 + (level - 1) // 4
