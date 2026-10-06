"""Pure spatial geometry over a board: distance, line of sight, cover (R1 spec §3)."""

from __future__ import annotations

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
