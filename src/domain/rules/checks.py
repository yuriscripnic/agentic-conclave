"""Deterministic resolution of checks, saves, and attack rolls (Implementation Plan §6)."""

from __future__ import annotations

from dataclasses import dataclass

from domain.common.errors import ValidationError
from domain.rules.dice import DiceRoller, RollMode


@dataclass(frozen=True)
class CheckResult:
    roll: int
    modifier: int
    total: int
    dc: int | None
    success: bool
    mode: RollMode


@dataclass(frozen=True)
class AttackRollResult:
    roll: int
    attack_bonus: int
    total: int
    target_ac: int
    hit: bool
    is_critical: bool
    is_critical_miss: bool
    mode: RollMode


class CheckResolver:
    def __init__(self, dice: DiceRoller) -> None:
        self._dice = dice

    def ability_check(
        self,
        modifier: int,
        dc: int | None = None,
        proficient: bool = False,
        proficiency_bonus: int = 0,
        mode: RollMode = RollMode.NORMAL,
    ) -> CheckResult:
        if proficient and proficiency_bonus < 0:
            raise ValidationError("proficiency bonus must be non-negative")
        total_bonus = modifier + (proficiency_bonus if proficient else 0)
        result = self._dice.roll_d20(modifier=total_bonus, mode=mode)
        total = result.total
        success = total >= dc if dc is not None else False
        return CheckResult(
            roll=result.natural if result.natural is not None else 0,
            modifier=total_bonus,
            total=total,
            dc=dc,
            success=success,
            mode=mode,
        )

    def saving_throw(
        self,
        modifier: int,
        dc: int,
        proficient: bool = False,
        proficiency_bonus: int = 0,
        mode: RollMode = RollMode.NORMAL,
    ) -> CheckResult:
        return self.ability_check(
            modifier=modifier,
            dc=dc,
            proficient=proficient,
            proficiency_bonus=proficiency_bonus,
            mode=mode,
        )

    def attack_roll(
        self,
        attack_bonus: int,
        target_ac: int,
        mode: RollMode = RollMode.NORMAL,
    ) -> AttackRollResult:
        if target_ac < 0:
            raise ValidationError("armor class must be non-negative")
        result = self._dice.roll_d20(modifier=attack_bonus, mode=mode)
        natural = result.natural
        if natural is None:  # pragma: no cover - roll_d20 always yields a natural
            raise ValidationError("attack roll requires a single d20")
        is_critical = natural == 20
        is_critical_miss = natural == 1
        hit = is_critical or (not is_critical_miss and result.total >= target_ac)
        return AttackRollResult(
            roll=natural,
            attack_bonus=attack_bonus,
            total=result.total,
            target_ac=target_ac,
            hit=hit,
            is_critical=is_critical,
            is_critical_miss=is_critical_miss,
            mode=mode,
        )
