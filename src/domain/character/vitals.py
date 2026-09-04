"""Hit points as an immutable value object with clamping semantics."""

from __future__ import annotations

from dataclasses import dataclass

from domain.common.errors import ValidationError


@dataclass(frozen=True)
class HitPoints:
    current: int
    maximum: int

    def __post_init__(self) -> None:
        if self.maximum < 1:
            raise ValidationError(f"maximum hp must be at least 1, got {self.maximum}")
        if not 0 <= self.current <= self.maximum:
            raise ValidationError(
                f"current hp must be between 0 and {self.maximum}, got {self.current}"
            )

    @property
    def is_defeated(self) -> bool:
        return self.current == 0

    def apply_damage(self, amount: int) -> HitPoints:
        if amount < 0:
            raise ValidationError("damage amount must be non-negative")
        return HitPoints(current=max(0, self.current - amount), maximum=self.maximum)

    def apply_healing(self, amount: int) -> HitPoints:
        if amount < 0:
            raise ValidationError("healing amount must be non-negative")
        return HitPoints(
            current=min(self.maximum, self.current + amount), maximum=self.maximum
        )
