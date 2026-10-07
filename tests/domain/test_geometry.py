import pytest

from domain.space.board import Board
from domain.space.geometry import distance_ft, line_of_sight
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


def _board(walls: set[tuple[int, int]]) -> Board:
    return Board(
        width=6,
        height=6,
        walls=frozenset(Square(x, y) for x, y in walls),
    )


def test_open_room_has_line_of_sight() -> None:
    assert line_of_sight(_board(set()), Square(0, 0), Square(5, 5))


def test_wall_in_the_same_row_blocks_sight() -> None:
    assert not line_of_sight(_board({(2, 0)}), Square(0, 0), Square(4, 0))


def test_peeking_past_a_wall_corner_sees_the_target() -> None:
    # Attacker (0,0), target (2,2), wall (1,1): the segment (1,0)->(3,2) touches
    # the wall only at its corner (2,1), so sight exists.
    assert line_of_sight(_board({(1, 1)}), Square(0, 0), Square(2, 2))


def test_line_grazing_only_a_wall_corner_is_clear() -> None:
    assert line_of_sight(_board({(1, 1)}), Square(0, 0), Square(1, 2))


def test_solid_wall_block_between_diagonals_blocks_sight() -> None:
    walls = {(1, 1), (1, 2), (2, 1), (2, 2)}
    assert not line_of_sight(_board(walls), Square(0, 0), Square(3, 3))


def test_a_wall_nowhere_near_the_line_does_not_block() -> None:
    assert line_of_sight(_board({(4, 4)}), Square(0, 0), Square(1, 1))


def test_non_dyadic_corner_graze_is_clear() -> None:
    # Segment (0,0)->(22,22) passes exactly through the corner (15,15) of wall
    # (15,15) at t = 15/22 — a non-dyadic parameter, so float reconstruction
    # would misclassify it as blocked.
    board = Board(width=23, height=23, walls=frozenset({Square(15, 15)}))
    assert line_of_sight(board, Square(0, 0), Square(22, 22))
