"""The Ruleset port (CLAUDE.md §13): rules data behind an interface."""

from __future__ import annotations

from typing import Protocol

from domain.character.weapon import Weapon
from domain.rules.classes import ClassData
from domain.rules.statblock import Statblock


class Ruleset(Protocol):
    """Queries the rules engine makes against the active ruleset's data."""

    @property
    def ruleset_id(self) -> str: ...

    @property
    def diagonal_rule(self) -> str: ...

    def weapon(self, weapon_id: str) -> Weapon: ...

    def statblock(self, statblock_id: str) -> Statblock: ...

    def character_class(self, class_id: str) -> ClassData: ...
