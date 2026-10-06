import pytest

from domain.common.errors import ValidationError
from domain.space.square import Square


def test_square_holds_coordinates_and_compares() -> None:
    assert Square(2, 3) == Square(2, 3)
    assert Square(1, 5) < Square(2, 5)
    assert hash(Square(1, 1)) == hash(Square(1, 1))


@pytest.mark.parametrize("x,y", [(-1, 0), (0, -1)])
def test_negative_coordinates_rejected(x: int, y: int) -> None:
    with pytest.raises(ValidationError):
        Square(x, y)
