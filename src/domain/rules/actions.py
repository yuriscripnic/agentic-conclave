"""Unified action model and per-turn action economy (Implementation Plan §7)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from domain.common.errors import ActionNotAvailableError, ValidationError
from domain.common.ids import CharacterId


class ActionType(StrEnum):
    ATTACK = "attack"
    ABILITY_CHECK = "ability_check"
    SAVING_THROW = "saving_throw"
    DASH = "dash"
    DODGE = "dodge"
    DISENGAGE = "disengage"
    HELP = "help"
    HIDE = "hide"
    READY = "ready"
    SEARCH = "search"
    USE_ITEM = "use_item"
    MOVE = "move"


class ActionCategory(StrEnum):
    ACTION = "action"
    BONUS_ACTION = "bonus_action"
    REACTION = "reaction"
    MOVEMENT = "movement"
    FREE = "free"


ACTION_CATEGORY: dict[ActionType, ActionCategory] = {
    ActionType.ATTACK: ActionCategory.ACTION,
    ActionType.ABILITY_CHECK: ActionCategory.ACTION,
    ActionType.SAVING_THROW: ActionCategory.FREE,
    ActionType.DASH: ActionCategory.ACTION,
    ActionType.DODGE: ActionCategory.ACTION,
    ActionType.DISENGAGE: ActionCategory.ACTION,
    ActionType.HELP: ActionCategory.ACTION,
    ActionType.HIDE: ActionCategory.ACTION,
    ActionType.READY: ActionCategory.ACTION,
    ActionType.SEARCH: ActionCategory.ACTION,
    ActionType.USE_ITEM: ActionCategory.ACTION,
    ActionType.MOVE: ActionCategory.MOVEMENT,
}


@dataclass(frozen=True)
class AttackProposal:
    actor_id: CharacterId
    target_id: CharacterId
    weapon_id: str | None = None

    @property
    def action_type(self) -> ActionType:
        return ActionType.ATTACK


@dataclass(frozen=True)
class GenericActionProposal:
    actor_id: CharacterId
    action_type: ActionType


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    reason: str = ""
    error_code: str = ""

    @classmethod
    def ok(cls) -> ValidationResult:
        return cls(valid=True)

    @classmethod
    def reject(cls, reason: str, error_code: str) -> ValidationResult:
        return cls(valid=False, reason=reason, error_code=error_code)


@dataclass
class ActionEconomy:
    movement_budget_ft: int
    movement_used_ft: int = 0
    action_taken: bool = False
    bonus_action_taken: bool = False
    reaction_taken: bool = False

    def __post_init__(self) -> None:
        if self.movement_budget_ft < 0:
            raise ValidationError("movement budget must be non-negative")

    def use(self, action_type: ActionType) -> None:
        category = ACTION_CATEGORY[action_type]
        if category is ActionCategory.ACTION:
            if self.action_taken:
                raise ActionNotAvailableError("action already used this turn")
            self.action_taken = True
        elif category is ActionCategory.BONUS_ACTION:
            if self.bonus_action_taken:
                raise ActionNotAvailableError("bonus action already used this turn")
            self.bonus_action_taken = True
        elif category is ActionCategory.REACTION:
            if self.reaction_taken:
                raise ActionNotAvailableError("reaction already used this turn")
            self.reaction_taken = True

    def use_movement(self, feet: int) -> None:
        if feet < 0:
            raise ValidationError("movement must be non-negative")
        if self.movement_used_ft + feet > self.movement_budget_ft:
            raise ActionNotAvailableError("not enough movement left this turn")
        self.movement_used_ft += feet

    def remaining_movement_ft(self) -> int:
        return self.movement_budget_ft - self.movement_used_ft

    def can_take_action(self, action_type: ActionType) -> bool:
        category = ACTION_CATEGORY[action_type]
        if category is ActionCategory.ACTION:
            return not self.action_taken
        if category is ActionCategory.BONUS_ACTION:
            return not self.bonus_action_taken
        if category is ActionCategory.REACTION:
            return not self.reaction_taken
        return True

    def reset_for_new_turn(self) -> None:
        self.movement_used_ft = 0
        self.action_taken = False
        self.bonus_action_taken = False
        self.reaction_taken = False
