"""Pure spatial geometry over a board: distance, line of sight, cover (R1 spec §3)."""

from __future__ import annotations

from domain.space.board import Board
from domain.space.square import Square


def distance_ft(a: Square, b: Square) -> int:
    """Distance in feet, 5-10-5: each diagonal step of the Chebyshev path costs
    5, then 10, alternating; straight steps cost 5."""
    dx = abs(a.x - b.x)
    dy = abs(a.y - b.y)
    diagonals = min(dx, dy)
    straight = max(dx, dy) - diagonals
    total = 0
    for index in range(diagonals):
        total += 5 if index % 2 == 0 else 10
    return total + 5 * straight


_Point = tuple[float, float]

_CORNER_OFFSETS: tuple[tuple[float, float], ...] = (
    (0.0, 0.0),
    (1.0, 0.0),
    (0.0, 1.0),
    (1.0, 1.0),
)


def _corners(square: Square) -> tuple[_Point, ...]:
    return tuple((square.x + dx, square.y + dy) for dx, dy in _CORNER_OFFSETS)


def _cell_blocks(cell: Square, p1: _Point, p2: _Point) -> bool:
    """Liang-Barsky clip of the segment against the cell's closed area.

    The wall blocks unless the segment meets the cell only at one of the cell's
    four corner points (R1 spec §3 edge rule): a positive-length overlap blocks,
    a single contact point blocks unless it is exactly a corner.
    """
    x, y = cell.x, cell.y
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    t0, t1 = 0.0, 1.0
    for delta, origin, low, high in ((dx, p1[0], x, x + 1), (dy, p1[1], y, y + 1)):
        if delta == 0:
            if not low <= origin <= high:
                return False
            continue
        enter = (low - origin) / delta
        exit_ = (high - origin) / delta
        if delta > 0:
            if enter > t1 or exit_ < t0:
                return False
            t0, t1 = max(t0, enter), min(t1, exit_)
        else:
            if exit_ > t1 or enter < t0:
                return False
            t0, t1 = max(t0, exit_), min(t1, enter)
    if t0 > t1:
        return False
    if t0 == t1:
        point = (p1[0] + t0 * dx, p1[1] + t0 * dy)
        corner_set = {(x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1)}
        return not any(point == corner for corner in corner_set)
    return True


def _blocked_segment_count(board: Board, a: Square, b: Square) -> int:
    blocked = 0
    for p1 in _corners(a):
        for p2 in _corners(b):
            if any(_cell_blocks(wall, p1, p2) for wall in board.walls):
                blocked += 1
    return blocked


def line_of_sight(board: Board, a: Square, b: Square) -> bool:
    """Sight exists if at least one corner-to-corner segment touches no wall."""
    return _blocked_segment_count(board, a, b) < len(_CORNER_OFFSETS) ** 2
