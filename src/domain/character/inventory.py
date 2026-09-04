"""Character inventory with explicit error signaling."""

from __future__ import annotations

from dataclasses import dataclass, field

from domain.common.errors import InsufficientResourceError, ValidationError


@dataclass
class Item:
    item_id: str
    name: str
    quantity: int

    def __post_init__(self) -> None:
        if not self.item_id.strip():
            raise ValidationError("item_id must be a non-empty string")
        if not self.name.strip():
            raise ValidationError("item name must be a non-empty string")
        if self.quantity < 1:
            raise ValidationError("item quantity must be at least 1")


@dataclass
class Inventory:
    items: dict[str, Item] = field(default_factory=dict)
    gold: int = 0

    def __post_init__(self) -> None:
        if self.gold < 0:
            raise ValidationError("gold must be non-negative")

    def get_item(self, item_id: str) -> Item | None:
        return self.items.get(item_id)

    def add_item(self, item_id: str, name: str, quantity: int) -> None:
        if quantity < 1:
            raise ValidationError("quantity must be at least 1")
        existing = self.items.get(item_id)
        if existing is None:
            self.items[item_id] = Item(item_id=item_id, name=name, quantity=quantity)
        else:
            existing.quantity += quantity

    def remove_item(self, item_id: str, quantity: int) -> None:
        existing = self.items.get(item_id)
        if existing is None or existing.quantity < quantity:
            raise InsufficientResourceError(
                f"not enough of item '{item_id}' to remove {quantity}"
            )
        existing.quantity -= quantity
        if existing.quantity == 0:
            del self.items[item_id]

    def add_gold(self, amount: int) -> None:
        if amount < 0:
            raise ValidationError("gold amount must be non-negative")
        self.gold += amount

    def spend_gold(self, amount: int) -> None:
        if amount < 0:
            raise ValidationError("gold amount must be non-negative")
        if self.gold < amount:
            raise InsufficientResourceError(
                f"need {amount} gold, only {self.gold} available"
            )
        self.gold -= amount
