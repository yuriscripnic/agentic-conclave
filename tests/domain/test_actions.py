import pytest

from domain.common.errors import ActionNotAvailableError, ValidationError
from domain.common.ids import CharacterId
from domain.rules.actions import (
    ACTION_CATEGORY,
    ActionCategory,
    ActionEconomy,
    ActionType,
    AttackProposal,
    GenericActionProposal,
    ValidationResult,
)


def test_action_type_has_the_twelve_initial_actions() -> None:
    assert len(ActionType) == 12
    assert ActionType.ATTACK.value == "attack"
    assert ActionType.USE_ITEM.value == "use_item"


def test_action_category_mapping() -> None:
    assert ACTION_CATEGORY[ActionType.ATTACK] is ActionCategory.ACTION
    assert ACTION_CATEGORY[ActionType.MOVE] is ActionCategory.MOVEMENT
    assert ACTION_CATEGORY[ActionType.SAVING_THROW] is ActionCategory.FREE
    assert ACTION_CATEGORY[ActionType.DODGE] is ActionCategory.ACTION


def test_validation_result_factories() -> None:
    ok = ValidationResult.ok()
    assert ok.valid is True
    assert ok.reason == ""

    rejected = ValidationResult.reject("target out of range", "target_out_of_range")
    assert rejected.valid is False
    assert rejected.error_code == "target_out_of_range"


def test_attack_proposal_carries_only_intent() -> None:
    actor = CharacterId.generate()
    target = CharacterId.generate()
    proposal = AttackProposal(actor_id=actor, target_id=target, weapon_id="longsword")
    assert proposal.action_type is ActionType.ATTACK
    assert proposal.weapon_id == "longsword"


def test_generic_proposal() -> None:
    proposal = GenericActionProposal(
        actor_id=CharacterId.generate(), action_type=ActionType.DODGE
    )
    assert proposal.action_type is ActionType.DODGE


def test_action_economy_tracks_actions_per_turn() -> None:
    economy = ActionEconomy(movement_budget_ft=30)
    assert economy.can_take_action(ActionType.ATTACK) is True

    economy.use(ActionType.ATTACK)
    assert economy.action_taken is True
    assert economy.can_take_action(ActionType.ATTACK) is False
    assert economy.can_take_action(ActionType.DODGE) is False
    assert economy.can_take_action(ActionType.MOVE) is True

    with pytest.raises(ActionNotAvailableError):
        economy.use(ActionType.ATTACK)


def test_action_economy_movement() -> None:
    economy = ActionEconomy(movement_budget_ft=30)
    economy.use_movement(20)
    assert economy.remaining_movement_ft() == 10
    with pytest.raises(ActionNotAvailableError):
        economy.use_movement(15)
    with pytest.raises(ValidationError):
        economy.use_movement(-1)


def test_action_economy_resets_for_new_turn() -> None:
    economy = ActionEconomy(movement_budget_ft=30)
    economy.use(ActionType.ATTACK)
    economy.use_movement(30)
    economy.reset_for_new_turn()
    assert economy.action_taken is False
    assert economy.remaining_movement_ft() == 30
    assert economy.can_take_action(ActionType.ATTACK) is True


def test_negative_movement_budget_rejected() -> None:
    with pytest.raises(ValidationError):
        ActionEconomy(movement_budget_ft=-1)
