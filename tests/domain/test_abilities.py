import pytest

from domain.character.abilities import (
    MAX_SCORE,
    MIN_SCORE,
    AbilityScore,
    AbilityScores,
    AbilityType,
    ability_modifier,
)
from domain.common.errors import ValidationError


@pytest.mark.parametrize(
    ("score", "expected"),
    [(1, -5), (8, -1), (9, -1), (10, 0), (11, 0), (16, 3), (20, 5), (30, 10)],
)
def test_ability_modifier_uses_floor_division(score: int, expected: int) -> None:
    assert ability_modifier(score) == expected


@pytest.mark.parametrize("score", [0, 31, -3])
def test_ability_modifier_rejects_out_of_range(score: int) -> None:
    with pytest.raises(ValidationError):
        ability_modifier(score)


def test_ability_score_value_object() -> None:
    strength = AbilityScore(ability_type=AbilityType.STRENGTH, score=16)
    assert strength.modifier == 3
    assert strength.score == 16


def test_bounds_constants() -> None:
    assert (MIN_SCORE, MAX_SCORE) == (1, 30)


def test_ability_scores_aggregate() -> None:
    scores = AbilityScores(
        strength=16,
        dexterity=13,
        constitution=15,
        intelligence=10,
        wisdom=12,
        charisma=9,
    )
    assert scores.score(AbilityType.DEXTERITY) == 13
    assert scores.modifier(AbilityType.DEXTERITY) == 1
    assert scores.modifier(AbilityType.CHARISMA) == -1


def test_ability_scores_reject_invalid_score() -> None:
    with pytest.raises(ValidationError):
        AbilityScores(
            strength=16,
            dexterity=13,
            constitution=15,
            intelligence=10,
            wisdom=12,
            charisma=99,
        )
