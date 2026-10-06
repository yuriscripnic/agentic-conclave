"""Grid squares: the address of one 5-ft cell on a battle map (R1 spec §3)."""

from __future__ import annotations

from dataclasses import dataclass

from domain.common.errors import ValidationError


@dataclass(frozen=True, order=True)
class Square:
    x: int
    y: int

    def __post_init__(self) -> None:
        if self.x < 0 or self.y < 0:
            raise ValidationError(
                f"square coordinates must be non-negative, got ({self.x}, {self.y})"
            )
