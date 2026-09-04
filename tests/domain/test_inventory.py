import pytest

from domain.character.inventory import Inventory
from domain.common.errors import InsufficientResourceError, ValidationError


def test_add_then_remove_item() -> None:
    inventory = Inventory()
    inventory.add_item("rope", "Hempen Rope", 1)
    inventory.add_item("rope", "Hempen Rope", 2)
    assert inventory.get_item("rope") is not None
    assert inventory.get_item("rope").quantity == 3

    inventory.remove_item("rope", 2)
    assert inventory.get_item("rope").quantity == 1


def test_remove_item_raises_when_missing_or_insufficient() -> None:
    inventory = Inventory()
    with pytest.raises(InsufficientResourceError):
        inventory.remove_item("rope", 1)

    inventory.add_item("rope", "Hempen Rope", 1)
    with pytest.raises(InsufficientResourceError):
        inventory.remove_item("rope", 2)


def test_add_item_rejects_invalid_quantity_or_name() -> None:
    inventory = Inventory()
    with pytest.raises(ValidationError):
        inventory.add_item("rope", "Hempen Rope", 0)
    with pytest.raises(ValidationError):
        inventory.add_item("rope", "  ", 1)


def test_gold_add_and_spend() -> None:
    inventory = Inventory(gold=10)
    inventory.add_gold(5)
    inventory.spend_gold(15)
    assert inventory.gold == 0


def test_spend_gold_raises_when_insufficient() -> None:
    inventory = Inventory(gold=1)
    with pytest.raises(InsufficientResourceError):
        inventory.spend_gold(2)


def test_negative_gold_rejected() -> None:
    with pytest.raises(ValidationError):
        Inventory(gold=-1)
