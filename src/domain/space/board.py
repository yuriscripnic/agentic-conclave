"""Battle boards: walls and cover terrain over a grid of squares (R1 spec §3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from domain.common.errors import ValidationError
from domain.space.square import Square


class CoverLevel(StrEnum):
    NONE = "none"
    HALF = "half"
    THREE_QUARTERS = "three_quarters"
    TOTAL = "total"


SEVERITY: tuple[CoverLevel, ...] = (
    CoverLevel.NONE,
    CoverLevel.HALF,
    CoverLevel.THREE_QUARTERS,
    CoverLevel.TOTAL,
)


def higher_cover(a: CoverLevel, b: CoverLevel) -> CoverLevel:
    """The more severe of two cover levels (enum members do not order by value)."""
    return a if SEVERITY.index(a) >= SEVERITY.index(b) else b


@dataclass(frozen=True)
class Board:
    width: int
    height: int
    walls: frozenset[Square] = frozenset()
    cover: dict[Square, CoverLevel] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.width < 1 or self.height < 1:
            raise ValidationError("board dimensions must be positive")
        for square in self.walls:
            self._check(square, "wall")
        for square, level in self.cover.items():
            self._check(square, "cover")
            if square in self.walls:
                raise ValidationError(f"wall square {square} cannot carry cover")
            if level is CoverLevel.NONE:
                raise ValidationError("cover squares must carry a non-NONE level")

    def _check(self, square: Square, what: str) -> None:
        if not self.in_bounds(square):
            raise ValidationError(f"{what} square {square} is outside the board")

    def in_bounds(self, square: Square) -> bool:
        return 0 <= square.x < self.width and 0 <= square.y < self.height

    def is_wall(self, square: Square) -> bool:
        return square in self.walls

    def cover_at(self, square: Square) -> CoverLevel:
        return self.cover.get(square, CoverLevel.NONE)


@dataclass(frozen=True)
class Spawns:
    party: tuple[Square, ...]
    enemies: tuple[Square, ...]
