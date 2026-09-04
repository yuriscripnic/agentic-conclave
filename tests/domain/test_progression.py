import pytest

from domain.common.errors import ValidationError
from domain.rules.progression import proficiency_bonus


@pytest.mark.parametrize(
    ("level", "expected"),
    [(1, 2), (4, 2), (5, 3), (8, 3), (9, 4), (12, 4), (13, 5), (17, 6), (20, 6)],
)
def test_proficiency_bonus_by_level(level: int, expected: int) -> None:
    assert proficiency_bonus(level) == expected


@pytest.mark.parametrize("level", [0, 21, -1])
def test_proficiency_bonus_rejects_invalid_level(level: int) -> None:
    with pytest.raises(ValidationError):
        proficiency_bonus(level)
