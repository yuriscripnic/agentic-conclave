import pytest

from domain.common.errors import ValidationError
from domain.space.board import Board, CoverLevel, higher_cover
from domain.space.square import Square


def test_board_accessors() -> None:
    board = Board(
        width=3,
        height=3,
        walls=frozenset({Square(0, 0)}),
        cover={Square(2, 2): CoverLevel.HALF},
    )
    assert board.in_bounds(Square(2, 2))
    assert not board.in_bounds(Square(3, 0))
    assert board.is_wall(Square(0, 0))
    assert not board.is_wall(Square(1, 1))
    assert board.cover_at(Square(2, 2)) is CoverLevel.HALF
    assert board.cover_at(Square(1, 1)) is CoverLevel.NONE


def test_wall_outside_board_rejected() -> None:
    with pytest.raises(ValidationError):
        Board(width=2, height=2, walls=frozenset({Square(2, 0)}))


def test_wall_cannot_carry_cover() -> None:
    with pytest.raises(ValidationError):
        Board(
            width=2,
            height=2,
            walls=frozenset({Square(0, 0)}),
            cover={Square(0, 0): CoverLevel.HALF},
        )


def test_cover_level_none_rejected() -> None:
    with pytest.raises(ValidationError):
        Board(width=2, height=2, cover={Square(0, 0): CoverLevel.NONE})


def test_higher_cover_returns_the_more_severe_level() -> None:
    assert higher_cover(CoverLevel.NONE, CoverLevel.HALF) is CoverLevel.HALF
    assert higher_cover(CoverLevel.THREE_QUARTERS, CoverLevel.HALF) is (
        CoverLevel.THREE_QUARTERS
    )
