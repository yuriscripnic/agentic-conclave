"""Pure spatial geometry over a board: distance, line of sight, cover (R1 spec §3)."""

from __future__ import annotations

from domain.space.board import Board, CoverLevel, higher_cover
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
        return not _touches_a_corner(cell, p1, p2)
    return True


def _touches_a_corner(cell: Square, p1: _Point, p2: _Point) -> bool:
    """Whether a single-point contact is a corner graze.

    Decided with exact integer arithmetic: corner coordinates and the segment
    endpoints are integer-valued, so the cross product is exact. Reconstructing
    the contact point as ``p1 + t0 * (p2 - p1)`` is not: for a non-dyadic
    parameter such as t = 15/22 the reconstruction is off by ~1 ulp and the
    graze is misread as a block.
    """
    px, py = p1
    dx, dy = p2[0] - px, p2[1] - py
    for corner in _corners(cell):
        cx, cy = corner
        if dx * (cy - py) - dy * (cx - px) != 0:
            continue
        if min(px, p2[0]) <= cx <= max(px, p2[0]) and min(py, p2[1]) <= cy <= max(py, p2[1]):
            return True
    return False


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


def cover_between(board: Board, a: Square, b: Square) -> CoverLevel:
    """Cover the target has against an attacker at ``a`` (R1 spec §3).

    All 16 segments blocked -> TOTAL; none blocked -> the target square's own
    flag; some blocked -> at least HALF, upgraded to the target's flag.
    """
    blocked = _blocked_segment_count(board, a, b)
    own = board.cover_at(b)
    if blocked >= len(_CORNER_OFFSETS) ** 2:
        return CoverLevel.TOTAL
    if blocked == 0:
        return own
    return higher_cover(CoverLevel.HALF, own)
