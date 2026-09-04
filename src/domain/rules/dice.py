"""Seeded deterministic dice engine (CLAUDE.md §15, Implementation Plan §5)."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from enum import StrEnum

from domain.common.errors import ValidationError

DIE_SIZES: tuple[int, ...] = (4, 6, 8, 10, 12, 20, 100)

_EXPRESSION_PATTERN = re.compile(r"^(\d*)d(\d+)([+-]\d+)?$")


@dataclass(frozen=True)
class DiceResult:
    die_size: int
    all_rolls: tuple[int, ...]
    kept_rolls: tuple[int, ...]
    modifier: int
    total: int

    @property
    def natural(self) -> int | None:
        """The kept natural roll, only meaningful for a single-die d20 roll."""
        if self.die_size == 20 and len(self.kept_rolls) == 1:
            return self.kept_rolls[0]
        return None


class RollMode(StrEnum):
    NORMAL = "normal"
    ADVANTAGE = "advantage"
    DISADVANTAGE = "disadvantage"


class DiceRoller:
    """All game randomness flows through here, seeded for reproducibility."""

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)

    def roll(
        self,
        count: int,
        die_size: int,
        modifier: int = 0,
        mode: RollMode = RollMode.NORMAL,
    ) -> DiceResult:
        if count < 1:
            raise ValidationError(f"dice count must be at least 1, got {count}")
        if die_size not in DIE_SIZES:
            raise ValidationError(
                f"die size must be one of {DIE_SIZES}, got d{die_size}"
            )

        all_rolls: tuple[int, ...]
        kept_rolls: tuple[int, ...]
        if mode is not RollMode.NORMAL:
            if (count, die_size) != (1, 20):
                raise ValidationError(
                    "advantage/disadvantage apply only to a single d20 roll"
                )
            first = self._rng.randint(1, die_size)
            second = self._rng.randint(1, die_size)
            all_rolls = (first, second)
            kept = (
                max(first, second) if mode is RollMode.ADVANTAGE else min(first, second)
            )
            kept_rolls = (kept,)
        else:
            all_rolls = tuple(self._rng.randint(1, die_size) for _ in range(count))
            kept_rolls = all_rolls

        return DiceResult(
            die_size=die_size,
            all_rolls=all_rolls,
            kept_rolls=kept_rolls,
            modifier=modifier,
            total=sum(kept_rolls) + modifier,
        )

    def roll_d20(
        self, modifier: int = 0, mode: RollMode = RollMode.NORMAL
    ) -> DiceResult:
        return self.roll(1, 20, modifier=modifier, mode=mode)

    def roll_expression(self, expression: str) -> DiceResult:
        match = _EXPRESSION_PATTERN.fullmatch(expression.strip().lower())
        if match is None:
            raise ValidationError(f"invalid dice expression: {expression!r}")
        count_text, die_text, modifier_text = match.groups()
        count = int(count_text) if count_text else 1
        die_size = int(die_text)
        modifier = int(modifier_text) if modifier_text else 0
        return self.roll(count, die_size, modifier=modifier)
