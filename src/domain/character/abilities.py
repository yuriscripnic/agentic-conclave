"""Ability scores and modifiers — Implementation Plan §4.2."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from domain.common.errors import ValidationError

MIN_SCORE = 1
MAX_SCORE = 30


class AbilityType(StrEnum):
    STRENGTH = "strength"
    DEXTERITY = "dexterity"
    CONSTITUTION = "constitution"
    INTELLIGENCE = "intelligence"
    WISDOM = "wisdom"
    CHARISMA = "charisma"


def _validate_score(score: int) -> None:
    if not MIN_SCORE <= score <= MAX_SCORE:
        raise ValidationError(
            f"ability score must be between {MIN_SCORE} and {MAX_SCORE}, got {score}"
        )


def ability_modifier(score: int) -> int:
    """D&D 5e ability modifier: floor((score - 10) / 2)."""
    _validate_score(score)
    return (score - 10) // 2


@dataclass(frozen=True)
class AbilityScore:
    ability_type: AbilityType
    score: int

    def __post_init__(self) -> None:
        _validate_score(self.score)

    @property
    def modifier(self) -> int:
        return ability_modifier(self.score)


@dataclass(frozen=True)
class AbilityScores:
    strength: int
    dexterity: int
    constitution: int
    intelligence: int
    wisdom: int
    charisma: int

    def __post_init__(self) -> None:
        for ability_type in AbilityType:
            _validate_score(self.score(ability_type))

    def score(self, ability_type: AbilityType) -> int:
        score_value: int = getattr(self, ability_type.value)
        return score_value

    def modifier(self, ability_type: AbilityType) -> int:
        return ability_modifier(self.score(ability_type))
