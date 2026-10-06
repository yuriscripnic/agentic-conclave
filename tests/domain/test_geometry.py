import pytest

from domain.space.geometry import distance_ft
from domain.space.square import Square


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        (Square(0, 0), Square(0, 0), 0),
        (Square(0, 0), Square(3, 0), 15),  # straight only
        (Square(0, 0), Square(1, 1), 5),  # first diagonal = 5
        (Square(0, 0), Square(2, 2), 15),  # second diagonal = 10
        (Square(0, 0), Square(3, 1), 15),  # 1 diagonal + 2 straight
        (Square(0, 0), Square(4, 2), 25),  # 2 diagonals (15) + 2 straight (10)
        (Square(0, 0), Square(20, 0), 100),  # the §28 example, verbatim
    ],
)
def test_distance_uses_the_5_10_5_rule(a: Square, b: Square, expected: int) -> None:
    assert distance_ft(a, b) == expected


def test_distance_is_symmetric() -> None:
    assert distance_ft(Square(0, 0), Square(3, 2)) == distance_ft(Square(3, 2), Square(0, 0))
